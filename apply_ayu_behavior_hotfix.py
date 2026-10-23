#!/usr/bin/env python3
from pathlib import Path
import sys


def one(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {n}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_behavior_hotfix.py <Telegram-iOS root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()

    # Manual Read: apply the selected MessageIndex locally, then send one exact
    # Telegram read request for the selected max id. Ghost's ordinary background
    # read-sync remains suppressed, so there is no stale one-shot allowance that
    # could leak into a later automatic read.
    enqueue = root / "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift"
    t = enqueue.read_text(encoding="utf-8")
    anchor = "public func enqueueMessages(account: Account, peerId: PeerId, messages: [EnqueueMessage]) -> Signal<[MessageId?], NoError> {\n"
    helper = '''// AYU_BEHAVIOR_HOTFIX_v0_3\n// AYU_MANUAL_READ_SERVER_v0_3\nprivate enum AyuManualReadTarget {\n    case cloud(Api.InputPeer)\n    case secret(Api.InputEncryptedChat)\n}\n\npublic func ayuReadMessageThroughGhost(account: Account, index: MessageIndex) {\n    guard AyuRuntimeSettings.snapshot.master else { return }\n\n    // Clear any allowance left by an older build. This explicit action no longer\n    // depends on the asynchronous PeerReadState synchronization race.\n    AyuRuntimeSettings.consumeManualReadAllowance(peerId: index.id.peerId)\n\n    let signal = account.postbox.transaction { transaction -> AyuManualReadTarget? in\n        // Telegram's own local read helper marks this message and every older\n        // incoming item up to the same MessageIndex as read.\n        _internal_applyMaxReadIndexInteractively(transaction: transaction, stateManager: account.stateManager, index: index)\n\n        guard let peer = transaction.getPeer(index.id.peerId) else {\n            return nil\n        }\n        if index.id.peerId.namespace == Namespaces.Peer.SecretChat {\n            if let input = apiInputSecretChat(peer) {\n                return .secret(input)\n            }\n        } else if let input = apiInputPeer(peer) {\n            return .cloud(input)\n        }\n        return nil\n    }\n    |> mapToSignal { target -> Signal<Void, NoError> in\n        guard let target else {\n            return .complete()\n        }\n\n        switch target {\n        case let .secret(input):\n            return account.network.request(Api.functions.messages.readEncryptedHistory(peer: input, maxDate: index.timestamp))\n            |> `catch` { _ -> Signal<Api.Bool, NoError> in\n                return .complete()\n            }\n            |> mapToSignal { _ -> Signal<Void, NoError> in\n                return .complete()\n            }\n\n        case let .cloud(input):\n            switch input {\n            case let .inputPeerChannel(data):\n                return account.network.request(Api.functions.channels.readHistory(channel: Api.InputChannel.inputChannel(.init(channelId: data.channelId, accessHash: data.accessHash)), maxId: index.id.id))\n                |> `catch` { _ -> Signal<Api.Bool, NoError> in\n                    return .complete()\n                }\n                |> mapToSignal { _ -> Signal<Void, NoError> in\n                    return .complete()\n                }\n\n            default:\n                return account.network.request(Api.functions.messages.readHistory(peer: input, maxId: index.id.id))\n                |> map(Optional.init)\n                |> `catch` { _ -> Signal<Api.messages.AffectedMessages?, NoError> in\n                    return .single(nil)\n                }\n                |> mapToSignal { result -> Signal<Void, NoError> in\n                    if let result {\n                        switch result {\n                        case let .affectedMessages(data):\n                            account.stateManager.addUpdateGroups([.updatePts(pts: data.pts, ptsCount: data.ptsCount)])\n                        }\n                    }\n                    return .complete()\n                }\n            }\n        }\n    }\n\n    let _ = signal.startStandalone()\n}\n\n'''
    if "AYU_BEHAVIOR_HOTFIX_v0_3" not in t:
        t = one(t, anchor, helper + anchor, "read helper")
    enqueue.write_text(t, encoding="utf-8")

    # Persistent burn state: after explicit Burn, keep the preserved local media,
    # hide our Burn context-menu action, and show a small 🔥 beside the timestamp.
    runtime = root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift"
    t = runtime.read_text(encoding="utf-8")
    burn_state_anchor = "    private static let manualBurnMessages = Atomic<Set<String>>(value: Set())\n"
    burn_state = '''    private static let manualBurnMessages = Atomic<Set<String>>(value: Set())\n\n    // AYU_BURNED_VIEW_ONCE_v0_3: durable UI state for explicit manual Burn.\n    private static let burnedViewOnceKey = keyPrefix + "viewOnce.burned"\n    private static let burnedViewOnceMessages = Atomic<Set<String>>(value: Set(UserDefaults.standard.stringArray(forKey: burnedViewOnceKey) ?? []))\n'''
    if "AYU_BURNED_VIEW_ONCE_v0_3" not in t:
        t = one(t, burn_state_anchor, burn_state, "burned view-once state")

    consume_anchor = '''    public static func consumeViewOnceBurnAllowance(_ id: MessageId) {\n        let key = burnMessageKey(id)\n        _ = manualBurnMessages.modify { current in\n            var current = current\n            current.remove(key)\n            return current\n        }\n    }\n\n'''
    consume_new = consume_anchor + '''    public static func markViewOnceBurned(_ id: MessageId) {\n        let key = burnMessageKey(id)\n        var updated: Set<String>?\n        _ = burnedViewOnceMessages.modify { current in\n            if current.contains(key) {\n                return current\n            }\n            var current = current\n            current.insert(key)\n            updated = current\n            return current\n        }\n        if let updated {\n            UserDefaults.standard.set(Array(updated), forKey: burnedViewOnceKey)\n        }\n    }\n\n    public static func isViewOnceBurned(_ id: MessageId) -> Bool {\n        let key = burnMessageKey(id)\n        return burnedViewOnceMessages.with { $0.contains(key) }\n    }\n\n'''
    if "public static func markViewOnceBurned" not in t:
        t = one(t, consume_anchor, consume_new, "burned view-once helpers")

    # Keep the explicit trash marker for deleted messages.
    t = t.replace('            return "✕"\n', '            return "❌"\n')
    t = t.replace('            return "✕ Крест"\n', '            return "❌"\n')

    old_decorate = '''    public static func decorateTimestamp(_ text: String, messageId: MessageId) -> String {\n        guard showDeletedMarker && isDeleted(messageId) else {\n            return text\n        }\n        registerDeletedMessageId(messageId)\n        return "\\(deletedMarkerPrefix) \\(text)"\n    }\n'''
    new_decorate = '''    public static func decorateTimestamp(_ text: String, messageId: MessageId) -> String {\n        var result = text\n        if isViewOnceBurned(messageId) {\n            result = "🔥 \\(result)"\n        }\n        if showDeletedMarker && isDeleted(messageId) {\n            registerDeletedMessageId(messageId)\n            result = "\\(deletedMarkerPrefix) \\(result)"\n        }\n        return result\n    }\n'''
    if "result = \"🔥 \\(result)\"" not in t:
        t = one(t, old_decorate, new_decorate, "burn flame timestamp")
    runtime.write_text(t, encoding="utf-8")

    menu = root / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"
    t = menu.read_text(encoding="utf-8")
    old_read = '''                AyuRuntimeSettings.allowNextRead(peerId: ayuMessage.id.peerId)\n                ayuGhostOnlinePulse(account: context.account)\n                let _ = context.engine.messages.applyMaxReadIndexInteractively(index: ayuMessage.index).startStandalone()\n'''
    if old_read not in t:
        old_read = '''                // AYU_MANUAL_READ_PULSE_v0_3: explicit Read briefly uses\n                // the same 200 ms online pulse as sending, then Ghost returns offline.\n                AyuRuntimeSettings.allowNextRead(peerId: ayuMessage.id.peerId)\n                ayuGhostOnlinePulse(account: context.account)\n                let _ = context.engine.messages.applyMaxReadIndexInteractively(index: ayuMessage.index).startStandalone()\n'''
    new_read = '''                ayuGhostOnlinePulse(account: context.account)\n                ayuReadMessageThroughGhost(account: context.account, index: ayuMessage.index)\n'''
    if "ayuReadMessageThroughGhost(account: context.account" not in t:
        t = one(t, old_read, new_read, "manual Read")

    # Burn is remote-only: notify Telegram that the view-once content was consumed,
    # but keep the local message/media/durable copy intact. Also pulse online 0.2 s.
    old_burn = '''                AyuRuntimeSettings.allowNextViewOnceBurn(ayuBurnMessage.id)\n                let _ = context.engine.messages.markMessageContentAsConsumedInteractively(messageId: ayuBurnMessage.id).startStandalone()\n'''
    new_burn = '''                AyuRuntimeSettings.markViewOnceBurned(ayuBurnMessage.id)\n                ayuGhostOnlinePulse(account: context.account)\n                let _ = ayuBurnViewOnceRemotely(account: context.account, messageId: ayuBurnMessage.id).startStandalone()\n'''
    if "ayuBurnViewOnceRemotely(account: context.account" not in t:
        t = one(t, old_burn, new_burn, "Burn action")
    elif "AyuRuntimeSettings.markViewOnceBurned(ayuBurnMessage.id)" not in t:
        old_existing_burn = '''                ayuGhostOnlinePulse(account: context.account)\n                let _ = ayuBurnViewOnceRemotely(account: context.account, messageId: ayuBurnMessage.id).startStandalone()\n'''
        t = one(t, old_existing_burn, new_burn, "Burn state mark")

    old_guard = '''           AyuRuntimeSettings.shouldPreserveViewOnce(message: ayuBurnMessage) {\n'''
    new_guard = '''           AyuRuntimeSettings.shouldPreserveViewOnce(message: ayuBurnMessage),\n           !AyuRuntimeSettings.isViewOnceBurned(ayuBurnMessage.id) {\n'''
    if "!AyuRuntimeSettings.isViewOnceBurned(ayuBurnMessage.id)" not in t:
        t = one(t, old_guard, new_guard, "hide Burn after burn")
    menu.write_text(t, encoding="utf-8")

    consume = root / "submodules/TelegramCore/Sources/TelegramEngine/Messages/MarkMessageContentAsConsumedInteractively.swift"
    t = consume.read_text(encoding="utf-8")
    consume_anchor_core = "func _internal_markMessageContentAsConsumedInteractively(postbox: Postbox, messageId: MessageId) -> Signal<Void, NoError> {\n"
    burn_helper = '''public func ayuBurnViewOnceRemotely(account: Account, messageId: MessageId) -> Signal<Void, NoError> {\n    return account.postbox.transaction { transaction -> Void in\n        guard let message = transaction.getMessage(messageId), AyuRuntimeSettings.shouldPreserveViewOnce(message: message) else { return }\n        addSynchronizeConsumeMessageContentsOperation(transaction: transaction, messageIds: [messageId])\n    }\n}\n\n'''
    if "public func ayuBurnViewOnceRemotely" not in t:
        t = one(t, consume_anchor_core, burn_helper + consume_anchor_core, "remote Burn helper")

    remote_anchor = "func markMessageContentAsConsumedRemotely(transaction: Transaction, messageId: MessageId, consumeDate: Int32?) {\n    if let message = transaction.getMessage(messageId) {\n"
    remote_new = "func markMessageContentAsConsumedRemotely(transaction: Transaction, messageId: MessageId, consumeDate: Int32?) {\n    if let message = transaction.getMessage(messageId) {\n        if AyuRuntimeSettings.shouldPreserveViewOnce(message: message) {\n            return\n        }\n"
    if "if AyuRuntimeSettings.shouldPreserveViewOnce(message: message) {\n            return\n        }\n        var updateMessage" not in t:
        t = one(t, remote_anchor, remote_new, "remote consume preservation")
    consume.write_text(t, encoding="utf-8")

    # Marker picker labels use emoji too.
    settings = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift"
    t = settings.read_text(encoding="utf-8")
    t = t.replace('            (.cross, "✕ Крест"),\n', '            (.cross, "❌"),\n')
    settings.write_text(t, encoding="utf-8")

    # A same-value StoreMessage update can be coalesced. Change one private local
    # tag bit so Postbox emits a real history-view update immediately; rendering
    # still uses AyuRuntimeSettings.isDeleted(id), so the tag has no UI semantics.
    manager = root / "submodules/TelegramCore/Sources/State/AccountStateManager.swift"
    t = manager.read_text(encoding="utf-8")
    old_tags = "                            localTags: currentMessage.localTags,\n"
    new_tags = '''                            localTags: currentMessage.localTags.union(LocalMessageTags(rawValue: 1 << 30)),\n'''
    if "LocalMessageTags(rawValue: 1 << 30)" not in t:
        t = one(t, old_tags, new_tags, "deleted realtime local tag")
    manager.write_text(t, encoding="utf-8")

    print("[ayu-behavior-hotfix] trash marker + persistent Burn flame/menu state + direct manual-read server push + realtime fixes patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
