import Foundation
import SwiftSignalKit

/// Local last-seen used only for the account owner's profile while Ghost hides online.
/// It represents the last moment Ayu intentionally allowed the account to be online.
public enum AyuGhostLastSeen {
    private static let key = "com.nomadvorga.telegram.ayu.v03.ghostLastSeen"

    private static func now() -> Int32 {
        return Int32(clamping: Int64(Date().timeIntervalSince1970))
    }

    private static func load() -> Int32 {
        let defaults = UserDefaults.standard
        if defaults.object(forKey: key) == nil {
            return now()
        }
        return Int32(clamping: defaults.integer(forKey: key))
    }

    private static let state = Atomic<Int32>(value: load())

    public static var timestamp: Int32 {
        return state.with { $0 }
    }

    public static func recordNow() {
        let value = now()
        UserDefaults.standard.set(Int(value), forKey: key)
        _ = state.swap(value)
    }
}
