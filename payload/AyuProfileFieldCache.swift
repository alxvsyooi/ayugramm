import Foundation
import Postbox
import TelegramCore
import SwiftSignalKit

struct AyuCachedProfileFields {
    let phone: String?
    let username: String?
    let note: String?
}

private struct AyuCachedProfileFieldsCodable: Codable {
    var phone: String? = nil
    var username: String? = nil
    var note: String? = nil
}

/// Keeps only profile fields that Telegram has already shown to this client.
/// Nil/empty server updates never erase a previously known value.
enum AyuProfileFieldCache {
    private static let defaultsKey = "com.nomadvorga.telegram.ayu.v03.profileFieldCache"

    private static func peerKey(_ peerId: PeerId) -> String {
        return String(peerId.toInt64())
    }

    private static func load() -> [String: AyuCachedProfileFieldsCodable] {
        guard let data = UserDefaults.standard.data(forKey: defaultsKey),
              let value = try? JSONDecoder().decode([String: AyuCachedProfileFieldsCodable].self, from: data) else {
            return [:]
        }
        return value
    }

    private static let state = Atomic<[String: AyuCachedProfileFieldsCodable]>(value: load())

    static func remember(peerId: PeerId, phone: String?, username: String?, note: String?) {
        var valueToPersist: [String: AyuCachedProfileFieldsCodable]?
        _ = state.modify { current in
            var current = current
            let key = peerKey(peerId)
            var entry = current[key] ?? AyuCachedProfileFieldsCodable()
            var changed = false

            if let phone, !phone.isEmpty, entry.phone != phone {
                entry.phone = phone
                changed = true
            }
            if let username, !username.isEmpty, entry.username != username {
                entry.username = username
                changed = true
            }
            if let note, !note.isEmpty, entry.note != note {
                entry.note = note
                changed = true
            }

            if changed {
                current[key] = entry
                valueToPersist = current
            }
            return current
        }

        if let valueToPersist, let data = try? JSONEncoder().encode(valueToPersist) {
            UserDefaults.standard.set(data, forKey: defaultsKey)
        }
    }

    static func value(peerId: PeerId) -> AyuCachedProfileFields {
        return state.with { current in
            let entry = current[peerKey(peerId)]
            return AyuCachedProfileFields(phone: entry?.phone, username: entry?.username, note: entry?.note)
        }
    }
}
