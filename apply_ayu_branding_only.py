#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

MAIN_MARK = "AYU_GHOST_ONLY_MAIN_BRANDING_v0_3"
CALLKIT_MARK = "AYU_GHOST_ONLY_CALLKIT_BRANDING_v0_3"
CHAT_MARK = "AYU_GHOST_ONLY_CHATLIST_BRANDING_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_branding_only.py <Telegram-iOS root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()

    build_path = root / "Telegram/BUILD"
    build = build_path.read_text(encoding="utf-8")
    if MAIN_MARK not in build:
        old = '''    <key>CFBundleDisplayName</key>\n    <string>Telegram</string>\n    <key>CFBundleIdentifier</key>\n    <string>{telegram_bundle_id}</string>\n    <key>CFBundleName</key>\n    <string>Telegram</string>\n'''
        new = f'''    <!-- {MAIN_MARK} -->\n    <key>CFBundleDisplayName</key>\n    <string>AyuGram</string>\n    <key>CFBundleIdentifier</key>\n    <string>{{telegram_bundle_id}}</string>\n    <key>CFBundleName</key>\n    <string>AyuGram</string>\n'''
        build = one(build, old, new, "main bundle branding")
        build = build.replace("    <key>CFBundleDisplayName</key>\n    <string>Telegram</string>\n", "    <key>CFBundleDisplayName</key>\n    <string>AyuGram</string>\n")
        build = build.replace("    <key>CFBundleName</key>\n    <string>Telegram</string>\n", "    <key>CFBundleName</key>\n    <string>AyuGram</string>\n")
        build_path.write_text(build, encoding="utf-8")

    for relative in ("Telegram/Telegram-iOS/InfoBazel.plist", "Telegram/Telegram-iOS/Info.plist"):
        path = root / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        text = text.replace("<string>${APP_NAME}</string>", "<string>AyuGram</string>")
        text = text.replace("<string>$(PRODUCT_NAME)</string>", "<string>AyuGram</string>")
        text = text.replace("<string>${PRODUCT_NAME}</string>", "<string>AyuGram</string>")
        path.write_text(text, encoding="utf-8")

    localized_plists = list((root / "Telegram/Telegram-iOS").glob("*.lproj/InfoPlist.strings"))
    if not localized_plists:
        raise RuntimeError("localized InfoPlist.strings files not found")
    for path in localized_plists:
        text = path.read_text(encoding="utf-8")
        display_pattern = re.compile(r'^\s*"CFBundleDisplayName"\s*=\s*"[^"]*"\s*;\s*$', re.MULTILINE)
        name_pattern = re.compile(r'^\s*"CFBundleName"\s*=\s*"[^"]*"\s*;\s*$', re.MULTILINE)
        text = display_pattern.sub('"CFBundleDisplayName" = "AyuGram";', text, count=1) if display_pattern.search(text) else '"CFBundleDisplayName" = "AyuGram";\n' + text
        text = name_pattern.sub('"CFBundleName" = "AyuGram";', text, count=1) if name_pattern.search(text) else '"CFBundleName" = "AyuGram";\n' + text
        path.write_text(text, encoding="utf-8")

    callkit_path = root / "submodules/TelegramCallsUI/Sources/CallKitIntegration.swift"
    callkit = callkit_path.read_text(encoding="utf-8")
    if CALLKIT_MARK not in callkit:
        callkit = one(callkit, '        let providerConfiguration = CXProviderConfiguration(localizedName: "Telegram")\n', f'        // {CALLKIT_MARK}\n        let providerConfiguration = CXProviderConfiguration(localizedName: "AyuGram")\n', "CallKit branding")
        callkit_path.write_text(callkit, encoding="utf-8")

    chat_path = root / "submodules/ChatListUI/Sources/ChatListController.swift"
    chat = chat_path.read_text(encoding="utf-8")
    if CHAT_MARK not in chat:
        chat = one(chat, '''            if groupId == .root {\n                title = self.presentationData.strings.DialogList_Title\n            } else {\n''', f'''            if groupId == .root {{\n                // {CHAT_MARK}\n                title = "AyuGram"\n            }} else {{\n''', "initial root title")
        chat = one(chat, '''            if groupId == .root {\n                defaultTitle = presentationData.strings.DialogList_Title\n            } else {\n''', '''            if groupId == .root {\n                defaultTitle = "AyuGram"\n            } else {\n''', "live root title")
        chat = one(chat, '''            self.chatListTitle = titleContent\n''', '''            if case .chatList(.root) = self.location, !stateAndFilterId.state.editing, !titleContent.activity {\n                titleContent.text = AyuRuntimeSettings.chatListHeaderTitle\n                titleContent.peerStatus = AyuRuntimeSettings.chatListHideStatus ? nil : peerStatus\n            }\n            self.chatListTitle = titleContent\n''', "final visible root title")
        chat_path.write_text(chat, encoding="utf-8")

    print("[ayu-branding-only] AyuGram names installed; theme and Liquid Glass untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
