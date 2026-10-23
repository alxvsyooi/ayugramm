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
    case onlinePulseOnSend = 6
}

public struct AyuRuntimeSnapshot: Equatable {
    public var master: Bool
    public var hideReadMessages: Bool
    public var hideReadStories: Bool
    public var hideOnline: Bool
    public var hideTyping: Bool
    public var automaticOffline: Bool
    public var onlinePulseOnSend: Bool
}

public enum AyuRuntimeSettings {
    private static let keyPrefix = "com.nomadvorga.telegram.ayu.v03.ghostonly."
    private static let legacyKeyPrefix = "com.nomadvorga.telegram.ayu.v03."

    private static func key(_ option: AyuRuntimeOption) -> String {
        switch option {
        case .master: return keyPrefix + "master"
        case .hideReadMessages: return keyPrefix + "hideReadMessages"
        case .hideReadStories: return keyPrefix + "hideReadStories"
        case .hideOnline: return keyPrefix + "hideOnline"
        case .hideTyping: return keyPrefix + "hideTyping"
        case .automaticOffline: return keyPrefix + "automaticOffline"
        case .onlinePulseOnSend: return keyPrefix + "onlinePulseOnSend"
        }
    }

    private static func defaultValue(_ option: AyuRuntimeOption) -> Bool {
        switch option {
        case .master:
            return false
        case .hideReadMessages, .hideReadStories, .hideOnline, .hideTyping, .automaticOffline, .onlinePulseOnSend:
            return true
        }
    }

    private static func storedValue(_ option: AyuRuntimeOption, defaults: UserDefaults) -> Bool {
        let newKey = key(option)
        if defaults.object(forKey: newKey) != nil {
            return defaults.bool(forKey: newKey)
        }
        let suffix = newKey.replacingOccurrences(of: keyPrefix, with: "")
        let legacyKey = legacyKeyPrefix + suffix
        if defaults.object(forKey: legacyKey) != nil {
            return defaults.bool(forKey: legacyKey)
        }
        return defaultValue(option)
    }

    private static func loadSnapshot() -> AyuRuntimeSnapshot {
        let defaults = UserDefaults.standard
        return AyuRuntimeSnapshot(
            master: storedValue(.master, defaults: defaults),
            hideReadMessages: storedValue(.hideReadMessages, defaults: defaults),
            hideReadStories: storedValue(.hideReadStories, defaults: defaults),
            hideOnline: storedValue(.hideOnline, defaults: defaults),
            hideTyping: storedValue(.hideTyping, defaults: defaults),
            automaticOffline: storedValue(.automaticOffline, defaults: defaults),
            onlinePulseOnSend: true
        )
    }

    private static let state = Atomic<AyuRuntimeSnapshot>(value: loadSnapshot())
    private static let manualReadPeers = Atomic<Set<Int64>>(value: Set())

    public static var snapshot: AyuRuntimeSnapshot {
        return state.with { $0 }
    }

    public static func value(_ option: AyuRuntimeOption) -> Bool {
        let current = snapshot
        switch option {
        case .master: return current.master
        case .hideReadMessages: return current.hideReadMessages
        case .hideReadStories: return current.hideReadStories
        case .hideOnline: return current.hideOnline
        case .hideTyping: return current.hideTyping
        case .automaticOffline: return current.automaticOffline
        case .onlinePulseOnSend: return true
        }
    }

    public static func set(_ option: AyuRuntimeOption, value: Bool) {
        if option == .onlinePulseOnSend {
            return
        }
        UserDefaults.standard.set(value, forKey: key(option))
        _ = state.modify { current in
            var current = current
            switch option {
            case .master: current.master = value
            case .hideReadMessages: current.hideReadMessages = value
            case .hideReadStories: current.hideReadStories = value
            case .hideOnline: current.hideOnline = value
            case .hideTyping: current.hideTyping = value
            case .automaticOffline: current.automaticOffline = value
            case .onlinePulseOnSend: break
            }
            current.onlinePulseOnSend = true
            return current
        }
    }

    public static var suppressReadMessages: Bool {
        return state.with { $0.master && $0.hideReadMessages }
    }

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
        return state.with { $0.master && $0.hideOnline }
    }
}
