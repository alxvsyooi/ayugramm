# AyuGram iOS

AyuGram — воспроизводимые патчи поверх официального Telegram-iOS: Ghost, удалённые сообщения, View Once, Spy и exteraGram без замены штатных тем, обоев и Liquid Glass.

> Следующему чату Work: начни с [MASTER_HANDOFF.md](MASTER_HANDOFF.md), затем проверь актуальные PR/head SHA/CI metadata на GitHub.

## Текущее состояние

| Параметр | Значение |
|---|---|
| Репозиторий | `vorga2/Telegram-iOS-Ghost` |
| Ветка / PR | `ayu-theme-repair-v1` / `#18` |
| Telegram-iOS | `6ad963e5b62d354da79040f388ae2b9132fb17b8` |
| Последний подтверждённый feature SHA | `69269b59888baa01395022c0dad8e1f3b6ee940c` |
| Последний подтверждённый CI | run `#190`, `SUCCESS` |

## Что реализовано

### AyuGram

- Раскрываемый Ghost master switch: блокировка read receipts, story views, online и typing/activity; auto-offline, ручное одноразовое «Прочитать», отложка и короткий `0,2 s` send pulse. Master default OFF.
- Архив удалённых: отдельный viewer, realtime refresh, SQLite/files storage, peer-qualified IDs и лимит `20 000` markers.
- Удалённое сообщение в обычном чате целиком имеет alpha `0,5`: bubble, текст, reply, аватар, sticker, emoji и media; viewer остаётся непрозрачным.
- Метка удалёнки: корзина / нет / крестик / глаз. Цвет: Telegram default, gray, red, orange, pink, magenta, purple, indigo или blue.
- Безопасная навигация viewer: никакого cloud jump к удалённому ID и очистки после «Сообщение не найдено».
- View Once сохраняется автоматически; «Сжечь» создаёт durable burned-state.
- Spy сохраняет удалённые, историю правок и read dates; детали доступны из context menu.

### exteraGram → Чаты

- «Запоминать последнюю камеру» сохраняет фактическую front/back capture camera кружка, не только preview. Default OFF.

### exteraGram → Оформление

- Три независимых скругления `0...100`: список чатов, message avatars и профили users/groups/channels. Default `100` — stock circle.
- «Единое закругление» default OFF: форумы сохраняют официальную форму; ON применяет выбранное скругление.
- Preview и видимые nodes обновляются сразу.
- Список чатов: вертикальный маленький снег только в header до Search, скрытие premium status только в header, скрытие stories только в collapsed header, заголовок AyuGram / username / имя / «Чаты».
- Light theme использует чёрный снег, dark — белый; fade сверху и снизу, реализация `CAEmitterLayer` без CPU timer.
- Реальные папки аккаунта: названия+иконки / только названия / только иконки; unread pills можно скрыть.

### Branding

- Display name `AyuGram`.
- Фиолетовая иконка — primary и первая в stock Telegram icon picker.
- Composer background `#2B2242`, без glass/specular/shadow и белой каймы.

## Stock themes и FPS

Theme family, wallpaper, bubble palette, контраст и Liquid Glass остаются штатными Telegram. Pipeline byte-for-byte проверяет критические theme-файлы. Настройки находятся в `Atomic` snapshot; нет polling loops, display links, покадровых аллокаций и full-chat scans. Снег работает через bounded Core Animation emitter. Полный контракт: [PERFORMANCE.md](PERFORMANCE.md).

## Сборка

```bash
git clone https://github.com/TelegramMessenger/Telegram-iOS.git Telegram-iOS
cd Telegram-iOS
git checkout 6ad963e5b62d354da79040f388ae2b9132fb17b8
git submodule update --init --recursive
cd ..
python3 apply_ayu_full_stock_pipeline.py Telegram-iOS
```

GitHub Actions выполняет быстрый Ubuntu verify, затем release arm64 build на macOS 26 / Xcode 26.2. Артефакт: `AyuGram-Full-StockThemes-IPA`.
