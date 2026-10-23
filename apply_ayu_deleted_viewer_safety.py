#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


MARK = "AYU_DELETED_VIEWER_SAFETY_v1"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_deleted_viewer_safety.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift"
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print(f"[ayu-deleted-viewer] already patched: {path}")
        return 0

    old_button = """        if incoming, case let .customChatContents(contents) = item.associatedData.subject, case .hashTagSearch = contents.kind {
            needsShareButton = true
"""
    new_button = f"""        // {MARK}
        // The deleted viewer reuses hashtag-search rendering, whose round arrow
        // normally force-loads the original message from Telegram's cloud. A
        // deleted id cannot exist there; that load also reconciles it out of
        // Postbox. Hide the destructive navigation affordance for Ayu-marked
        // messages while leaving real hashtag search byte-for-byte stock.
        if incoming, case let .customChatContents(contents) = item.associatedData.subject, case .hashTagSearch = contents.kind, !AyuRuntimeSettings.isDeleted(item.message.id) {{
            needsShareButton = true
"""
    text = one(text, old_button, new_button, "deleted viewer navigation button")

    old_action = """            } else if case let .customChatContents(contents) = item.associatedData.subject, case .hashTagSearch = contents.kind {
                item.controllerInteraction.navigateToMessage(item.content.firstMessage.id, item.content.firstMessage.id, NavigateToMessageParams(timestamp: nil, quote: nil, forceNew: true))
"""
    new_action = """            } else if case let .customChatContents(contents) = item.associatedData.subject, case .hashTagSearch = contents.kind {
                if !AyuRuntimeSettings.isDeleted(item.content.firstMessage.id) {
                    item.controllerInteraction.navigateToMessage(item.content.firstMessage.id, item.content.firstMessage.id, NavigateToMessageParams(timestamp: nil, quote: nil, forceNew: true))
                }
"""
    text = one(text, old_action, new_action, "deleted viewer navigation action")

    path.write_text(text, encoding="utf-8")
    print("[ayu-deleted-viewer] cloud navigation disabled for archived deleted messages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
