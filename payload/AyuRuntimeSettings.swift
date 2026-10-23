import Foundation
import Postbox
import SwiftSignalKit

public enum AyuRuntimeOption: Int32, CaseIterable {
    case master = 0
    case hideReadMessages = 1
    case hideReadStories = 2
    case hideOnline = 3
    case hideTyping = 4
    case automaticOffline = 5
    // Kept only for settings migration. The 0.2 s send pulse is always enabled
    // whenever Ghost + hide-online are enabled and is no longer user-configurable.
    case onlinePulseOnSend = 6
    case keepDeletedMessages = 7
    case showDeletedMarker = 8
}

public enum AyuDeletedMarkerStyle: Int32, CaseIterable {
    case trash = 0
    case text = 1
    case cross = 2
    case compact = 3
}

public enum AyuDeletedMarkerColor: Int32, CaseIterable {
    case red = 0
    case orange = 1
    case gray = 2
    case purple = 3
}

public struct AyuRuntimeSnapshot: Equatable {
    public var master: Bool
    public var hideReadMessages: Bool
    public var hideReadStories: Bool
    public var hideOnline: Bool
    public var hideTyping: Bool
    public var automaticOffline: Bool
    public var onlinePulseOnSend: Bool
    public var keepDeletedMessages: Bool
    public var showDeletedMarker: Bool
    public var deletedMarkerStyle: Int32
    public var deletedMarkerColor: Int32
}

private struct AyuDeletedState {
    var globalIds: Set<Int32>
    var fullIds: Set<String>
}

/// Runtime state for the iOS Ayu port.
/// Hot paths only touch in-memory Atomics. UserDefaults is used for persistence,
/// never as a per-message/per-request lookup.
public enum AyuRuntimeSettings {
    private static let keyPrefix = "com.nomadvorga.telegram.ayu.v03."
    private static let legacyKeyPrefix = "com.nomadvorga.telegram.ayu.v02."
    private static let deletedGlobalKey = keyPrefix + "deleted.global"
    private static let deletedFullKey = keyPrefix + "deleted.full"
    private static let deletedMarkerStyleKey = keyPrefix + "deleted.markerStyle"
    private static let deletedMarkerColorKey = keyPrefix + "deleted.markerColor"
    private static let maxDeletedMarkers = 20_000

    /// Deleted messages in the ordinary chat are deliberately dimmed, while
    /// the dedicated deleted-message viewer renders them at full opacity.
    public static let deletedMessageAlpha: Float = 0.5

    private static func key(_ option: AyuRuntimeOption) -> String {
        switch option {
        case .master:
            return keyPrefix + "master"
        case .hideReadMessages:
            return keyPrefix + "hideReadMessages"
        case .hideReadStories:
            return keyPrefix + "hideReadStories"
        case .hideOnline:
            return keyPrefix + "hideOnline"
        case .hideTyping:
            return keyPrefix + "hideTyping"
        case .automaticOffline:
            return keyPrefix + "automaticOffline"
        case .onlinePulseOnSend:
            return keyPrefix + "onlinePulseOnSend"
        case .keepDeletedMessages:
            return keyPrefix + "keepDeletedMessages"
        case .showDeletedMarker:
            return keyPrefix + "showDeletedMarker"
        }
    }

    private static func defaultValue(_ option: AyuRuntimeOption) -> Bool {
        switch option {
        case .master:
            return false
        case .hideReadMessages, .hideReadStories, .hideOnline, .hideTyping, .automaticOffline, .onlinePulseOnSend, .keepDeletedMessages, .showDeletedMarker:
            return true
        }
    }

    private static func storedValue(_ option: AyuRuntimeOption, defaults: UserDefaults) -> Bool {
        let optionKey = key(option)
        if defaults.object(forKey: optionKey) != nil {
            return defaults.bool(forKey: optionKey)
        }
        // Migrate v0.2 privacy toggles without changing the user's current Ghost setup.
        switch option {
        case .master, .hideReadMessages, .hideReadStories, .hideOnline, .hideTyping, .automaticOffline:
            let suffix = optionKey.replacingOccurrences(of: keyPrefix, with: "")
            let legacyKey = legacyKeyPrefix + suffix
            if defaults.object(forKey: legacyKey) != nil {
                return defaults.bool(forKey: legacyKey)
            }
        case .onlinePulseOnSend, .keepDeletedMessages, .showDeletedMarker:
            break
        }
        return defaultValue(option)
    }

    private static func loadSnapshot() -> AyuRuntimeSnapshot {
        let defaults = UserDefaults.standard
        let style: Int32
        if defaults.object(forKey: deletedMarkerStyleKey) == nil {
            style = AyuDeletedMarkerStyle.trash.rawValue
        } else {
            style = Int32(defaults.integer(forKey: deletedMarkerStyleKey))
        }
        let color: Int32
        if defaults.object(forKey: deletedMarkerColorKey) == nil {
            color = AyuDeletedMarkerColor.red.rawValue
        } else {
            color = Int32(defaults.integer(forKey: deletedMarkerColorKey))
        }
        return AyuRuntimeSnapshot(
            master: storedValue(.master, defaults: defaults),
            hideReadMessages: storedValue(.hideReadMessages, defaults: defaults),
            hideReadStories: storedValue(.hideReadStories, defaults: defaults),
            hideOnline: storedValue(.hideOnline, defaults: defaults),
            hideTyping: storedValue(.hideTyping, defaults: defaults),
            automaticOffline: storedValue(.automaticOffline, defaults: defaults),
            onlinePulseOnSend: true,
            keepDeletedMessages: storedValue(.keepDeletedMessages, defaults: defaults),
            showDeletedMarker: storedValue(.showDeletedMarker, defaults: defaults),
            deletedMarkerStyle: style,
            deletedMarkerColor: color
        )
    }

    private static func loadDeletedState() -> AyuDeletedState {
        let defaults = UserDefaults.standard
        let rawGlobal = defaults.array(forKey: deletedGlobalKey) as? [Int] ?? []
        let fullIds = Set(defaults.stringArray(forKey: deletedFullKey) ?? [])
        // Global delete updates do not contain a peer id. Once Telegram has
        // resolved one to a peer-qualified key, retaining the raw Int32 would
        // make an unrelated message with the same per-chat id look deleted.
        let resolvedIds = Set(fullIds.compactMap { key -> Int32? in
            guard let rawId = key.split(separator: ":").last else {
                return nil
            }
            return Int32(rawId)
        })
        let globalIds = Set(rawGlobal.compactMap { Int32(exactly: $0) }).subtracting(resolvedIds)
        return AyuDeletedState(globalIds: globalIds, fullIds: fullIds)
    }

    private static let state = Atomic<AyuRuntimeSnapshot>(value: loadSnapshot())
    private static let deletedState = Atomic<AyuDeletedState>(value: loadDeletedState())

    /// A one-operation bypass for the explicit "Прочитать" context-menu action.
    /// This is a set, not a timer/poller: the next peer read synchronization consumes it.
    private static let manualReadPeers = Atomic<Set<Int64>>(value: Set())

    public static var snapshot: AyuRuntimeSnapshot {
        return state.with { $0 }
    }

    public static func value(_ option: AyuRuntimeOption) -> Bool {
        let current = snapshot
        switch option {
        case .master:
            return current.master
        case .hideReadMessages:
            return current.hideReadMessages
        case .hideReadStories:
            return current.hideReadStories
        case .hideOnline:
            return current.hideOnline
        case .hideTyping:
            return current.hideTyping
        case .automaticOffline:
            return current.automaticOffline
        case .onlinePulseOnSend:
            return true
        case .keepDeletedMessages:
            return current.keepDeletedMessages
        case .showDeletedMarker:
            return current.showDeletedMarker
        }
    }

    public static func set(_ option: AyuRuntimeOption, value: Bool) {
        // The send pulse is intentionally permanent now. Ignore old callers/key values.
        if option == .onlinePulseOnSend {
            return
        }
        UserDefaults.standard.set(value, forKey: key(option))
        _ = state.modify { current in
            var current = current
            switch option {
            case .master:
                current.master = value
            case .hideReadMessages:
                current.hideReadMessages = value
            case .hideReadStories:
                current.hideReadStories = value
            case .hideOnline:
                current.hideOnline = value
            case .hideTyping:
                current.hideTyping = value
            case .automaticOffline:
                current.automaticOffline = value
            case .onlinePulseOnSend:
                break
            case .keepDeletedMessages:
                current.keepDeletedMessages = value
            case .showDeletedMarker:
                current.showDeletedMarker = value
            }
            current.onlinePulseOnSend = true
            return current
        }
    }

    public static func setDeletedMarkerStyle(_ value: Int32) {
        let normalized = AyuDeletedMarkerStyle(rawValue: value)?.rawValue ?? AyuDeletedMarkerStyle.trash.rawValue
        UserDefaults.standard.set(Int(normalized), forKey: deletedMarkerStyleKey)
        _ = state.modify { current in
            var current = current
            current.deletedMarkerStyle = normalized
            return current
        }
    }

    public static func setDeletedMarkerColor(_ value: Int32) {
        let normalized = AyuDeletedMarkerColor(rawValue: value)?.rawValue ?? AyuDeletedMarkerColor.red.rawValue
        UserDefaults.standard.set(Int(normalized), forKey: deletedMarkerColorKey)
        _ = state.modify { current in
            var current = current
            current.deletedMarkerColor = normalized
            return current
        }
    }

    public static var suppressReadMessages: Bool {
        return state.with { $0.master && $0.hideReadMessages }
    }

    /// Used by the read-sync layer so only the explicit manual-read operation can pass.
    public static func shouldSuppressRead(peerId: PeerId) -> Bool {
        guard suppressReadMessages else {
            return false
        }
        let key = peerId.toInt64()
        return manualReadPeers.with { !$0.contains(key) }
    }

    public static func allowNextRead(peerId: PeerId) {
        let key = peerId.toInt64()
        _ = manualReadPeers.modify { current in
            var current = current
            current.insert(key)
            return current
        }
    }

    public static func consumeManualReadAllowance(peerId: PeerId) {
        let key = peerId.toInt64()
        _ = manualReadPeers.modify { current in
            var current = current
            current.remove(key)
            return current
        }
    }

    public static var suppressStoryViews: Bool {
        return state.with { $0.master && $0.hideReadStories }
    }

    public static var suppressOnlineStatus: Bool {
        return state.with { $0.master && $0.hideOnline }
    }

    public static var suppressTypingActivities: Bool {
        return state.with { $0.master && $0.hideTyping }
    }

    public static var shouldSendAutomaticOffline: Bool {
        return state.with { $0.master && $0.hideOnline && $0.automaticOffline }
    }

    public static var shouldPulseOnlineOnSend: Bool {
        // Always enabled when Ghost is actively hiding online status.
        return state.with { $0.master && $0.hideOnline }
    }

    public static var keepDeletedMessages: Bool {
        return state.with { $0.keepDeletedMessages }
    }

    public static var showDeletedMarker: Bool {
        return state.with { $0.keepDeletedMessages && $0.showDeletedMarker }
    }

    private static func fullKey(_ id: MessageId) -> String {
        return "\(id.peerId.namespace):\(id.peerId.id._internalGetInt64Value()):\(id.namespace):\(id.id)"
    }

    private static func peerFullKeyPrefix(_ peerId: PeerId) -> String {
        return "\(peerId.namespace):\(peerId.id._internalGetInt64Value()):"
    }

    private static func persistDeletedState(_ value: AyuDeletedState) {
        let defaults = UserDefaults.standard
        defaults.set(value.globalIds.map(Int.init), forKey: deletedGlobalKey)
        defaults.set(Array(value.fullIds), forKey: deletedFullKey)
    }

    public static func markDeletedGlobalIds(_ ids: [Int32]) {
        guard !ids.isEmpty else {
            return
        }
        var updated: AyuDeletedState?
        _ = deletedState.modify { current in
            var current = current
            for id in ids {
                current.globalIds.insert(id)
            }
            if current.globalIds.count > maxDeletedMarkers {
                current.globalIds = Set(current.globalIds.prefix(maxDeletedMarkers))
            }
            updated = current
            return current
        }
        // Atomic is already updated before persistence, so lookups see the deletion immediately.
        if let updated {
            persistDeletedState(updated)
        }
    }

    public static func markDeletedMessageIds(_ ids: [MessageId]) {
        guard !ids.isEmpty else {
            return
        }
        var updated: AyuDeletedState?
        _ = deletedState.modify { current in
            var current = current
            for id in ids {
                current.fullIds.insert(fullKey(id))
                if id.peerId.namespace != Namespaces.Peer.CloudChannel {
                    current.globalIds.remove(id.id)
                }
            }
            if current.fullIds.count > maxDeletedMarkers {
                current.fullIds = Set(current.fullIds.prefix(maxDeletedMarkers))
            }
            updated = current
            return current
        }
        if let updated {
            persistDeletedState(updated)
        }
    }

    /// Promotes a non-channel global deletion to a peer-qualified id as soon as the
    /// message is rendered. This makes per-chat clearing/viewing deterministic.
    public static func registerDeletedMessageId(_ id: MessageId) {
        guard isDeleted(id) else {
            return
        }
        let key = fullKey(id)
        var updated: AyuDeletedState?
        _ = deletedState.modify { current in
            let alreadyQualified = current.fullIds.contains(key)
            let hasRawGlobal = id.peerId.namespace != Namespaces.Peer.CloudChannel && current.globalIds.contains(id.id)
            if alreadyQualified && !hasRawGlobal {
                return current
            }
            var current = current
            current.fullIds.insert(key)
            if id.peerId.namespace != Namespaces.Peer.CloudChannel {
                current.globalIds.remove(id.id)
            }
            if current.fullIds.count > maxDeletedMarkers {
                current.fullIds = Set(current.fullIds.prefix(maxDeletedMarkers))
            }
            updated = current
            return current
        }
        if let updated {
            persistDeletedState(updated)
        }
    }

    public static func clearDeletedMarkers() {
        _ = deletedState.modify { _ in
            return AyuDeletedState(globalIds: Set(), fullIds: Set())
        }
        UserDefaults.standard.removeObject(forKey: deletedGlobalKey)
        UserDefaults.standard.removeObject(forKey: deletedFullKey)
    }

    /// Clears only deleted-message markers belonging to one chat.
    public static func clearDeletedMarkers(peerId: PeerId) {
        let prefix = peerFullKeyPrefix(peerId)
        var updated: AyuDeletedState?
        _ = deletedState.modify { current in
            var current = current
            let removedKeys = current.fullIds.filter { $0.hasPrefix(prefix) }
            if removedKeys.isEmpty {
                return current
            }
            current.fullIds.subtract(removedKeys)
            for key in removedKeys {
                if let rawId = key.split(separator: ":").last, let value = Int32(rawId) {
                    current.globalIds.remove(value)
                }
            }
            updated = current
            return current
        }
        if let updated {
            persistDeletedState(updated)
        }
    }

    public static func isDeleted(_ id: MessageId) -> Bool {
        return deletedState.with { current in
            if current.fullIds.contains(fullKey(id)) {
                return true
            }
            if id.namespace == Namespaces.Message.Cloud && id.peerId.namespace != Namespaces.Peer.CloudChannel {
                return current.globalIds.contains(id.id)
            }
            return false
        }
    }

    public static var deletedMarkerPrefix: String {
        switch AyuDeletedMarkerStyle(rawValue: state.with({ $0.deletedMarkerStyle })) ?? .trash {
        case .trash:
            return "🗑"
        case .text:
            return "Удалено"
        case .cross:
            return "✕"
        case .compact:
            return "DEL"
        }
    }

    public static var deletedMarkerStyleTitle: String {
        switch AyuDeletedMarkerStyle(rawValue: state.with({ $0.deletedMarkerStyle })) ?? .trash {
        case .trash:
            return "🗑 Значок"
        case .text:
            return "Удалено"
        case .cross:
            return "✕ Крест"
        case .compact:
            return "DEL"
        }
    }

    public static var deletedMarkerColorTitle: String {
        switch AyuDeletedMarkerColor(rawValue: state.with({ $0.deletedMarkerColor })) ?? .red {
        case .red:
            return "Красный"
        case .orange:
            return "Оранжевый"
        case .gray:
            return "Серый"
        case .purple:
            return "Фиолетовый"
        }
    }

    public static func decorateTimestamp(_ text: String, messageId: MessageId) -> String {
        guard showDeletedMarker && isDeleted(messageId) else {
            return text
        }
        registerDeletedMessageId(messageId)
        return "\(deletedMarkerPrefix) \(text)"
    }

    public static func isDeletedTimestampText(_ text: String) -> Bool {
        guard showDeletedMarker else {
            return false
        }
        return text.hasPrefix(deletedMarkerPrefix + " ")
    }
}
