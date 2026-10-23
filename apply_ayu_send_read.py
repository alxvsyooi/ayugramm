#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

MARK = "AYU_SEND_READ_v0_3"


def die(message: str) -> None:
    print(f"[ayu-send-read] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        die(f"{label}: expected exactly once, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read the current peer on send and pulse online for explicit Read")
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.repo).expanduser().resolve()
    enqueue_path = root / "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift"
    menu_path = root / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"
    for path in (enqueue_path, menu_path):
        if not path.exists():
            die(f"missing file: {path}")

    text = enqueue_path.read_text(encoding="utf-8")
    if MARK not in text:
        anchor = "public func enqueueMessages(account: Account, peerId: PeerId, messages: [EnqueueMessage]) -> Signal<[MessageId?], NoError> {\n    ayuSendOnlinePulse(account: account)\n"
        if text.count(anchor) != 1:
            die(f"enqueue anchor expected exactly once, found {text.count(anchor)}")

        helper = r'''
// AYU_SEND_READ_v0_3: sending is an explicit interaction, so while Ghost is on
// we read the current peer even if passive read receipts are suppressed.
// One Postbox transaction per send action; no timer, polling or history scan.
private func ayuReadPeerOnSend(account: Account, peerId: PeerId) {
    guard AyuRuntimeSettings.snapshot.master else {
        return
    }

    let _ = account.postbox.transaction { transaction -> Void in
        guard let index = transaction.getTopPeerMessageIndex(peerId: peerId) else {
            return
        }

        AyuRuntimeSettings.allowNextRead(peerId: peerId)
        _internal_applyMaxReadIndexInteractively(
            transaction: transaction,
            stateManager: account.stateManager,
            index: index
        )
    }.start()
}

'''
        replacement = helper + "public func enqueueMessages(account: Account, peerId: PeerId, messages: [EnqueueMessage]) -> Signal<[MessageId?], NoError> {\n    ayuSendOnlinePulse(account: account)\n    ayuReadPeerOnSend(account: account, peerId: peerId)\n"
        text = text.replace(anchor, replacement, 1)

    # Export the existing 200 ms pulse helper so the explicit context-menu Read
    # action can reuse exactly the same presence behavior as sending.
    if "public func ayuGhostOnlinePulse(account: Account)" not in text:
        text = replace_once(
            text,
            "private func ayuSendOnlinePulse(account: Account) {",
            "public func ayuGhostOnlinePulse(account: Account) {",
            "pulse helper visibility",
        )
        text = replace_once(
            text,
            "    ayuSendOnlinePulse(account: account)\n",
            "    ayuGhostOnlinePulse(account: account)\n",
            "send pulse call",
        )

    enqueue_path.write_text(text, encoding="utf-8")

    menu = menu_path.read_text(encoding="utf-8")
    if "AYU_MANUAL_READ_PULSE_v0_3" not in menu:
        old = """                AyuRuntimeSettings.allowNextRead(peerId: ayuMessage.id.peerId)\n                let _ = context.engine.messages.applyMaxReadIndexInteractively(index: ayuMessage.index).startStandalone()\n"""
        new = """                // AYU_MANUAL_READ_PULSE_v0_3: explicit Read briefly uses\n                // the same 200 ms online pulse as sending, then Ghost returns offline.\n                AyuRuntimeSettings.allowNextRead(peerId: ayuMessage.id.peerId)\n                ayuGhostOnlinePulse(account: context.account)\n                let _ = context.engine.messages.applyMaxReadIndexInteractively(index: ayuMessage.index).startStandalone()\n"""
        menu = replace_once(menu, old, new, "manual Read action")
        menu_path.write_text(menu, encoding="utf-8")

    print("[ayu-send-read] current chat read + manual Read pulse patched")


if __name__ == "__main__":
    main()
