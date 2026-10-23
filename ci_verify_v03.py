#!/usr/bin/env python3
from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path


def run(*args: str, cwd: Path | None = None) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=str(cwd) if cwd else None, check=True)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parent)).resolve()
    runner_temp = Path(os.environ.get("RUNNER_TEMP", "/tmp")).resolve()
    telegram = runner_temp / "Telegram-iOS"

    print("=== Python syntax ===", flush=True)
    for name in ("apply_ayu_v03.py", "apply_ayu_v03_fixed.py", "apply_ayu_v03_crashfix.py", "apply_ayu_profile_cache.py"):
        py_compile.compile(str(workspace / name), doraise=True)
        print(f"OK: {name}")

    ref = (workspace / "telegram-ref.txt").read_text(encoding="utf-8").strip()
    require(bool(ref), "telegram-ref.txt is empty")

    print("=== Checkout pinned Telegram source ===", flush=True)
    shutil.rmtree(telegram, ignore_errors=True)
    run("git", "init", str(telegram))
    run("git", "remote", "add", "origin", "https://github.com/TelegramMessenger/Telegram-iOS.git", cwd=telegram)
    run("git", "fetch", "--depth", "1", "origin", ref, cwd=telegram)
    run("git", "checkout", "--detach", "FETCH_HEAD", cwd=telegram)
    actual_ref = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=telegram, text=True).strip()
    require(actual_ref == ref, f"Pinned Telegram ref mismatch: {actual_ref} != {ref}")
    print(f"Telegram ref: {actual_ref}")

    print("=== Apply Ayu patches ===", flush=True)
    run(sys.executable, str(workspace / "apply_ayu_v03_crashfix.py"), str(telegram))
    run(sys.executable, str(workspace / "apply_ayu_profile_cache.py"), str(telegram))

    print("=== Verify native settings ===", flush=True)
    settings = (telegram / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoSettingsItems.swift").read_text(encoding="utf-8")
    marker = 'text: "AyuGram"'
    photo = "items[.edit]!.append(PeerInfoScreenActionItem(id: 2,"
    username = 'if let peer = data.peer, (peer.addressName ?? "").isEmpty {'
    require(settings.count(marker) == 1, "AyuGram settings row missing or duplicated")
    require(photo in settings, "profile photo row anchor missing")
    require(username in settings, "My Profile row anchor missing")
    require(settings.index(photo) < settings.index(marker) < settings.index(username), "AyuGram row is not between profile photo and My Profile")

    peer_info_root = telegram / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources"
    require((peer_info_root / "AyuSettingsController.swift").exists(), "AyuSettingsController.swift missing")
    require((peer_info_root / "AyuProfileFieldCache.swift").exists(), "AyuProfileFieldCache.swift missing")
    require((telegram / "submodules/TelegramCore/Sources/State/AyuGhostLastSeen.swift").exists(), "AyuGhostLastSeen.swift missing")

    debug = (telegram / "submodules/DebugSettingsUI/Sources/DebugController.swift").read_text(encoding="utf-8")
    require("AyuGram Settings" not in debug, "legacy DebugController Ayu row is still being injected")

    print("=== Verify Ghost read crash fix ===", flush=True)
    read_state = (telegram / "submodules/TelegramCore/Sources/State/SynchronizePeerReadState.swift").read_text(encoding="utf-8")
    require("Ghost read suppression must remove the Postbox" in read_state, "transaction-safe Ghost read marker missing")
    require("transaction.confirmSynchronizedIncomingReadState(peerId)" in read_state, "Ghost read operation is not consumed through Postbox")
    require("if validate && !AyuRuntimeSettings.suppressReadMessages" not in read_state, "old validation no-op recursion path is still present")
    dangerous = "if AyuRuntimeSettings.suppressReadMessages {\n        return .single(readState)"
    require(dangerous not in read_state, "old synchronous .single(readState) Ghost shortcut is still present")

    print("=== Verify deleted-message hooks ===", flush=True)
    state_utils = (telegram / "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift").read_text(encoding="utf-8")
    require(state_utils.count("AyuRuntimeSettings.markDeletedGlobalIds") >= 1, "global deleted-message hook missing")
    require(state_utils.count("AyuRuntimeSettings.markDeletedMessageIds") >= 2, "channel deleted-message hooks missing")
    require("AyuRuntimeSettings.keepDeletedMessages" in state_utils, "deleted preservation guard missing")

    print("=== Verify profile field cache ===", flush=True)
    profile = (peer_info_root / "PeerInfoProfileItems.swift").read_text(encoding="utf-8")
    for needle in (
        "AYU_IOS_PROFILE_CACHE_v0_3",
        "user.phone ?? ayuCachedProfile.phone",
        "user.addressName ?? ayuCachedProfile.username",
        "ayuCachedProfile.note",
    ):
        require(needle in profile, f"profile cache hook missing: {needle}")

    cache_payload = (peer_info_root / "AyuProfileFieldCache.swift").read_text(encoding="utf-8")
    require("var phone: String? = nil" in cache_payload, "profile cache Codable defaults missing")
    require("var username: String? = nil" in cache_payload, "profile cache Codable username default missing")
    require("var note: String? = nil" in cache_payload, "profile cache Codable note default missing")
    require("String(peerId.toInt64())" in cache_payload, "profile cache uses an unsafe/internal PeerId key path")

    print("=== Verify all patch markers ===", flush=True)
    marker_files = (
        "submodules/TelegramCore/Sources/State/ManagedAccountPresence.swift",
        "submodules/TelegramCore/Sources/State/ManagedLocalInputActivities.swift",
        "submodules/TelegramCore/Sources/State/SynchronizePeerReadState.swift",
        "submodules/TelegramCore/Sources/State/ManagedSynchronizeViewStoriesOperations.swift",
        "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift",
        "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift",
        "submodules/TelegramUI/Components/Chat/ChatMessageDateAndStatusNode/Sources/StringForMessageTimestampStatus.swift",
        "submodules/TelegramUI/Components/Chat/ChatMessageDateAndStatusNode/Sources/ChatMessageDateAndStatusNode.swift",
        "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoSettingsItems.swift",
        "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoData.swift",
    )
    for relative in marker_files:
        text = (telegram / relative).read_text(encoding="utf-8")
        require("AYU_IOS_PATCH_v0_3" in text, f"patch marker missing in {relative}")
        print(f"OK: {relative}")

    settings_controller = (peer_info_root / "AyuSettingsController.swift").read_text(encoding="utf-8")
    require("func ayuSettingsController(context: AccountContext)" in settings_controller, "Ayu settings controller entrypoint missing")
    ghost_last_seen = (telegram / "submodules/TelegramCore/Sources/State/AyuGhostLastSeen.swift").read_text(encoding="utf-8")
    require("public enum AyuGhostLastSeen" in ghost_last_seen, "Ghost last-seen runtime missing")

    print("=== VERIFY SUCCESS ===", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"=== VERIFY FAILURE ===\n{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
