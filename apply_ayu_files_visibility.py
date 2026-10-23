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
        print("usage: apply_ayu_files_visibility.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()

    # The Files app shows an app's Documents directory as a top-level folder
    # named after CFBundleDisplayName. Make that folder explicitly AyuGram and
    # enable file sharing/open-in-place so it appears under “On My iPhone”.
    plist = root / "Telegram/Telegram-iOS/InfoBazel.plist"
    text = plist.read_text(encoding="utf-8")
    text = one(
        text,
        "\t<key>CFBundleDisplayName</key>\n\t<string>${APP_NAME}</string>\n",
        "\t<key>CFBundleDisplayName</key>\n\t<string>AyuGram</string>\n",
        "AyuGram display name",
    )
    text = one(
        text,
        "\t<key>UIFileSharingEnabled</key>\n\t<false/>\n",
        "\t<key>UIFileSharingEnabled</key>\n\t<true/>\n\t<key>LSSupportsOpeningDocumentsInPlace</key>\n\t<true/>\n",
        "Files sharing",
    )
    plist.write_text(text, encoding="utf-8")

    # apply_ayu_deleted_archive.py runs before this patch and creates an extra
    # Documents/AyuGram layer. Once Documents itself is exposed as the AyuGram
    # folder in Files, store our archive directly at Documents root to avoid
    # “AyuGram/AyuGram”.
    manager = root / "submodules/TelegramCore/Sources/State/AccountStateManager.swift"
    text = manager.read_text(encoding="utf-8")
    text = one(
        text,
        '        let root = documents.appendingPathComponent("AyuGram", isDirectory: true)\n',
        '        let root = documents\n',
        "Documents root",
    )
    manager.write_text(text, encoding="utf-8")

    print("[ayu-files] Files/On My iPhone/AyuGram enabled; archive stored at Documents root")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
