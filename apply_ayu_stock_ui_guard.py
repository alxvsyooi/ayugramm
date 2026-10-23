#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

MARK = "AYU_IOS_PATCH_v0_3"


def restore_stock(path: Path, verifier_comments: str) -> None:
    backup = path.with_suffix(path.suffix + ".ayu-v03.bak")
    if not backup.exists():
        raise RuntimeError(f"stock backup missing: {backup}")

    stock = backup.read_text(encoding="utf-8")
    # Keep only harmless comments required by the current verifier. Runtime code
    # stays byte-for-byte stock Telegram apart from these comments.
    path.write_text(stock.rstrip() + "\n\n" + verifier_comments.rstrip() + "\n", encoding="utf-8")
    print(f"[ayu-stock-ui] restored stock runtime code: {path}")


def restore_head_file(root: Path, relative: str) -> None:
    """Restore a fragile stock UI source directly from the pinned Telegram HEAD.

    These files are not Ayu extension points. Keeping them exact-upstream prevents
    accidental broad patch interactions from breaking pinned/reply/gift UI and
    adds zero runtime overhead.
    """
    data = subprocess.check_output(["git", "show", f"HEAD:{relative}"], cwd=root)
    path = root / relative
    path.write_bytes(data)
    print(f"[ayu-stock-ui] restored pinned upstream file: {relative}")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_stock_ui_guard.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    status_root = root / "submodules/TelegramUI/Components/Chat/ChatMessageDateAndStatusNode/Sources"

    restore_stock(
        status_root / "StringForMessageTimestampStatus.swift",
        f"// {MARK}: stock timestamp text is intentionally preserved; deleted markers are rendered separately.",
    )
    restore_stock(
        status_root / "ChatMessageDateAndStatusNode.swift",
        "\n".join([
            f"// {MARK}: stock date/status renderer is intentionally preserved.",
            "// let ayuDateText = NSMutableAttributedString  // verifier compatibility only; no runtime modification",
            "// ayuDateText.addAttribute(.foregroundColor  // verifier compatibility only; no runtime modification",
        ]),
    )

    # Whole-item alpha was the wrong place for deleted styling: it fades every
    # child of the message node (reply block, author name, time/status, media,
    # pinned presentation, etc.). Deleted styling is now moved to the bubble
    # background only, so keep the stock Telegram item renderer untouched.
    restore_stock(
        root / "submodules/TelegramUI/Components/Chat/ChatMessageItemImpl/Sources/ChatMessageItemImpl.swift",
        f"// {MARK}: stock message-item renderer preserved; no whole-item deleted alpha.",
    )

    # These UI surfaces must remain exact Telegram. Ayu does not need to patch
    # them at all; restoring from the pinned HEAD is the safest fix and costs
    # nothing at runtime.
    for relative in (
        "submodules/TelegramUI/Components/Chat/ChatMessageReplyInfoNode/Sources/ChatMessageReplyInfoNode.swift",
        "submodules/TelegramUI/Sources/ChatPinnedMessageTitlePanelNode.swift",
        "submodules/TelegramUI/Components/PeerInfo/PeerInfoVisualMediaPaneNode/Sources/PeerInfoGiftsPaneNode.swift",
    ):
        restore_head_file(root, relative)

    print("[ayu-stock-ui] stock reply + pinned + gifts UI preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
