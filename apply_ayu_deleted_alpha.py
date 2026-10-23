#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


MARK = "AYU_DELETED_MESSAGE_ALPHA_v1"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_deleted_alpha.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramUI/Components/Chat/ChatMessageItemImpl/Sources/ChatMessageItemImpl.swift"
    text = path.read_text(encoding="utf-8")

    if MARK not in text:
        old_create = (
            "            let node = (viewClassName as! ChatMessageItemView.Type).init(rotated: self.controllerInteraction.chatIsRotated)\n"
            "            node.setupItem(self, synchronousLoad: synchronousLoads)\n"
            "            \n"
            "            let nodeLayout = node.asyncLayout()\n"
        )
        new_create = f"""            let node = (viewClassName as! ChatMessageItemView.Type).init(rotated: self.controllerInteraction.chatIsRotated)
            node.setupItem(self, synchronousLoad: synchronousLoads)
            // {MARK}: final-node opacity only. Theme colors, bubble backgrounds,
            // replies, links and native glass rendering remain stock Telegram.
            let ayuDeletedAlpha: CGFloat = AyuRuntimeSettings.isDeleted(self.message.id) && !AyuRuntimeSettings.isInDeletedViewer(self.message.id) ? 0.5 : 1.0
            node.alpha = ayuDeletedAlpha

            let nodeLayout = node.asyncLayout()
"""
        new_create = new_create.replace("node.alpha = ayuDeletedAlpha\n\n", "node.alpha = ayuDeletedAlpha\n            \n")
        text = one(text, old_create, new_create, "deleted alpha create")

        old_update = (
            "            if let nodeValue = node() as? ChatMessageItemView {\n"
            "                nodeValue.setupItem(self, synchronousLoad: false)\n"
            "                \n"
            "                let nodeLayout = nodeValue.asyncLayout()\n"
        )
        new_update = """            if let nodeValue = node() as? ChatMessageItemView {
                nodeValue.setupItem(self, synchronousLoad: false)
                let ayuDeletedAlpha: CGFloat = AyuRuntimeSettings.isDeleted(self.message.id) && !AyuRuntimeSettings.isInDeletedViewer(self.message.id) ? 0.5 : 1.0
                nodeValue.alpha = ayuDeletedAlpha

                let nodeLayout = nodeValue.asyncLayout()
"""
        new_update = new_update.replace("nodeValue.alpha = ayuDeletedAlpha\n\n", "nodeValue.alpha = ayuDeletedAlpha\n                \n")
        text = one(text, old_update, new_update, "deleted alpha update")
        path.write_text(text, encoding="utf-8")

    verify = path.read_text(encoding="utf-8")
    if MARK not in verify or verify.count("? 0.5 : 1.0") != 2:
        raise RuntimeError("deleted-message 0.5 alpha is incomplete")
    if "backgroundColor" in verify[verify.find(MARK) : verify.find(MARK) + 700]:
        raise RuntimeError("deleted alpha patch must not alter theme backgrounds")

    print("[ayu-deleted-alpha] deleted messages use final-node alpha 0.5; viewer stays opaque")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
