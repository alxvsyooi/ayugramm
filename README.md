# ayugramm

AyuGram iOS: патчи поверх официального Telegram-iOS (перенесено из `vorga2/Telegram-iOS-Ghost`, ветка `ayu-theme-repair-v1`, коммит `f3108c1`). Подробности — `MASTER_HANDOFF.md`.

## Сборка IPA

1. Settings → Secrets and variables → Actions: добавить `TG_API_ID` и `TG_API_HASH` (my.telegram.org).
2. Actions → «AyuGram IPA» → Run workflow (выбрать ветку).
3. После сборки скачать артефакт `AyuGram-Full-StockThemes-IPA`.

IPA подписан тестовыми сертификатами Telegram — для установки переподписать (Sideloadly / AltStore / TrollStore).

На каждый push запускается только быстрая проверка патчей (`verify`, Ubuntu); сборка на macOS — только вручную.
