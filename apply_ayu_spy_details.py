#!/usr/bin/env python3
from pathlib import Path
import sys

MARK = "AYU_SPY_DETAILS_v0_3"
DB_MARK = "AYU_SPY_QUERY_ROWS_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_spy_details.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()

    # Small read-only query helper for Ayu's own SQLite. This stays in Postbox,
    # beside the existing Database wrapper, and is used only after the user taps Details.
    database_path = root / "submodules/Postbox/Sources/Database.swift"
    text = database_path.read_text(encoding="utf-8")
    if DB_MARK not in text:
        anchor = '''    public func currentError() -> String? {\n'''
        helper = '''    // AYU_SPY_QUERY_ROWS_v0_3\n    public func queryRows(_ SQL: String) -> [[String?]] {\n        var statement: OpaquePointer?\n        guard sqlite3_prepare_v2(self.handle, SQL, -1, &statement, nil) == SQLITE_OK else {\n            return []\n        }\n        defer {\n            sqlite3_finalize(statement)\n        }\n\n        var result: [[String?]] = []\n        while sqlite3_step(statement) == SQLITE_ROW {\n            let count = sqlite3_column_count(statement)\n            var row: [String?] = []\n            row.reserveCapacity(Int(count))\n            for index in 0 ..< count {\n                if sqlite3_column_type(statement, index) == SQLITE_NULL {\n                    row.append(nil)\n                } else if let value = sqlite3_column_text(statement, index) {\n                    let cString = UnsafeRawPointer(value).assumingMemoryBound(to: CChar.self)\n                    row.append(String(cString: cString))\n                } else {\n                    row.append(nil)\n                }\n            }\n            result.append(row)\n        }\n        return result\n    }\n\n'''
        text = one(text, anchor, helper + anchor, "Database queryRows")
    database_path.write_text(text, encoding="utf-8")

    # Normalize all Ayu storage to the app Documents root. Because the app itself
    # is exposed to Files as “AyuGram”, an extra Documents/AyuGram component would
    # otherwise produce “На iPhone/AyuGram/AyuGram”.
    manager_path = root / "submodules/TelegramCore/Sources/State/AccountStateManager.swift"
    text = manager_path.read_text(encoding="utf-8")
    text = text.replace(
        '        let root = documents.appendingPathComponent("AyuGram", isDirectory: true)\n',
        '        let root = documents\n',
        1,
    )

    if MARK not in text:
        anchor = '''private enum AccountStateManagerOperationContent {\n'''
        helper = r'''// AYU_SPY_DETAILS_v0_3
public struct AyuSpyStoredMessageDetails {
    public let deletedAt: Int64?
    public let localReadAt: Int64?

    public init(deletedAt: Int64?, localReadAt: Int64?) {
        self.deletedAt = deletedAt
        self.localReadAt = localReadAt
    }
}

// Two indexed lookups, executed only when the user explicitly opens Details.
// Telegram-provided read timestamps remain preferred in UI; localReadAt is only
// the fallback requested by the Spy setting.
public func ayuSpyStoredMessageDetails(_ messageId: MessageId) -> AyuSpyStoredMessageDetails {
    guard let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else {
        return AyuSpyStoredMessageDetails(deletedAt: nil, localReadAt: nil)
    }
    let databasePath = documents
        .appendingPathComponent("Deleted", isDirectory: true)
        .appendingPathComponent("deleted.sqlite")
        .path
    guard FileManager.default.fileExists(atPath: databasePath), let database = Database(databasePath, readOnly: true) else {
        return AyuSpyStoredMessageDetails(deletedAt: nil, localReadAt: nil)
    }

    let peerId = messageId.peerId.toInt64()
    let deletedRows = database.queryRows("SELECT deleted_at FROM deleted_messages WHERE peer_id = \(peerId) AND message_namespace = \(messageId.namespace) AND message_id = \(messageId.id) LIMIT 1")
    var deletedAt: Int64?
    if let row = deletedRows.first, let value = row.first ?? nil {
        deletedAt = Int64(value)
    }

    var localReadAt: Int64?
    if AyuRuntimeSettings.snapshot.saveReadDates && messageId.peerId.namespace != Namespaces.Peer.CloudChannel {
        let readRows = database.queryRows("SELECT read_at FROM read_receipts WHERE peer_id = \(peerId) AND max_message_id >= \(messageId.id) ORDER BY read_at ASC LIMIT 1")
        if let row = readRows.first, let value = row.first ?? nil {
            localReadAt = Int64(value)
        }
    }

    return AyuSpyStoredMessageDetails(deletedAt: deletedAt, localReadAt: localReadAt)
}

'''
        text = one(text, anchor, helper + anchor, "stored Details helper")
    manager_path.write_text(text, encoding="utf-8")

    # Read-date writer must point to the same exposed Documents/Deleted database.
    state_utils = root / "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift"
    text = state_utils.read_text(encoding="utf-8")
    old_path = '''        let deleted = documents\n            .appendingPathComponent("AyuGram", isDirectory: true)\n            .appendingPathComponent("Deleted", isDirectory: true)\n'''
    new_path = '''        let deleted = documents\n            .appendingPathComponent("Deleted", isDirectory: true)\n'''
    if old_path in text:
        text = text.replace(old_path, new_path, 1)
    state_utils.write_text(text, encoding="utf-8")

    menu_path = root / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"
    text = menu_path.read_text(encoding="utf-8")
    if MARK not in text:
        helper_anchor = '''private struct MessageContextMenuData {\n'''
        menu_helpers = r'''// AYU_SPY_DETAILS_v0_3
private func ayuDetailsDate(_ timestamp: Int64) -> String {
    let formatter = DateFormatter()
    formatter.locale = Locale.current
    formatter.timeZone = TimeZone.current
    formatter.dateFormat = "dd.MM.yy 'в' HH:mm:ss"
    return formatter.string(from: Date(timeIntervalSince1970: TimeInterval(timestamp)))
}

private func ayuDetailsSize(_ bytes: Int64) -> String {
    if bytes >= 1024 * 1024 {
        let mb = Double(bytes) / (1024.0 * 1024.0)
        return String(format: "%.1f МБ", mb)
    } else {
        let kb = Double(bytes) / 1024.0
        let rounded = (kb / 10.0).rounded() * 10.0
        return String(format: "%.0f КБ", rounded)
    }
}

private func ayuDetailsRow(_ text: String) -> ContextMenuItem {
    let emptyAction: ((ContextMenuActionItem.Action) -> Void)? = nil
    return .action(ContextMenuActionItem(text: text, textLayout: .multiline, textFont: .small, icon: { _ in nil }, action: emptyAction))
}

private func ayuDetailsMenuItems(message: EngineRawMessage, stored: AyuSpyStoredMessageDetails, readStats: MessageReadStats?) -> [ContextMenuItem] {
    var items: [ContextMenuItem] = []
    items.append(.action(ContextMenuActionItem(text: "Назад", icon: { _ in nil }, action: { controller, _ in
        controller?.popItems()
    })))
    // Visually detach Back from the informational block, matching Telegram's
    // native nested context-menu layout rather than opening a half-screen sheet.
    items.append(.separator)

    items.append(ayuDetailsRow("ID: \(message.id.id)"))
    items.append(ayuDetailsRow("Дата: \(ayuDetailsDate(Int64(message.timestamp)))"))

    let isOutgoing = !message.flags.contains(.Incoming)
    var telegramReadAt: Int64?
    if AyuRuntimeSettings.snapshot.saveReadDates && isOutgoing, let readStats {
        telegramReadAt = readStats.readTimestamps.values.min().map(Int64.init)
    }
    let effectiveReadAt = telegramReadAt ?? (AyuRuntimeSettings.snapshot.saveReadDates ? stored.localReadAt : nil)

    var didAddMediaDetails = false
    for media in message.media {
        if let image = media as? TelegramMediaImage {
            didAddMediaDetails = true
            items.append(ayuDetailsRow("Тип MIME: image/jpeg"))
            if let representation = largestImageRepresentation(image.representations) {
                items.append(ayuDetailsRow("Разрешение: \(representation.dimensions.width)×\(representation.dimensions.height)"))
            }
        } else if let file = media as? TelegramMediaFile {
            didAddMediaDetails = true
            items.append(ayuDetailsRow("Тип MIME: \(file.mimeType)"))

            var duration: Double?
            var dimensions: PixelDimensions?
            for attribute in file.attributes {
                switch attribute {
                case let .Video(value, size, _, _, _, _):
                    duration = value
                    dimensions = size
                case let .Audio(_, value, _, _, _):
                    duration = Double(value)
                case let .ImageSize(size):
                    if dimensions == nil {
                        dimensions = size
                    }
                default:
                    break
                }
            }

            if let size = file.size {
                items.append(ayuDetailsRow("Размер: \(ayuDetailsSize(size))"))
                if let duration, duration > 0.0 {
                    let bitrate = Int((Double(size) * 8.0 / duration / 1000.0).rounded())
                    items.append(ayuDetailsRow("Битрейт: \(bitrate) Kbps"))
                }
            }
            if let dimensions {
                items.append(ayuDetailsRow("Разрешение: \(dimensions.width)×\(dimensions.height)"))
            }
            if let duration {
                items.append(ayuDetailsRow(String(format: "Длительность: %.1f с", duration)))
            }

            if (file.isVoice || file.isInstantVideo), let effectiveReadAt {
                items.append(ayuDetailsRow("Дата прочтения содержимого: \(ayuDetailsDate(effectiveReadAt))"))
            }
        }
    }

    if !didAddMediaDetails, isOutgoing, let effectiveReadAt {
        items.append(ayuDetailsRow("Время прочтения: \(ayuDetailsDate(effectiveReadAt))"))
    }

    if AyuRuntimeSettings.isDeleted(message.id), let deletedAt = stored.deletedAt {
        items.append(ayuDetailsRow("Дата удаления: \(ayuDetailsDate(deletedAt))"))
    }

    return items
}

'''
        text = one(text, helper_anchor, menu_helpers + helper_anchor, "Details UI helpers")

        return_anchor = '''        return ContextController.Items(content: .list(actions), tip: nil)\n'''
        details_action = r'''        // AYU_SPY_DETAILS_v0_3
        // Always available: the Spy read-date toggle only controls whether read
        // timestamps appear inside Details, not whether the Details entry exists.
        if let ayuDetailsMessage = messages.first {
            if !actions.isEmpty {
                actions.append(.separator)
            }
            actions.append(.action(ContextMenuActionItem(text: "Детали", icon: { theme in
                return generateTintedImage(image: UIImage(bundleImageName: "Chat/Context Menu/Info"), color: theme.actionSheet.primaryTextColor)
            }, action: { controller, _ in
                guard let controller else {
                    return
                }
                let stored = ayuSpyStoredMessageDetails(ayuDetailsMessage.id)
                let detailItems = ayuDetailsMenuItems(message: ayuDetailsMessage, stored: stored, readStats: readStats)
                controller.pushItems(items: .single(ContextController.Items(content: .list(detailItems))))
            })))
        }

'''
        text = one(text, return_anchor, details_action + return_anchor, "Details context action")
    menu_path.write_text(text, encoding="utf-8")

    print("[ayu-spy-details] nested Details context menu + DB fallback + root storage normalization installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
