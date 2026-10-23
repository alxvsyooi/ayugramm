#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PATCH_VERSION = "0.3.0"
MARK = "AYU_IOS_PATCH_v0_3"


def die(message: str) -> None:
    print(f"[ayu-v03] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def backup(path: Path) -> None:
    dst = path.with_suffix(path.suffix + ".ayu-v03.bak")
    if not dst.exists():
        shutil.copy2(path, dst)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        die(f"anchor '{label}' expected exactly once, found {count}")
    return text.replace(old, new, 1)


def replace_all_checked(text: str, old: str, new: str, label: str, minimum: int = 1) -> str:
    count = text.count(old)
    if count < minimum:
        die(f"anchor '{label}' expected at least {minimum}, found {count}")
    print(f"[ayu-v03] {label}: {count} replacement(s)")
    return text.replace(old, new)


def patch_file(path: Path, transform) -> None:
    if not path.exists():
        die(f"missing file: {path}")
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print(f"[ayu-v03] already patched: {path}")
        return
    new_text = transform(text)
    if new_text == text:
        die(f"patch produced no changes: {path}")
    backup(path)
    path.write_text(new_text, encoding="utf-8")
    print(f"[ayu-v03] patched: {path}")


def install_payload(source: Path, target: Path, label: str) -> None:
    if not source.exists():
        die(f"missing payload: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.read_text(encoding="utf-8") != source.read_text(encoding="utf-8"):
        if target.exists():
            backup(target)
        shutil.copy2(source, target)
        print(f"[ayu-v03] installed {label}: {target}")


def patch_presence(text: str) -> str:
    old = """            request = self.network.request(Api.functions.account.updateStatus(offline: .boolFalse))\n        } else {\n"""
    new = """            // AYU_IOS_PATCH_v0_3: keep Telegram's original presence state machine/timer.\n            // Only change the actual status request; this avoids the v0.2 timer/disposable surgery.\n            if AyuRuntimeSettings.suppressOnlineStatus {\n                request = self.network.request(Api.functions.account.updateStatus(offline: .boolTrue))\n            } else {\n                request = self.network.request(Api.functions.account.updateStatus(offline: .boolFalse))\n            }\n        } else {\n"""
    return replace_once(text, old, new, "presence-safe-request")


def patch_typing(text: str) -> str:
    old = """private func requestActivity(postbox: Postbox, network: Network, accountPeerId: PeerId, peerId: PeerId, threadId: Int64?, activity: PeerInputActivity?) -> Signal<Void, NoError> {\n    return postbox.transaction { transaction -> Signal<Void, NoError> in\n"""
    new = """private func requestActivity(postbox: Postbox, network: Network, accountPeerId: PeerId, peerId: PeerId, threadId: Int64?, activity: PeerInputActivity?) -> Signal<Void, NoError> {\n    // AYU_IOS_PATCH_v0_3: suppress only user-visible typing/upload activities.\n    // Keep cancel, group-call speech and emoji interaction semantics intact.\n    if AyuRuntimeSettings.suppressTypingActivities, let activity {\n        switch activity {\n        case .speakingInGroupCall, .interactingWithEmoji, .seeingEmojiInteraction:\n            break\n        default:\n            return .complete()\n        }\n    }\n\n    return postbox.transaction { transaction -> Signal<Void, NoError> in\n"""
    return replace_once(text, old, new, "typing")


def patch_read_state(text: str) -> str:
    old_low = """private func pushPeerReadState(network: Network, postbox: Postbox, stateManager: AccountStateManager, peerId: PeerId, readState: PeerReadState) -> Signal<PeerReadState, PeerReadStateValidationError> {\n    if peerId.namespace == Namespaces.Peer.SecretChat {\n"""
    new_low = """private func pushPeerReadState(network: Network, postbox: Postbox, stateManager: AccountStateManager, peerId: PeerId, readState: PeerReadState) -> Signal<PeerReadState, PeerReadStateValidationError> {\n    // AYU_IOS_PATCH_v0_3: preserve Telegram's outer synchronization/operation-log flow,\n    // but do not emit readHistory/readEncryptedHistory while Ghost is active.\n    if AyuRuntimeSettings.suppressReadMessages {\n        return .single(readState)\n    }\n\n    if peerId.namespace == Namespaces.Peer.SecretChat {\n"""
    text = replace_once(text, old_low, new_low, "read-low-level")

    old_validate = """    if validate {\n        signal = signal\n        |> then(validatePeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n"""
    new_validate = """    if validate && !AyuRuntimeSettings.suppressReadMessages {\n        // AYU_IOS_PATCH_v0_3: server validation would immediately overwrite the local ghost read.\n        signal = signal\n        |> then(validatePeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n"""
    return replace_once(text, old_validate, new_validate, "read-validation")


def patch_stories(text: str) -> str:
    old = """private func pushStoriesAreSeen(postbox: Postbox, network: Network, stateManager: AccountStateManager, peer: Peer, operation: SynchronizeViewStoriesOperation) -> Signal<Void, NoError> {\n    guard let inputPeer = apiInputPeer(peer) else {\n"""
    new = """private func pushStoriesAreSeen(postbox: Postbox, network: Network, stateManager: AccountStateManager, peer: Peer, operation: SynchronizeViewStoriesOperation) -> Signal<Void, NoError> {\n    // AYU_IOS_PATCH_v0_3: consume the local operation without sending stories.readStories.\n    if AyuRuntimeSettings.suppressStoryViews {\n        return .complete()\n    }\n\n    guard let inputPeer = apiInputPeer(peer) else {\n"""
    return replace_once(text, old, new, "story-views")


def patch_online_pulse(text: str) -> str:
    anchor = "public func enqueueMessages(account: Account, peerId: PeerId, messages: [EnqueueMessage]) -> Signal<[MessageId?], NoError> {"
    if anchor not in text:
        die("enqueueMessages anchor missing")

    helper = r'''
// AYU_IOS_PATCH_v0_3: Ayu-style 200 ms online pulse when the user sends a message.
// This bypasses ManagedAccountPresence intentionally for one tiny explicit window,
// then restores offline. It does not mutate Telegram's presence timers/state machine.
private func ayuSendOnlinePulse(account: Account) {
    guard AyuRuntimeSettings.shouldPulseOnlineOnSend else {
        return
    }

    let online = account.network.request(Api.functions.account.updateStatus(offline: .boolFalse))
    |> `catch` { _ -> Signal<Api.Bool, NoError> in
        return .single(.boolFalse)
    }
    let _ = online.start()

    Queue.mainQueue().after(0.2) {
        guard AyuRuntimeSettings.suppressOnlineStatus else {
            return
        }
        let offline = account.network.request(Api.functions.account.updateStatus(offline: .boolTrue))
        |> `catch` { _ -> Signal<Api.Bool, NoError> in
            return .single(.boolFalse)
        }
        let _ = offline.start()
        AyuGhostLastSeen.recordNow()
    }
}

'''
    text = text.replace(anchor, helper + anchor, 1)
    text = replace_once(
        text,
        anchor + "\n    let signal:",
        anchor + "\n    ayuSendOnlinePulse(account: account)\n    let signal:",
        "enqueue-pulse-call",
    )
    return text


def patch_deleted_state(text: str) -> str:
    old_global = "                updatedState.deleteMessagesWithGlobalIds(updateDeleteMessagesData.messages)"
    new_global = """                // AYU_IOS_PATCH_v0_3: keep remote-deleted cloud messages locally and remember their ids.\n                if AyuRuntimeSettings.keepDeletedMessages {\n                    AyuRuntimeSettings.markDeletedGlobalIds(updateDeleteMessagesData.messages)\n                } else {\n                    updatedState.deleteMessagesWithGlobalIds(updateDeleteMessagesData.messages)\n                }"""
    text = replace_all_checked(text, old_global, new_global, "deleted-global", minimum=2)

    old_channel = "                        updatedState.deleteMessages(messages.map({ MessageId(peerId: peerId, namespace: Namespaces.Message.Cloud, id: $0) }))"
    new_channel = """                        let ayuDeletedIds = messages.map({ MessageId(peerId: peerId, namespace: Namespaces.Message.Cloud, id: $0) })\n                        if AyuRuntimeSettings.keepDeletedMessages {\n                            AyuRuntimeSettings.markDeletedMessageIds(ayuDeletedIds)\n                        } else {\n                            updatedState.deleteMessages(ayuDeletedIds)\n                        }"""
    text = replace_all_checked(text, old_channel, new_channel, "deleted-channel-pts", minimum=2)

    old_channel_other = "                        updatedState.deleteMessages(updateDeleteChannelMessagesData.messages.map({ MessageId(peerId: peerId, namespace: Namespaces.Message.Cloud, id: $0) }))"
    new_channel_other = """                        let ayuDeletedIds = updateDeleteChannelMessagesData.messages.map({ MessageId(peerId: peerId, namespace: Namespaces.Message.Cloud, id: $0) })\n                        if AyuRuntimeSettings.keepDeletedMessages {\n                            AyuRuntimeSettings.markDeletedMessageIds(ayuDeletedIds)\n                        } else {\n                            updatedState.deleteMessages(ayuDeletedIds)\n                        }"""
    text = replace_all_checked(text, old_channel_other, new_channel_other, "deleted-channel-other", minimum=2)
    return text


def patch_timestamp(text: str) -> str:
    old = """    return dateText\n}\n"""
    if text.count(old) != 1:
        die(f"timestamp return anchor expected once, found {text.count(old)}")
    new = """    // AYU_IOS_PATCH_v0_3: a single central marker path covers text, media, files, polls, stickers, etc.\n    return AyuRuntimeSettings.decorateTimestamp(dateText, messageId: message.id)\n}\n"""
    return text.replace(old, new, 1)


def patch_status_color(text: str) -> str:
    text = replace_once(text, "            let dateColor: UIColor\n", "            var dateColor: UIColor\n", "deleted-color-var")
    anchor = """            }\n            \n            var updatedDateText = arguments.dateText\n"""
    replacement = """            }\n\n            // AYU_IOS_PATCH_v0_3: customize the deleted timestamp/marker color.\n            if AyuRuntimeSettings.isDeletedTimestampText(arguments.dateText) {\n                switch AyuDeletedMarkerColor(rawValue: AyuRuntimeSettings.snapshot.deletedMarkerColor) ?? .red {\n                case .red:\n                    dateColor = UIColor.systemRed\n                case .orange:\n                    dateColor = UIColor.systemOrange\n                case .gray:\n                    dateColor = UIColor.systemGray\n                case .purple:\n                    dateColor = UIColor.systemPurple\n                }\n            }\n            \n            var updatedDateText = arguments.dateText\n"""
    return replace_once(text, anchor, replacement, "deleted-color-anchor")


def patch_native_settings(text: str) -> str:
    username_anchor = """    if let peer = data.peer, (peer.addressName ?? "").isEmpty {\n"""
    ayu_row = """    // AYU_IOS_PATCH_v0_3: native AyuGram entry directly under profile photo controls.\n    items[.edit]!.append(PeerInfoScreenDisclosureItem(id: 90, text: "AyuGram", icon: PresentationResourcesSettings.security, action: {\n        guard let controller = interaction.getController() else {\n            return\n        }\n        controller.push(ayuSettingsController(context: context))\n    }))\n    \n"""
    return replace_once(text, username_anchor, ayu_row + username_anchor, "settings-row")


def patch_own_profile_last_seen(text: str) -> str:
    old = """                    if user.id == context.account.peerId {\n                        return .none\n                    }\n"""
    new = """                    if user.id == context.account.peerId {\n                        // AYU_IOS_PATCH_v0_3: Telegram normally hides the owner's own presence here.\n                        // While Ghost hides online, expose Ayu's locally tracked last-seen instead.\n                        if AyuRuntimeSettings.suppressOnlineStatus {\n                            let timestamp = AyuGhostLastSeen.timestamp\n                            return .presence(TelegramUserPresence(status: .present(until: timestamp), lastActivity: timestamp))\n                        }\n                        return .none\n                    }\n"""
    return replace_once(text, old, new, "own-profile-last-seen")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply AyuGram iOS v0.3 to Telegram-iOS")
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.repo).expanduser().resolve()
    if not (root / "submodules" / "TelegramCore").exists():
        die(f"'{root}' is not TelegramMessenger/Telegram-iOS")

    here = Path(__file__).resolve().parent
    state = root / "submodules/TelegramCore/Sources/State"

    install_payload(
        here / "payload" / "AyuRuntimeSettings.swift",
        state / "AyuRuntimeSettings.swift",
        "runtime settings",
    )
    install_payload(
        here / "payload" / "AyuGhostLastSeen.swift",
        state / "AyuGhostLastSeen.swift",
        "Ghost last-seen state",
    )
    install_payload(
        here / "payload" / "AyuSettingsController.swift",
        root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift",
        "native settings controller",
    )

    patch_file(state / "ManagedAccountPresence.swift", patch_presence)
    patch_file(state / "ManagedLocalInputActivities.swift", patch_typing)
    patch_file(state / "SynchronizePeerReadState.swift", patch_read_state)
    patch_file(state / "ManagedSynchronizeViewStoriesOperations.swift", patch_stories)
    patch_file(state / "AccountStateManagementUtils.swift", patch_deleted_state)

    patch_file(root / "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift", patch_online_pulse)
    patch_file(root / "submodules/TelegramUI/Components/Chat/ChatMessageDateAndStatusNode/Sources/StringForMessageTimestampStatus.swift", patch_timestamp)
    patch_file(root / "submodules/TelegramUI/Components/Chat/ChatMessageDateAndStatusNode/Sources/ChatMessageDateAndStatusNode.swift", patch_status_color)
    patch_file(root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoSettingsItems.swift", patch_native_settings)
    patch_file(root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoData.swift", patch_own_profile_last_seen)

    print("[ayu-v03] DONE")
    print("[ayu-v03] Native Settings -> AyuGram; Ghost defaults OFF; deleted-message preservation defaults ON.")


if __name__ == "__main__":
    main()
