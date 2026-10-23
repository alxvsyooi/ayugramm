#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

MARK = "AYU_MANUAL_READ_FIX_v0_3"


def die(message: str) -> None:
    print(f"[ayu-manual-read] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Keep the Ayu manual-read allowance until an actual push sync")
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.repo).expanduser().resolve()
    path = root / "submodules/TelegramCore/Sources/State/SynchronizePeerReadState.swift"
    if not path.exists():
        die(f"missing file: {path}")

    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print(f"[ayu-manual-read] already patched: {path}")
        return

    old = """    // A manual allowance is single-use: this synchronization is allowed through,
    // then Ghost immediately resumes suppressing future read receipts.
    AyuRuntimeSettings.consumeManualReadAllowance(peerId: peerId)

    var signal: Signal<Never, PeerReadStateValidationError> = .complete()
"""
    new = """    // AYU_MANUAL_READ_FIX_v0_3
    // A validate-only synchronization must not consume the one-shot allowance.
    // Otherwise Telegram can validate first, consume the bypass, and then the
    // actual push is suppressed by Ghost, making the \"Прочитать\" action appear
    // to work locally while never sending the read receipt.
    if push {
        AyuRuntimeSettings.consumeManualReadAllowance(peerId: peerId)
    }

    var signal: Signal<Never, PeerReadStateValidationError> = .complete()
"""

    count = text.count(old)
    if count != 1:
        die(f"manual-read anchor expected exactly once, found {count}")

    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"[ayu-manual-read] patched: {path}")


if __name__ == "__main__":
    main()
