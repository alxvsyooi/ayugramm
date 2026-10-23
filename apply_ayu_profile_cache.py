#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

MARK = "AYU_IOS_PROFILE_CACHE_v0_3"


def die(message: str) -> None:
    print(f"[ayu-profile-cache] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def backup(path: Path) -> None:
    dst = path.with_suffix(path.suffix + ".ayu-profile-cache.bak")
    if not dst.exists():
        shutil.copy2(path, dst)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        die(f"anchor '{label}' expected exactly once, found {count}")
    return text.replace(old, new, 1)


def patch_profile_items(text: str) -> str:
    anchor = """        let ItemCommunity = 10000\n        \n"""
    injected = """        let ItemCommunity = 10000\n\n        // AYU_IOS_PROFILE_CACHE_v0_3: remember only values Telegram has already shown locally.\n        // Telegram can keep these fields as non-nil empty strings after privacy/block updates,\n        // so normalize empty values to nil before caching and before choosing the display value.\n        let ayuServerPhone = user.phone.flatMap { value -> String? in\n            return value.isEmpty ? nil : value\n        }\n        let ayuServerUsername = user.addressName.flatMap { value -> String? in\n            return value.isEmpty ? nil : value\n        }\n        let ayuCurrentNote = (data.cachedData as? CachedUserData)?.note?.text\n        AyuProfileFieldCache.remember(peerId: user.id, phone: ayuServerPhone, username: ayuServerUsername, note: ayuCurrentNote)\n        let ayuCachedProfile = AyuProfileFieldCache.value(peerId: user.id)\n        let ayuDisplayPhone = ayuServerPhone ?? ayuCachedProfile.phone\n        let ayuDisplayUsername = ayuServerUsername ?? ayuCachedProfile.username\n        \n"""
    text = replace_once(text, anchor, injected, "profile-cache-init")

    text = replace_once(
        text,
        "        if let phone = user.phone {\n",
        "        if let phone = ayuDisplayPhone {\n",
        "profile-cache-phone",
    )
    text = replace_once(
        text,
        "        if let mainUsername = user.addressName {\n",
        "        if let mainUsername = ayuDisplayUsername {\n",
        "profile-cache-username",
    )

    old_has_note = """            var hasNote = false\n            if let note = cachedData.note, !note.text.isEmpty {\n                hasNote = true\n            }\n"""
    new_has_note = """            let ayuNoteText: String?\n            if let note = cachedData.note, !note.text.isEmpty {\n                ayuNoteText = note.text\n            } else {\n                ayuNoteText = ayuCachedProfile.note\n            }\n            let hasNote = !(ayuNoteText ?? "").isEmpty\n"""
    text = replace_once(text, old_has_note, new_has_note, "profile-cache-note-flag")

    old_note = """                if let note = cachedData.note, !note.text.isEmpty {\n                    var entities = note.entities\n                    if context.isPremium {\n                        entities = generateTextEntities(note.text, enabledTypes: [.mention, .hashtag, .allUrl], currentEntities: entities)\n                    }\n                    items[currentPeerInfoSection]!.append(PeerInfoScreenLabeledValueItem(id: ItemNote, label: presentationData.strings.PeerInfo_Notes, rightLabel: presentationData.strings.PeerInfo_NotesInfo, text: note.text, entities: entities, handleSpoilers: true, textColor: .primary, textBehavior: .multiLine(maxLines: 100, enabledEntities: []), action: nil, linkItemAction: bioLinkAction, button: nil, contextAction: noteContextAction, requestLayout: { animated in\n                        interaction.requestLayout(animated)\n                    }))\n                }\n"""
    new_note = """                if let note = cachedData.note, !note.text.isEmpty {\n                    var entities = note.entities\n                    if context.isPremium {\n                        entities = generateTextEntities(note.text, enabledTypes: [.mention, .hashtag, .allUrl], currentEntities: entities)\n                    }\n                    items[currentPeerInfoSection]!.append(PeerInfoScreenLabeledValueItem(id: ItemNote, label: presentationData.strings.PeerInfo_Notes, rightLabel: presentationData.strings.PeerInfo_NotesInfo, text: note.text, entities: entities, handleSpoilers: true, textColor: .primary, textBehavior: .multiLine(maxLines: 100, enabledEntities: []), action: nil, linkItemAction: bioLinkAction, button: nil, contextAction: noteContextAction, requestLayout: { animated in\n                        interaction.requestLayout(animated)\n                    }))\n                } else if let noteText = ayuCachedProfile.note, !noteText.isEmpty {\n                    items[currentPeerInfoSection]!.append(PeerInfoScreenLabeledValueItem(id: ItemNote, label: presentationData.strings.PeerInfo_Notes, rightLabel: presentationData.strings.PeerInfo_NotesInfo, text: noteText, entities: [], handleSpoilers: false, textColor: .primary, textBehavior: .multiLine(maxLines: 100, enabledEntities: []), action: nil, linkItemAction: bioLinkAction, button: nil, contextAction: noteContextAction, requestLayout: { animated in\n                        interaction.requestLayout(animated)\n                    }))\n                }\n"""
    text = replace_once(text, old_note, new_note, "profile-cache-note-row")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Ayu v0.3 last-known profile field cache")
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.repo).expanduser().resolve()
    peer_info = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen"
    if not peer_info.exists():
        die(f"'{root}' is not TelegramMessenger/Telegram-iOS")

    here = Path(__file__).resolve().parent
    source = here / "payload" / "AyuProfileFieldCache.swift"
    target = peer_info / "Sources/AyuProfileFieldCache.swift"
    if not source.exists():
        die(f"missing payload: {source}")
    if not target.exists() or target.read_text(encoding="utf-8") != source.read_text(encoding="utf-8"):
        if target.exists():
            backup(target)
        shutil.copy2(source, target)
        print(f"[ayu-profile-cache] installed: {target}")

    profile_items = peer_info / "Sources/PeerInfoProfileItems.swift"
    text = profile_items.read_text(encoding="utf-8")
    if MARK in text:
        print(f"[ayu-profile-cache] already patched: {profile_items}")
        return
    patched = patch_profile_items(text)
    backup(profile_items)
    profile_items.write_text(patched, encoding="utf-8")
    print(f"[ayu-profile-cache] patched: {profile_items}")


if __name__ == "__main__":
    main()
