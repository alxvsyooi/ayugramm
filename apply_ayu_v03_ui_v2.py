#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import apply_ayu_v03_crashfix as crashfix

base = crashfix.base


def patch_read_state(text: str) -> str:
    """Keep the transaction-safe Ghost read suppression, but allow exactly one
    explicit read synchronization when the user taps the Ayu 'Прочитать' action.
    """
    old = """func synchronizePeerReadState(network: Network, postbox: Postbox, stateManager: AccountStateManager, peerId: PeerId, push: Bool, validate: Bool) -> Signal<Never, PeerReadStateValidationError> {\n    var signal: Signal<Never, PeerReadStateValidationError> = .complete()\n    if push {\n        signal = signal\n        |> then(pushPeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n    if validate {\n        signal = signal\n        |> then(validatePeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n    return signal\n}"""

    new = """func synchronizePeerReadState(network: Network, postbox: Postbox, stateManager: AccountStateManager, peerId: PeerId, push: Bool, validate: Bool) -> Signal<Never, PeerReadStateValidationError> {\n    // AYU_IOS_PATCH_v0_3: Ghost read suppression must remove the Postbox\n    // synchronization operation before completing. Returning .single(readState)\n    // here/inside pushPeerReadState completes synchronously while the operation is\n    // still visible, and ManagedSynchronizePeerReadStates immediately calls update()\n    // again -> unbounded SwiftSignalKit recursion / stack overflow.\n    if AyuRuntimeSettings.shouldSuppressRead(peerId: peerId) {\n        return postbox.transaction { transaction -> Void in\n            transaction.confirmSynchronizedIncomingReadState(peerId)\n        }\n        |> castError(PeerReadStateValidationError.self)\n        |> ignoreValues\n    }\n\n    // A manual allowance is single-use: this synchronization is allowed through,\n    // then Ghost immediately resumes suppressing future read receipts.\n    AyuRuntimeSettings.consumeManualReadAllowance(peerId: peerId)\n\n    var signal: Signal<Never, PeerReadStateValidationError> = .complete()\n    if push {\n        signal = signal\n        |> then(pushPeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n    if validate {\n        signal = signal\n        |> then(validatePeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n    return signal\n}"""

    return base.replace_once(text, old, new, "read-crashfix-manual-bypass")


def patch_runtime_features(text: str) -> str:
    text = base.replace_once(
        text,
        """public enum AyuDeletedMarkerColor: Int32, CaseIterable {\n    case red = 0\n    case orange = 1\n    case gray = 2\n    case purple = 3\n}\n""",
        """public enum AyuDeletedMarkerColor: Int32, CaseIterable {\n    case red = 0\n    case orange = 1\n    case gray = 2\n    case purple = 3\n    case pink = 4\n    case magenta = 5\n    case indigo = 6\n    case blue = 7\n    case telegram = 8\n}\n""",
        "deleted-color-palette",
    )

    text = base.replace_once(
        text,
        """    private static let manualReadPeers = Atomic<Set<Int64>>(value: Set())\n""",
        """    private static let manualReadPeers = Atomic<Set<Int64>>(value: Set())\n\n    // Only used while the dedicated deleted-message viewer is on screen.\n    // This is a single Atomic read in the message configuration path; no timers/polling.\n    private static let deletedViewerPeerId = Atomic<Int64?>(value: nil)\n""",
        "deleted-viewer-state",
    )

    anchor = """    public static func isDeleted(_ id: MessageId) -> Bool {\n"""
    helpers = """    /// Peer-qualified deleted ids used by the dedicated viewer and per-chat clear.\n    /// Global ids are promoted to full ids by the ordinary chat renderer, so this\n    /// stays bounded and never scans all Postbox messages.\n    public static func deletedMessageIds(peerId: PeerId) -> [MessageId] {\n        let prefix = peerFullKeyPrefix(peerId)\n        return deletedState.with { current in\n            return current.fullIds.compactMap { key -> MessageId? in\n                guard key.hasPrefix(prefix) else {\n                    return nil\n                }\n                let parts = key.split(separator: \":\")\n                guard parts.count == 4, let namespace = Int32(parts[2]), let id = Int32(parts[3]) else {\n                    return nil\n                }\n                return MessageId(peerId: peerId, namespace: namespace, id: id)\n            }.sorted(by: { lhs, rhs in\n                if lhs.namespace != rhs.namespace {\n                    return lhs.namespace < rhs.namespace\n                }\n                return lhs.id < rhs.id\n            })\n        }\n    }\n\n    public static func beginDeletedViewer(peerId: PeerId) {\n        _ = deletedViewerPeerId.swap(peerId.toInt64())\n    }\n\n    public static func endDeletedViewer(peerId: PeerId) {\n        let key = peerId.toInt64()\n        _ = deletedViewerPeerId.modify { current in\n            if current == key {\n                return nil\n            }\n            return current\n        }\n    }\n\n    public static func shouldDimDeletedMessage(_ id: MessageId) -> Bool {\n        guard isDeleted(id) else {\n            return false\n        }\n        let viewerPeer = deletedViewerPeerId.with { $0 }\n        return viewerPeer != id.peerId.toInt64()\n    }\n\n    public static func isInDeletedViewer(_ id: MessageId) -> Bool {\n        return deletedViewerPeerId.with { $0 == id.peerId.toInt64() }\n    }\n\n"""
    text = base.replace_once(text, anchor, helpers + anchor, "deleted-viewer-helpers")

    old_prefix = """    public static var deletedMarkerPrefix: String {\n        switch AyuDeletedMarkerStyle(rawValue: state.with({ $0.deletedMarkerStyle })) ?? .trash {\n        case .trash:\n            return \"🗑\"\n        case .text:\n            return \"Удалено\"\n        case .cross:\n            return \"✕\"\n        case .compact:\n            return \"DEL\"\n        }\n    }\n"""
    new_prefix = """    public static var deletedMarkerPrefix: String {\n        switch AyuDeletedMarkerStyle(rawValue: state.with({ $0.deletedMarkerStyle })) ?? .trash {\n        case .trash:\n            return \"🗑\"\n        case .text:\n            return \"\"\n        case .cross:\n            return \"✕\"\n        case .compact:\n            return \"◉\"\n        }\n    }\n"""
    text = base.replace_once(text, old_prefix, new_prefix, "deleted-marker-prefixes")

    old_style_title = """    public static var deletedMarkerStyleTitle: String {\n        switch AyuDeletedMarkerStyle(rawValue: state.with({ $0.deletedMarkerStyle })) ?? .trash {\n        case .trash:\n            return \"🗑 Значок\"\n        case .text:\n            return \"Удалено\"\n        case .cross:\n            return \"✕ Крест\"\n        case .compact:\n            return \"DEL\"\n        }\n    }\n"""
    new_style_title = """    public static var deletedMarkerStyleTitle: String {\n        switch AyuDeletedMarkerStyle(rawValue: state.with({ $0.deletedMarkerStyle })) ?? .trash {\n        case .trash:\n            return \"Корзинка\"\n        case .text:\n            return \"Убрать значок\"\n        case .cross:\n            return \"Крестик\"\n        case .compact:\n            return \"Глазик\"\n        }\n    }\n"""
    text = base.replace_once(text, old_style_title, new_style_title, "deleted-marker-style-titles")

    old_color_title = """    public static var deletedMarkerColorTitle: String {\n        switch AyuDeletedMarkerColor(rawValue: state.with({ $0.deletedMarkerColor })) ?? .red {\n        case .red:\n            return \"Красный\"\n        case .orange:\n            return \"Оранжевый\"\n        case .gray:\n            return \"Серый\"\n        case .purple:\n            return \"Фиолетовый\"\n        }\n    }\n"""
    new_color_title = """    public static var deletedMarkerColorTitle: String {\n        switch AyuDeletedMarkerColor(rawValue: state.with({ $0.deletedMarkerColor })) ?? .telegram {\n        case .red:\n            return \"Красный\"\n        case .orange:\n            return \"Оранжевый\"\n        case .gray:\n            return \"Серый\"\n        case .purple:\n            return \"Фиолетовый\"\n        case .pink:\n            return \"Розовый\"\n        case .magenta:\n            return \"Малиновый\"\n        case .indigo:\n            return \"Индиго\"\n        case .blue:\n            return \"Синий\"\n        case .telegram:\n            return \"Тема Telegram\"\n        }\n    }\n"""
    text = base.replace_once(text, old_color_title, new_color_title, "deleted-color-titles")

    text = base.replace_once(text, "            color = AyuDeletedMarkerColor.red.rawValue\n", "            color = AyuDeletedMarkerColor.telegram.rawValue\n", "deleted-color-default")
    text = base.replace_once(text, "        let normalized = AyuDeletedMarkerColor(rawValue: value)?.rawValue ?? AyuDeletedMarkerColor.red.rawValue\n", "        let normalized = AyuDeletedMarkerColor(rawValue: value)?.rawValue ?? AyuDeletedMarkerColor.telegram.rawValue\n", "deleted-color-normalization")

    old_decorate = """    public static func decorateTimestamp(_ text: String, messageId: MessageId) -> String {\n        guard showDeletedMarker && isDeleted(messageId) else {\n            return text\n        }\n        registerDeletedMessageId(messageId)\n        return \"\\(deletedMarkerPrefix) \\(text)\"\n    }\n\n    public static func isDeletedTimestampText(_ text: String) -> Bool {\n        guard showDeletedMarker else {\n            return false\n        }\n        return text.hasPrefix(deletedMarkerPrefix + \" \")\n    }\n"""
    new_decorate = """    public static func decorateTimestamp(_ text: String, messageId: MessageId) -> String {\n        guard showDeletedMarker && isDeleted(messageId) else {\n            return text\n        }\n        registerDeletedMessageId(messageId)\n        if isInDeletedViewer(messageId) {\n            return \"🗑 \\(text)\"\n        }\n        let marker = deletedMarkerPrefix\n        guard !marker.isEmpty else {\n            return text\n        }\n        return \"\\(marker) \\(text)\"\n    }\n\n    public static func isDeletedTimestampText(_ text: String) -> Bool {\n        guard showDeletedMarker else {\n            return false\n        }\n        let marker = deletedMarkerPrefix\n        guard !marker.isEmpty else {\n            return false\n        }\n        return text.hasPrefix(marker + \" \")\n    }\n"""
    return base.replace_once(text, old_decorate, new_decorate, "deleted-timestamp-decoration")


def patch_settings_choices(text: str) -> str:
    old_styles = """        let options: [(AyuDeletedMarkerStyle, String)] = [\n            (.trash, \"🗑 Значок\"),\n            (.text, \"Удалено\"),\n            (.cross, \"✕ Крест\"),\n            (.compact, \"DEL\")\n        ]\n"""
    new_styles = """        let options: [(AyuDeletedMarkerStyle, String)] = [\n            (.text, \"Убрать значок\"),\n            (.trash, \"🗑 Корзинка\"),\n            (.cross, \"✕ Крестик\"),\n            (.compact, \"◉ Глазик\")\n        ]\n"""
    text = base.replace_once(text, old_styles, new_styles, "settings-marker-style-options")

    old_colors = """        let options: [(AyuDeletedMarkerColor, String)] = [\n            (.red, \"🔴 Красный\"),\n            (.orange, \"🟠 Оранжевый\"),\n            (.gray, \"⚪️ Серый\"),\n            (.purple, \"🟣 Фиолетовый\")\n        ]\n"""
    new_colors = """        let options: [(AyuDeletedMarkerColor, String)] = [\n            (.telegram, \"Тема Telegram\"),\n            (.gray, \"⚪️ Серый\"),\n            (.red, \"🔴 Красный\"),\n            (.orange, \"🟠 Оранжевый\"),\n            (.pink, \"🩷 Розовый\"),\n            (.magenta, \"🩷 Малиновый\"),\n            (.purple, \"🟣 Фиолетовый\"),\n            (.indigo, \"🔵 Индиго\"),\n            (.blue, \"🔵 Синий\")\n        ]\n"""
    return base.replace_once(text, old_colors, new_colors, "settings-marker-color-options")


def patch_status_marker_only(text: str) -> str:
    """Tint only the deletion marker. The actual message time keeps Telegram's
    original secondary-text color, fixing the old behavior that colored the date.
    """
    old = """            let dateFont = Font.regular(floor(arguments.presentationData.fontSize.baseDisplaySize * 11.0 / 17.0))\n            let (date, dateApply) = dateLayout(TextNodeLayoutArguments(attributedString: NSAttributedString(string: updatedDateText, font: dateFont, textColor: dateColor), backgroundColor: nil, maximumNumberOfLines: 1, truncationType: .middle, constrainedSize: arguments.constrainedSize, alignment: .natural, cutout: nil, insets: UIEdgeInsets()))\n"""
    new = """            let dateFont = Font.regular(floor(arguments.presentationData.fontSize.baseDisplaySize * 11.0 / 17.0))\n            // AYU_IOS_PATCH_v0_3: keep Telegram's normal date color. Only the\n            // deletion marker prefix is tinted with the selected Ayu color.\n            let ayuDateText = NSMutableAttributedString(string: updatedDateText, font: dateFont, textColor: dateColor)\n            if AyuRuntimeSettings.isDeletedTimestampText(updatedDateText) {\n                let markerPrefix = AyuRuntimeSettings.deletedMarkerPrefix + \" \"\n                let markerLength = (markerPrefix as NSString).length\n                if markerLength <= ayuDateText.length {\n                    let markerColor: UIColor\n                    switch AyuDeletedMarkerColor(rawValue: AyuRuntimeSettings.snapshot.deletedMarkerColor) ?? .red {\n                    case .red:\n                        markerColor = UIColor.systemRed\n                    case .orange:\n                        markerColor = UIColor.systemOrange\n                    case .gray:\n                        markerColor = UIColor.systemGray\n                    case .purple:\n                        markerColor = UIColor.systemPurple\n                    case .pink:\n                        markerColor = UIColor.systemPink\n                    case .magenta:\n                        markerColor = UIColor(red: 0.86, green: 0.12, blue: 0.46, alpha: 1.0)\n                    case .indigo:\n                        markerColor = UIColor.systemIndigo\n                    case .blue:\n                        markerColor = UIColor.systemBlue\n                    }\n                    ayuDateText.addAttribute(.foregroundColor, value: markerColor, range: NSRange(location: 0, length: markerLength))\n                }\n            }\n            let (date, dateApply) = dateLayout(TextNodeLayoutArguments(attributedString: ayuDateText, backgroundColor: nil, maximumNumberOfLines: 1, truncationType: .middle, constrainedSize: arguments.constrainedSize, alignment: .natural, cutout: nil, insets: UIEdgeInsets()))\n"""
    new = new.replace("snapshot.deletedMarkerColor) ?? .red", "snapshot.deletedMarkerColor) ?? .telegram", 1)
    new = new.replace("                    case .blue:\\n                        markerColor = UIColor.systemBlue\\n", "                    case .blue:\\n                        markerColor = UIColor.systemBlue\\n                    case .telegram:\\n                        markerColor = dateColor\\n", 1)
    return base.replace_once(text, old, new, "deleted-marker-only-color")


def patch_deleted_alpha(text: str) -> str:
    old_create = """            let node = (viewClassName as! ChatMessageItemView.Type).init(rotated: self.controllerInteraction.chatIsRotated)\n            node.setupItem(self, synchronousLoad: synchronousLoads)\n            \n            let nodeLayout = node.asyncLayout()\n"""
    new_create = """            let node = (viewClassName as! ChatMessageItemView.Type).init(rotated: self.controllerInteraction.chatIsRotated)\n            node.setupItem(self, synchronousLoad: synchronousLoads)\n            // AYU_IOS_PATCH_v0_3: one O(1) Atomic lookup per configured item.\n            // No timers, polling or per-frame work. The deleted-only viewer\n            // explicitly opts the peer out of dimming while it is on screen.\n            let ayuIsDeleted = AyuRuntimeSettings.isDeleted(self.message.id)\n            if ayuIsDeleted {\n                AyuRuntimeSettings.registerDeletedMessageId(self.message.id)\n            }\n            node.alpha = AyuRuntimeSettings.shouldDimDeletedMessage(self.message.id) ? CGFloat(AyuRuntimeSettings.deletedMessageAlpha) : 1.0\n            \n            let nodeLayout = node.asyncLayout()\n"""
    text = base.replace_once(text, old_create, new_create, "deleted-alpha-create")

    old_update = """            if let nodeValue = node() as? ChatMessageItemView {\n                nodeValue.setupItem(self, synchronousLoad: false)\n                \n                let nodeLayout = nodeValue.asyncLayout()\n"""
    new_update = """            if let nodeValue = node() as? ChatMessageItemView {\n                nodeValue.setupItem(self, synchronousLoad: false)\n                let ayuIsDeleted = AyuRuntimeSettings.isDeleted(self.message.id)\n                if ayuIsDeleted {\n                    AyuRuntimeSettings.registerDeletedMessageId(self.message.id)\n                }\n                nodeValue.alpha = AyuRuntimeSettings.shouldDimDeletedMessage(self.message.id) ? CGFloat(AyuRuntimeSettings.deletedMessageAlpha) : 1.0\n                \n                let nodeLayout = nodeValue.asyncLayout()\n"""
    return base.replace_once(text, old_update, new_update, "deleted-alpha-update")


def patch_message_context_read(text: str) -> str:
    anchor = """        return ContextController.Items(content: .list(actions), tip: nil)\n"""
    addition = """        // AYU_IOS_PATCH_v0_3: explicit one-message/chat read escape hatch.\n        // It is deliberately appended after every stock action, so it is the\n        // final context-menu item exactly when Ghost + no-read are active.\n        if AyuRuntimeSettings.suppressReadMessages, let ayuMessage = messages.first, ayuMessage.effectivelyIncoming(context.account.peerId) {\n            if !actions.isEmpty {\n                actions.append(.separator)\n            }\n            actions.append(.action(ContextMenuActionItem(text: \"Прочитать\", icon: { theme in\n                return generateTintedImage(image: UIImage(bundleImageName: \"Chat/Context Menu/MarkAsRead\"), color: theme.actionSheet.primaryTextColor)\n            }, action: { _, f in\n                AyuRuntimeSettings.allowNextRead(peerId: ayuMessage.id.peerId)\n                let _ = context.engine.messages.applyMaxReadIndexInteractively(index: ayuMessage.index).startStandalone()\n                f(.dismissWithoutContent)\n            })))\n        }\n\n"""
    return base.replace_once(text, anchor, addition + anchor, "message-context-manual-read")


def patch_peer_info_deleted_menu(text: str) -> str:
    anchor = """                var hasDiscussion = false\n"""
    addition = """                // AYU_IOS_PATCH_v0_3: per-chat deleted-message controls in the\n                // three-dot menu opened from the chat header.\n                if strongSelf.isOpenedFromChat {\n                    items.append(.action(ContextMenuActionItem(text: \"Посмотреть удалёнки\", icon: { theme in\n                        return generateTintedImage(image: UIImage(bundleImageName: \"Chat/Context Menu/MessageBubble\"), color: theme.contextMenu.primaryColor)\n                    }, action: { [weak self] _, f in\n                        f(.dismissWithoutContent)\n                        guard let self else {\n                            return\n                        }\n                        if let deletedController = ayuDeletedMessagesController(context: self.context, peerId: self.peerId) {\n                            self.controller?.push(deletedController)\n                        }\n                    })))\n\n                    items.append(.action(ContextMenuActionItem(text: \"Очистить удалёнки\", textColor: .destructive, icon: { theme in\n                        return generateTintedImage(image: UIImage(bundleImageName: \"Chat/Context Menu/Delete\"), color: theme.contextMenu.destructiveColor)\n                    }, action: { [weak self] _, f in\n                        f(.dismissWithoutContent)\n                        guard let self else {\n                            return\n                        }\n                        let peerId = self.peerId\n                        let ids = AyuRuntimeSettings.deletedMessageIds(peerId: peerId)\n                        let finish: () -> Void = { [weak self] in\n                            AyuRuntimeSettings.clearDeletedMarkers(peerId: peerId)\n                            if let navigationController = self?.controller?.navigationController as? NavigationController {\n                                navigationController.popToRoot(animated: true)\n                            }\n                        }\n                        guard !ids.isEmpty else {\n                            finish()\n                            return\n                        }\n                        let context = self.context\n                        let _ = (context.account.postbox.transaction { transaction -> Void in\n                            context.engine.messages.deleteMessages(transaction: transaction, ids: ids)\n                        }\n                        |> deliverOnMainQueue).startStandalone(completed: {\n                            finish()\n                        })\n                    })))\n                }\n\n"""
    return base.replace_once(text, anchor, addition + anchor, "peer-info-deleted-menu")


# Override the crashfix/base transforms before running the normal patcher.
base.patch_read_state = patch_read_state
base.patch_status_color = patch_status_marker_only


if __name__ == "__main__":
    base.main()

    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").expanduser().resolve()
    here = Path(__file__).resolve().parent

    # Extend the installed runtime/settings without touching any stock Telegram UI
    # backgrounds, reply nodes, gift buttons or timestamp colors.
    base.patch_file(
        root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift",
        patch_runtime_features,
    )
    base.patch_file(
        root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift",
        patch_settings_choices,
    )
    base.install_payload(
        here / "payload" / "AyuDeletedMessagesController.swift",
        root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuDeletedMessagesController.swift",
        "deleted messages viewer",
    )

    base.patch_file(
        root / "submodules/TelegramUI/Components/Chat/ChatMessageItemImpl/Sources/ChatMessageItemImpl.swift",
        patch_deleted_alpha,
    )
    base.patch_file(
        root / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift",
        patch_message_context_read,
    )
    base.patch_file(
        root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoScreenPerformButtonAction.swift",
        patch_peer_info_deleted_menu,
    )
    print("[ayu-v03-ui-v2] DONE")
