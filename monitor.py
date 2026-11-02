"""
localsearchuf — монитор онлайна своих Telegram-аккаунтов.

Один watcher-аккаунт следит за списком целей (по @username или id):
  - пишет в консоль/лог, когда цель заходит в онлайн и уходит в офлайн;
  - помечает ⚠, если цель давно не была онлайн или её статус скрыт
    (возможный признак того, что аккаунт "лёг").

Запуск:
    python monitor.py            # бесконечный мониторинг
    python monitor.py --once     # один проход и выход
"""

import argparse
import asyncio
import configparser
import datetime as dt
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.types import (
    UserStatusOnline,
    UserStatusOffline,
    UserStatusRecently,
    UserStatusLastWeek,
    UserStatusLastMonth,
    UserStatusEmpty,
)

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.ini"
TARGETS_PATH = BASE / "targets.txt"
LOG_PATH = BASE / "monitor.log"


def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(line: str) -> None:
    """Печатает в консоль и дописывает в monitor.log."""
    stamped = f"[{now()}] {line}"
    print(stamped, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(stamped + "\n")
    except OSError:
        pass


def load_config() -> configparser.ConfigParser:
    if not CONFIG_PATH.exists():
        sys.exit(
            f"Нет {CONFIG_PATH.name}. Скопируй config.example.ini в config.ini "
            "и впиши свои api_id / api_hash."
        )
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding="utf-8")
    return cfg


def load_targets() -> list[str]:
    """Читает targets.txt: по одному @username или id в строке. # — комментарий."""
    if not TARGETS_PATH.exists():
        sys.exit(f"Нет {TARGETS_PATH.name}. Впиши туда свои аккаунты (по одному в строке).")
    targets = []
    for raw in TARGETS_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        targets.append(line)
    if not targets:
        sys.exit(f"{TARGETS_PATH.name} пустой — некого мониторить.")
    return targets


def parse_target(value: str):
    """'123456' -> int (id), '@user'/'user' -> str (username)."""
    v = value.lstrip("@")
    return int(v) if v.isdigit() else v


def describe_status(status) -> tuple[str, str]:
    """
    Превращает UserStatus в (state, detail).
    state: online | offline | recently | hidden | unknown
    """
    if isinstance(status, UserStatusOnline):
        return "online", "в сети"
    if isinstance(status, UserStatusOffline):
        was = status.was_online
        when = was.astimezone().strftime("%Y-%m-%d %H:%M:%S") if was else "?"
        return "offline", f"был(а) {when}"
    if isinstance(status, UserStatusRecently):
        return "recently", "недавно (точное время скрыто)"
    if isinstance(status, UserStatusLastWeek):
        return "hidden", "на этой неделе (скрыто)"
    if isinstance(status, UserStatusLastMonth):
        return "hidden", "в этом месяце (скрыто)"
    if isinstance(status, UserStatusEmpty) or status is None:
        return "hidden", "статус недоступен"
    return "unknown", str(type(status).__name__)


class Watcher:
    def __init__(self, client: TelegramClient, targets: list[str], offline_alert_min: int):
        self.client = client
        self.raw_targets = targets
        self.offline_alert = dt.timedelta(minutes=offline_alert_min)
        self.entities: dict[str, object] = {}   # исходная строка -> entity
        self.labels: dict[str, str] = {}         # исходная строка -> человекочитаемое имя
        self.prev_state: dict[str, str] = {}     # исходная строка -> прошлый state

    async def resolve(self) -> None:
        """Один раз находим каждую цель и запоминаем её."""
        for t in self.raw_targets:
            try:
                ent = await self.client.get_entity(parse_target(t))
                self.entities[t] = ent
                name = getattr(ent, "first_name", None) or getattr(ent, "title", None) or ""
                uname = getattr(ent, "username", None)
                label = name.strip()
                if uname:
                    label = f"{label} (@{uname})".strip()
                self.labels[t] = label or t
                log(f"цель найдена: {t} -> {self.labels[t]} [id={getattr(ent,'id','?')}]")
            except (RPCError, ValueError) as e:
                self.labels[t] = t
                log(f"⚠ не удалось найти цель {t}: {e}. "
                    "Проверь username/id и что watcher может её видеть.")

    async def poll_once(self) -> None:
        for t in self.raw_targets:
            label = self.labels.get(t, t)
            if t not in self.entities:
                # цель не разрешилась при старте — пробуем снова
                try:
                    self.entities[t] = await self.client.get_entity(parse_target(t))
                except (RPCError, ValueError):
                    log(f"⚠ {label}: по-прежнему недоступна (возможно, лёг)")
                    self.prev_state[t] = "unreachable"
                    continue

            try:
                # свежий запрос статуса
                ent = await self.client.get_entity(getattr(self.entities[t], "id"))
                self.entities[t] = ent
            except (RPCError, ValueError) as e:
                if self.prev_state.get(t) != "unreachable":
                    log(f"⚠ {label}: пропал из доступа ({e}) — возможно, лёг")
                self.prev_state[t] = "unreachable"
                continue

            state, detail = describe_status(getattr(ent, "status", None))
            prev = self.prev_state.get(t)

            # Логируем только изменения состояния, чтобы не засорять лог.
            if state != prev:
                if state == "online":
                    log(f"🟢 {label}: ЗАШЁЛ В ОНЛАЙН")
                elif state == "offline":
                    log(f"⚪ {label}: ушёл в офлайн ({detail})")
                else:
                    log(f"• {label}: {detail}")

            # Предупреждение о "лёг": давно не был онлайн.
            if state == "offline" and isinstance(ent.status, UserStatusOffline):
                was = ent.status.was_online
                if was and (dt.datetime.now(dt.timezone.utc) - was) > self.offline_alert:
                    log(f"⚠ {label}: не был онлайн дольше "
                        f"{int(self.offline_alert.total_seconds() // 60)} мин — проверь аккаунт")

            self.prev_state[t] = state


async def run(once: bool) -> None:
    cfg = load_config()
    tg = cfg["telegram"]
    api_id = int(tg["api_id"])
    api_hash = tg["api_hash"]
    session = tg.get("session", "watcher")
    interval = int(cfg["monitor"].get("poll_interval_sec", "60"))
    offline_alert_min = int(cfg["monitor"].get("offline_alert_min", "120"))

    targets = load_targets()

    client = TelegramClient(str(BASE / session), api_id, api_hash)
    await client.start()  # при первом запуске спросит номер + код

    me = await client.get_me()
    log(f"watcher: {getattr(me,'first_name','')} "
        f"(@{getattr(me,'username',None)}) — слежу за {len(targets)} аккаунтами")

    watcher = Watcher(client, targets, offline_alert_min)
    await watcher.resolve()

    try:
        while True:
            await watcher.poll_once()
            if once:
                break
            await asyncio.sleep(interval)
    finally:
        await client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Монитор онлайна Telegram-аккаунтов")
    parser.add_argument("--once", action="store_true", help="один проход и выход")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.once))
    except KeyboardInterrupt:
        print("\nостановлено")


if __name__ == "__main__":
    main()
