#!/usr/bin/env python3
from pathlib import Path
import sys


def one(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {n}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_behavior_anchor_compat.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    runtime = root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift"
    text = runtime.read_text(encoding="utf-8")

    # apply_ayu_behavior_hotfix.py owns the final Burn/deleted timestamp decorator.
    # UI v2 previously rewrote the same function first, so normalize just this
    # function back to the stable anchor expected by the behavior hotfix.
    ui_v2 = '''    public static func decorateTimestamp(_ text: String, messageId: MessageId) -> String {\n        guard showDeletedMarker && isDeleted(messageId) else {\n            return text\n        }\n        registerDeletedMessageId(messageId)\n        if isInDeletedViewer(messageId) {\n            return "🗑 \\(text)"\n        }\n        let marker = deletedMarkerPrefix\n        guard !marker.isEmpty else {\n            return text\n        }\n        return "\\(marker) \\(text)"\n    }\n'''
    stable = '''    public static func decorateTimestamp(_ text: String, messageId: MessageId) -> String {\n        guard showDeletedMarker && isDeleted(messageId) else {\n            return text\n        }\n        registerDeletedMessageId(messageId)\n        return "\\(deletedMarkerPrefix) \\(text)"\n    }\n'''

    if 'result = "🔥 \\(result)"' not in text and ui_v2 in text:
        text = one(text, ui_v2, stable, "timestamp decorator compatibility")

    runtime.write_text(text, encoding="utf-8")
    print("[ayu-behavior-compat] timestamp anchor normalized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
