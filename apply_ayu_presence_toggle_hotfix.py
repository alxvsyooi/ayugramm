#!/usr/bin/env python3
from pathlib import Path
import sys


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_presence_toggle_hotfix.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()

    enqueue = root / "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift"
    text = enqueue.read_text(encoding="utf-8")
    anchor = "public func ayuGhostOnlinePulse(account: Account) {\n"
    helper = '''// AYU_GHOST_PRESENCE_TOGGLE_v0_3\n// Apply the effective Ghost presence immediately when the user changes the\n// master/hide-online switch. No timer/polling: exactly one status request.\npublic func ayuApplyGhostPresence(account: Account) {\n    let shouldBeOffline = AyuRuntimeSettings.suppressOnlineStatus\n    let request = account.network.request(Api.functions.account.updateStatus(offline: shouldBeOffline ? .boolTrue : .boolFalse))\n    |> `catch` { _ -> Signal<Api.Bool, NoError> in\n        return .single(.boolFalse)\n    }\n    let _ = request.start()\n    if shouldBeOffline {\n        AyuGhostLastSeen.recordNow()\n    }\n}\n\n'''
    if "AYU_GHOST_PRESENCE_TOGGLE_v0_3" not in text:
        text = one(text, anchor, helper + anchor, "presence helper")
    enqueue.write_text(text, encoding="utf-8")

    settings = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift"
    text = settings.read_text(encoding="utf-8")
    old = '''        updateBool: { option, value in\n            AyuRuntimeSettings.set(option, value: value)\n            if value {\n                switch option {\n                case .master, .hideOnline:\n                    if AyuRuntimeSettings.suppressOnlineStatus {\n                        AyuGhostLastSeen.recordNow()\n                    }\n                default:\n                    break\n                }\n            }\n            bump()\n        },\n'''
    new = '''        updateBool: { option, value in\n            AyuRuntimeSettings.set(option, value: value)\n            switch option {\n            case .master, .hideOnline:\n                // Make presence match the new Ghost state immediately. Enabling\n                // Ghost+hide-online sends offline; disabling it sends online.\n                ayuApplyGhostPresence(account: context.account)\n            default:\n                break\n            }\n            bump()\n        },\n'''
    if "ayuApplyGhostPresence(account: context.account)" not in text:
        text = one(text, old, new, "settings toggle presence")
    settings.write_text(text, encoding="utf-8")

    print("[ayu-presence-toggle] Ghost presence now applies immediately on toggle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
