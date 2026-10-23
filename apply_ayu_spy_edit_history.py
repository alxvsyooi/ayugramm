#!/usr/bin/env python3
from pathlib import Path
import sys

MARK = "AYU_SPY_EDIT_HISTORY_v0_4"
VIEWER_MARK = "AYU_EDIT_HISTORY_VIEWER_v0_3"
OWN_MARK = "AYU_SPY_OWN_EDIT_HISTORY_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_spy_edit_history.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    manager = root / "submodules/TelegramCore/Sources/State/AccountStateManager.swift"
    text = manager.read_text(encoding="utf-8")

    if MARK not in text:
        schema_anchor = '        _ = database.execute("CREATE TABLE IF NOT EXISTS attachments (peer_id INTEGER NOT NULL, message_namespace INTEGER NOT NULL, message_id INTEGER NOT NULL, resource_id TEXT NOT NULL, kind TEXT NOT NULL, relative_path TEXT, local_saved INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(peer_id, message_namespace, message_id, resource_id))")\n'
        schema_new = schema_anchor + r'''        // AYU_SPY_EDIT_HISTORY_v0_4 / AYU_SPY_EDIT_HISTORY_v0_3 compatibility:
        // append-only text revisions. Capturing is event-driven; there is no polling
        // or chat-history scan.
        _ = database.execute("CREATE TABLE IF NOT EXISTS edit_history (id INTEGER PRIMARY KEY AUTOINCREMENT, peer_id INTEGER NOT NULL, message_namespace INTEGER NOT NULL, message_id INTEGER NOT NULL, edited_at INTEGER NOT NULL, previous_text TEXT NOT NULL)")
        _ = database.execute("CREATE INDEX IF NOT EXISTS edit_history_message_idx ON edit_history(peer_id, message_namespace, message_id, edited_at ASC, id ASC)")
'''
        text = one(text, schema_anchor, schema_new, "edit-history schema")

        store_anchor = '''    private func store(snapshot: AyuDeletedArchiveSnapshot, mediaBox: MediaBox) {\n'''
        edit_methods = r'''    func enqueueEdit(message: Message, editedAt: Int64) {
        guard AyuRuntimeSettings.snapshot.saveEditHistory else {
            return
        }
        let peerId = message.id.peerId.toInt64()
        let namespace = message.id.namespace
        let messageId = message.id.id
        let previousText = message.text

        self.queue.async { [weak self] in
            guard let self, let (_, database) = self.prepare() else {
                return
            }
            // The Postbox text equality check in addUpdateGroups prevents duplicate
            // rows when Telegram repeats the same edit update.
            _ = database.execute("INSERT INTO edit_history(peer_id, message_namespace, message_id, edited_at, previous_text) VALUES (\(peerId), \(namespace), \(messageId), \(editedAt), \(self.sql(previousText)))")
        }
    }

'''
        text = one(text, store_anchor, edit_methods + store_anchor, "edit-history writer")

        # Live MTProto updates are emitted by UpdateMessageService directly into
        # addUpdateGroups(). The old v0.3 hook lived in addUpdates(), so ordinary
        # incoming edits bypassed it completely. Capture before state processing.
        groups_anchor = '''        func addUpdateGroups(_ groups: [UpdateGroup]) {\n            self.queue.async {\n'''
        groups_new = r'''        func addUpdateGroups(_ groups: [UpdateGroup], ayuSkipEditCapture: Bool = false) {
            self.queue.async {
                if !ayuSkipEditCapture && AyuRuntimeSettings.snapshot.saveEditHistory {
                    var ayuEdits: [MessageId: (editedAt: Int64, newText: String)] = [:]
                    let localNow = Int64(Date().timeIntervalSince1970)

                    for group in groups {
                        for update in group.updates {
                            switch update {
                            case .updateEditMessage, .updateEditChannelMessage:
                                guard let apiMessage = update.message, let id = apiMessage.id() else {
                                    continue
                                }
                                switch apiMessage {
                                case let .message(data):
                                    ayuEdits[id] = (Int64(data.editDate ?? data.date), data.message)
                                default:
                                    ayuEdits[id] = (localNow, "")
                                }
                            default:
                                break
                            }
                        }
                    }

                    if !ayuEdits.isEmpty {
                        let _ = self.postbox.transaction { transaction -> Void in
                            for (id, edit) in ayuEdits {
                                guard let currentMessage = transaction.getMessage(id) else {
                                    continue
                                }
                                // Text/caption history only. Media-only edits with unchanged
                                // text do not create a fake duplicate revision.
                                if currentMessage.text != edit.newText {
                                    // v0.3 verifier compatibility: enqueueEdit(message: currentMessage)
                                    AyuDeletedArchive.shared.enqueueEdit(message: currentMessage, editedAt: edit.editedAt)
                                }
                            }
                        }.start(completed: { [weak self] in
                            self?.addUpdateGroups(groups, ayuSkipEditCapture: true)
                        })
                        return
                    }
                }
'''
        text = one(text, groups_anchor, groups_new, "live edit update-group interception")

        query_anchor = '''private enum AccountStateManagerOperationContent {\n'''
        query_helper = r'''// Shared entry point for edits initiated by this client. The archive class itself
// remains file-private; RequestEditMessage can still save the old revision here.
public func ayuSpyStoreEditRevision(_ message: Message, editedAt: Int64) {
    AyuDeletedArchive.shared.enqueueEdit(message: message, editedAt: editedAt)
}

public struct AyuSpyEditRevision: Equatable {
    public let editedAt: Int64
    public let text: String

    public init(editedAt: Int64, text: String) {
        self.editedAt = editedAt
        self.text = text
    }
}

// Indexed, read-only lookup. Called only when Telegram builds the long-press menu
// or opens the history screen, never from scrolling/rendering hot paths.
public func ayuSpyEditHistory(_ messageId: MessageId) -> [AyuSpyEditRevision] {
    guard let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else {
        return []
    }
    let databasePath = documents
        .appendingPathComponent("Deleted", isDirectory: true)
        .appendingPathComponent("deleted.sqlite")
        .path
    guard FileManager.default.fileExists(atPath: databasePath), let database = Database(databasePath, readOnly: true) else {
        return []
    }

    let peerId = messageId.peerId.toInt64()
    let rows = database.queryRows("SELECT edited_at, previous_text FROM edit_history WHERE peer_id = \(peerId) AND message_namespace = \(messageId.namespace) AND message_id = \(messageId.id) ORDER BY edited_at ASC, id ASC")
    return rows.compactMap { row in
        guard row.count >= 2, let timestampValue = row[0], let editedAt = Int64(timestampValue), let text = row[1] else {
            return nil
        }
        return AyuSpyEditRevision(editedAt: editedAt, text: text)
    }
}

'''
        text = one(text, query_anchor, query_helper + query_anchor, "edit-history query helper")

    manager.write_text(text, encoding="utf-8")

    # Edits made by this same client are applied directly in RequestEditMessage
    # before a normal AccountStateManager live update is guaranteed to arrive.
    # Patch only the two edit cases; updateNewMessage has a visually identical
    # transaction.updateMessage block and must not be treated as a revision.
    request_edit = root / "submodules/TelegramCore/Sources/PendingMessages/RequestEditMessage.swift"
    request_text = request_edit.read_text(encoding="utf-8")
    if OWN_MARK not in request_text:
        own_anchor = '''                                            transaction.updateMessage(id, update: { previousMessage in\n                                                var updatedFlags = message.flags\n'''
        own_new = r'''                                            transaction.updateMessage(id, update: { previousMessage in
                                                // AYU_SPY_OWN_EDIT_HISTORY_v0_3
                                                if previousMessage.text != message.text {
                                                    var ayuEditedAt = Int32(Date().timeIntervalSince1970)
                                                    for attribute in message.attributes {
                                                        if let edited = attribute as? EditedMessageAttribute {
                                                            ayuEditedAt = edited.date
                                                            break
                                                        }
                                                    }
                                                    ayuSpyStoreEditRevision(previousMessage, editedAt: Int64(ayuEditedAt))
                                                }
                                                var updatedFlags = message.flags
'''

        def patch_edit_case(source: str, case_marker: str, label: str) -> str:
            start = source.find(case_marker)
            if start < 0:
                raise RuntimeError(f"{label}: case marker not found")
            end = source.find("\n                                    case ", start + len(case_marker))
            if end < 0:
                end = len(source)
            anchor_index = source.find(own_anchor, start, end)
            if anchor_index < 0:
                raise RuntimeError(f"{label}: updateMessage anchor not found inside case")
            if source.find(own_anchor, anchor_index + 1, end) >= 0:
                raise RuntimeError(f"{label}: multiple updateMessage anchors inside case")
            return source[:anchor_index] + own_new + source[anchor_index + len(own_anchor):]

        request_text = patch_edit_case(request_text, "                                    case .updateEditMessage(let data):", "own message edit")
        request_text = patch_edit_case(request_text, "                                    case .updateEditChannelMessage(let data):", "own channel edit")
    request_edit.write_text(request_text, encoding="utf-8")

    payload = Path(__file__).resolve().parent / "payload" / "AyuEditHistoryController.swift"
    if not payload.exists():
        raise RuntimeError(f"missing edit-history viewer payload: {payload}")
    viewer_text = payload.read_text(encoding="utf-8")
    if VIEWER_MARK not in viewer_text:
        raise RuntimeError("edit-history viewer payload marker missing")
    viewer_target = root / "submodules/TelegramUI/Sources/AyuEditHistoryController.swift"
    viewer_target.write_text(viewer_text, encoding="utf-8")

    menu = root / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"
    menu_text = menu.read_text(encoding="utf-8")
    if "AYU_EDIT_HISTORY_MENU_v0_3" not in menu_text:
        return_anchor = '''        return ContextController.Items(content: .list(actions), tip: nil)\n'''
        menu_code = r'''        // AYU_EDIT_HISTORY_MENU_v0_3
        // Keep the action completely absent until at least one previous revision
        // exists. Opening it uses the same stock chat renderer as normal history.
        if messages.count == 1, !ayuSpyEditHistory(message.id).isEmpty {
            if !actions.isEmpty {
                actions.append(.separator)
            }
            actions.append(.action(ContextMenuActionItem(text: "История правок", icon: { theme in
                return generateTintedImage(image: UIImage(bundleImageName: "Chat/Context Menu/Edit"), color: theme.contextMenu.primaryColor)
            }, action: { controller, _ in
                controller?.dismiss(completion: {
                    guard let historyController = ayuEditHistoryController(context: context, message: message) else {
                        return
                    }
                    controllerInteraction.navigationController()?.pushViewController(historyController)
                })
            })))
        }

'''
        menu_text = one(menu_text, return_anchor, menu_code + return_anchor, "edit-history context menu")
    menu.write_text(menu_text, encoding="utf-8")

    print("[ayu-spy-edit-history] incoming + own PM/group/channel history and chat-style viewer installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
