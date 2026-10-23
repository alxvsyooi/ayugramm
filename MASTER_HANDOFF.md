# MASTER HANDOFF — AyuGram iOS

Актуально на 2026-08-22. Это главный источник контекста для следующего чата Work.

## Инструкция следующему чату

Продолжай проект строго из этого файла. Первым действием проверь актуальный GitHub state: PR, head SHA и последний workflow run. Не считай SHA ниже вечным. После пользовательского verify не читай CI logs: разрешена только проверка metadata/status/conclusion, если пользователь не попросил иначе.

## GitHub state на момент handoff

| Поле | Значение |
|---|---|
| Repository | `vorga2/Telegram-iOS-Ghost` |
| PR | `#18` |
| PR title | `CI: build Ayu ThemeRepair V1 IPA` |
| Head branch | `ayu-theme-repair-v1` |
| Последний feature head до docs | `6e6b69d` (Essentials + v6 night-slot repair) |
| Последний подтверждённый run | id `32643889106`, `SUCCESS` (verify + build_ipa) |
| Pinned Telegram-iOS | `6ad963e5b62d354da79040f388ae2b9132fb17b8` |
| IPA artifact | `AyuGram-Full-StockThemes-IPA` |

После коммита с этим handoff head/run изменятся — всегда перепроверь GitHub.

## Архитектура

Репозиторий хранит воспроизводимые patchers, а не fork Telegram целиком. CI клонирует pinned upstream и применяет `apply_ayu_full_stock_pipeline.py`. Не запускай patchers в случайном порядке: поздние слои рассчитаны на anchors ранних.

Порядок слоёв:

1. базовый Ayu UI/runtime и profile cache;
2. View Once + durable/burn;
3. stock UI guard;
4. deleted alpha/viewer/background/marker/realtime;
5. manual read/send-read/behavior compatibility;
6. deleted archive и Files visibility;
7. presence hotfix, settings, Spy, camera/Ghost;
8. avatar rounding (list/chat/profile);
9. chat-list appearance и folders;
10. Spy edit/read/details/content dates;
11. branding, app icon и theme integrity;
12. exteraGram Essentials (числа/секунды/Zaglo/профиль-ID), peer-id scope fix.

ThemeRepair v6: ночной слот чинится один раз по фактическому рендеру
(`makePresentationTheme(...).overallDarkAppearance`), а не по заявленной базе —
день-базированные тёмные кастомы (типа «геймерской») теперь занимают night slot.
Ключ recovery: `themeStockRoutingRecovery.v6`.

## Карта функций и defaults

### AyuGram → Режим Призрака

Раскрываемая строка с анимированной стрелкой и master switch. Master default OFF.

- Не читать сообщения.
- Не отмечать просмотр историй.
- Скрывать онлайн.
- Скрывать «печатает…» и другие activity.
- Автоматически офлайн.
- Читать при действиях.
- Использовать отложку.

Ручное «Прочитать» даёт allowance одной штатной read-operation, не меняет Postbox вручную. При Ghost+hideOnline отправка делает короткий online pulse `0,2 s`; отдельного toggle для pulse нет.

### Удалённые сообщения

- Сохранение, отдельный viewer, realtime raw+final refresh.
- Alpha `0,5` применяется ко всему normal-chat message node: bubble, текст, reply, аватар, sticker, emoji, media. В viewer архив непрозрачный.
- Метка: корзина / без значка / крестик / глаз.
- Цвет: Telegram default / gray / red / orange / pink / magenta / purple / indigo / blue.
- В dark theme кастомный фон имеет effective alpha `0,5`; Telegram mode использует родные incoming/outgoing colors.
- Storage: peer-qualified IDs, максимум `20 000` markers, SQLite + `Documents/AyuGram`.
- Viewer не должен выполнять cloud jump к удалённому ID и не должен очищать запись после «Сообщение не найдено».

### View Once и Spy

View Once сохраняется всегда. «Сжечь» удаляет копию и создаёт durable burned-state.

Spy сохраняет удалённые, историю правок и даты прочтения. Edit history: incoming и own messages в PM/group/channel. Read dates: PM/basic group/supergroup; broadcast исключён. Детали доступны из message context menu с DB fallback.

### exteraGram → Чаты

`Камера → Запоминать последнюю камеру`, default OFF. Сохраняется реальный capture route кружка front/back и применяется при следующем фактическом старте; одного preview state недостаточно.

### exteraGram → Оформление

Три независимых скругления `0...100`, default `100`:

- список чатов — только строки списка;
- аватарки сообщений в чате;
- профили users/groups/channels.

Все preview и видимые nodes обновляются сразу. `Единое закругление` default OFF: forum avatar остаётся stock; ON применяет общее скругление форуму.

Список чатов:

- `Принудительный снег`: вертикальное падение, маленькие редкие частицы, только header около `54 pt`, заканчивается до Search/folders, fade сверху/снизу, light=black, dark=white; `CAEmitterLayer`, без timer/display link.
- `Скрыть статус`: premium emoji/status скрывается только из верхнего header.
- `Скрыть истории`: stories скрыты только в collapsed/mini header и видны при раскрытии.
- `Текст в заголовке`: AyuGram default / username без `@` / Telegram first name / «Чаты». Actual header и preview меняются сразу.

Папки:

- Preview использует реальные folders аккаунта и обновляется live.
- Названия+иконки default / только названия / только иконки.
- Notification counter default ON; OFF скрывает unread pills в preview и реальном tab strip.
- Folder icons синхронизируются с аккаунтом.

### Branding

Display name `AyuGram`. Фиолетовая иконка — primary и первый вариант Telegram icon picker. Исходник обрезан без белых линий; Composer background `#2B2242`, glass/specular/shadow выключены.

## ThemeRepair: точная причина и запреты

Пропадающие тексты, ссылки, reply backgrounds, неправильные bubbles, блеклые профили и сломанный Liquid Glass возникали из-за вмешательства Ayu в глобальную theme/presentation routing и UIKit trait propagation. Нельзя возвращать принудительный `overrideUserInterfaceStyle`, глобальные alpha/color transforms, подмену wallpaper/theme family или правки native glass.

Pipeline сохраняет эти файлы byte-for-byte от pinned Telegram:

- `ThemeSettingsController.swift`
- `NativeWindowHostView.swift`
- `LiquidLensView.swift`
- `GlassBackgroundComponent.swift`
- `ChatMessageReplyInfoNode.swift`
- `ChatPinnedMessageTitlePanelNode.swift`
- `PeerInfoGiftsPaneNode.swift`
- `PresentationData.swift`

`apply_ayu_theme_integrity.py` допускает только узкую legacy alpha-zero compatibility и восстановление stock routing. Preferred Night Theme полностью принадлежит stock Telegram и не должен сбрасываться при повторном выборе dark theme.

## Важные прошлые ошибки

- Swift 6 ругался на лишний `#available(iOS 12)` в `NativeWindowHostView` — файл возвращён stock.
- Debug `TelegramCore` с Xcode 26.2 падал на deprecated `SCNetworkReachability*` + `-Werror`; эталон — release workflow.
- `AyuDeletedMarkerColor.telegram` отсутствовал — enum и UI options должны совпадать.
- `ayuSpySettingsController` был вне scope — controllers должны быть объявлены и включены в target.
- `override init()` у `AyuAvatarRoundingItem` не был designated override.
- Submodule RPC/DNS/timeouts — инфраструктурная сеть; не переписывать feature code из-за этого.

## Performance contract

- Settings snapshot в `Atomic`; без `UserDefaults` reads в hot path.
- Без polling, per-frame work и full-chat scans.
- Deleted lookup O(1), только visible nodes.
- Snow — bounded Core Animation emitter, ориентир не более ~20–25 живых частиц.
- Avatar rounding — локальный clipping/corner radius и event-driven refresh.
- Theme/wallpaper/glass — stock.

Количество настроек само по себе FPS не снижает. Нулевой измеримый impact — цель архитектуры, но абсолютное равенство официальному Telegram можно подтвердить только Instruments на одном устройстве и сценарии.

## Verify и CI

```bash
python3 apply_ayu_full_stock_pipeline.py /path/to/clean/Telegram-iOS
```

Workflow:

1. `verify` на Ubuntu — pipeline и anchors.
2. `build_ipa` на macOS 26 / Xcode 26.2 — release arm64 Bazel.
3. Artifact `AyuGram-Full-StockThemes-IPA`.

После verify пользователь просил не читать logs. Проверять только status, conclusion, SHA и номер run.

## Порядок работы следующего чата

1. Получить PR #18 и сравнить remote head с указанным здесь.
2. Проверить последний workflow run только по metadata.
3. Работать поверх `ayu-theme-repair-v1`.
4. Перед правкой найти фактический runtime consumer: работа одного preview не считается реализацией.
5. Применить полный pipeline к чистому pinned Telegram tree.
6. Выполнить anchor/stock checks и отправить commit в PR.
7. После CI сообщить номер run и conclusion, не открывая logs.
