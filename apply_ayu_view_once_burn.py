#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

MARK = "AYU_VIEW_ONCE_BURN_v0_3"


def die(message: str) -> None:
    print(f"[ayu-view-once-burn] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Append Ayu manual burn action for preserved incoming view-once media")
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.repo).expanduser().resolve()
    path = root / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"
    if not path.exists():
        die(f"missing file: {path}")

    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print(f"[ayu-view-once-burn] already patched: {path}")
        return

    anchor = """        return ContextController.Items(content: .list(actions), tip: nil)\n"""
    addition = """        // AYU_VIEW_ONCE_BURN_v0_3\n        // Preserved incoming view-once photo / voice / instant-video gets one\n        // explicit destructive escape hatch. It is appended after every stock/Ayu\n        // action, so \"Сжечь\" is always the final context-menu item.\n        if let ayuBurnMessage = messages.first,\n           ayuBurnMessage.effectivelyIncoming(context.account.peerId),\n           AyuRuntimeSettings.shouldPreserveViewOnce(message: ayuBurnMessage) {\n            if !actions.isEmpty {\n                actions.append(.separator)\n            }\n            actions.append(.action(ContextMenuActionItem(text: \"Сжечь\", textColor: .destructive, icon: { theme in\n                return generateTintedImage(image: UIImage(bundleImageName: \"Chat/Context Menu/Delete\"), color: theme.actionSheet.primaryTextColor)\n            }, action: { _, f in\n                // Arm exactly one consume operation. The existing Telegram consume\n                // path then runs unchanged, sends the normal burn/consume receipt\n                // and starts the stock local destruction flow.\n                AyuRuntimeSettings.allowNextViewOnceBurn(ayuBurnMessage.id)\n                let _ = context.engine.messages.markMessageContentAsConsumedInteractively(messageId: ayuBurnMessage.id).startStandalone()\n                f(.dismissWithoutContent)\n            })))\n        }\n\n"""

    count = text.count(anchor)
    if count != 1:
        die(f"context-menu return anchor expected exactly once, found {count}")

    path.write_text(text.replace(anchor, addition + anchor, 1), encoding="utf-8")
    print(f"[ayu-view-once-burn] patched: {path}")


if __name__ == "__main__":
    main()
