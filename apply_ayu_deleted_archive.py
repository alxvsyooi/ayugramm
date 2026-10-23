#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

MARK = "AYU_DELETED_ARCHIVE_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_deleted_archive.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramCore/Sources/State/AccountStateManager.swift"
    if not path.exists():
        raise RuntimeError(f"missing Telegram source: {path}")

    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print(f"[ayu-deleted-archive] already patched: {path}")
        return 0

    class_anchor = "private enum AccountStateManagerOperationContent {\n"
    helpers = r'''// AYU_DELETED_ARCHIVE_v0_3
// Deleted archive is entirely event-driven. The chat/render path never touches
// the filesystem or database. A tiny immutable snapshot is made only when a
// remote delete update arrives; SQLite and attachment copies run on one serial
// background queue.
private struct AyuDeletedArchiveAttachment {
    let kind: String
    let resource: MediaResource
    let fileExtension: String
}

private struct AyuDeletedArchiveSnapshot {
    let peerId: Int64
    let messageNamespace: Int32
    let messageId: Int32
    let chatTitle: String
    let chatUsername: String
    let authorId: Int64?
    let messageTimestamp: Int32
    let deletedAt: Int64
    let text: String
    let attachments: [AyuDeletedArchiveAttachment]
}

private final class AyuDeletedArchive {
    static let shared = AyuDeletedArchive()

    private let queue = Queue(name: "ayu.deleted.archive")
    private var database: Database?
    private var rootPath: String?

    private init() {
    }

    private func sql(_ value: String) -> String {
        return "'" + value.replacingOccurrences(of: "'", with: "''") + "'"
    }

    private func safeName(_ value: String) -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_."))
        return value.unicodeScalars.map { allowed.contains($0) ? String($0) : "_" }.joined()
    }

    private func prepare() -> (String, Database)? {
        if let rootPath = self.rootPath, let database = self.database {
            return (rootPath, database)
        }
        guard let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else {
            return nil
        }

        // Keep the Ayu archive directly under the app's Documents directory so
        // Files shows a simple Documents/AyuGram layout without an extra Downloads layer.
        let root = documents.appendingPathComponent("AyuGram", isDirectory: true)
        let deleted = root.appendingPathComponent("Deleted", isDirectory: true)
        let saved = root.appendingPathComponent("Saved attachments", isDirectory: true)
        let photos = saved.appendingPathComponent("Photos", isDirectory: true)
        let voice = saved.appendingPathComponent("Voice", isDirectory: true)
        let videoMessages = saved.appendingPathComponent("Video Messages", isDirectory: true)

        for directory in [root, deleted, saved, photos, voice, videoMessages] {
            try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        }

        let databasePath = deleted.appendingPathComponent("deleted.sqlite").path
        guard let database = Database(databasePath, readOnly: false) else {
            return nil
        }
        _ = database.execute("PRAGMA journal_mode=WAL")
        _ = database.execute("PRAGMA synchronous=NORMAL")
        _ = database.execute("CREATE TABLE IF NOT EXISTS deleted_messages (peer_id INTEGER NOT NULL, message_namespace INTEGER NOT NULL, message_id INTEGER NOT NULL, chat_title TEXT NOT NULL, chat_username TEXT NOT NULL, author_id INTEGER, message_timestamp INTEGER NOT NULL, deleted_at INTEGER NOT NULL, text TEXT NOT NULL, PRIMARY KEY(peer_id, message_namespace, message_id))")
        _ = database.execute("CREATE TABLE IF NOT EXISTS attachments (peer_id INTEGER NOT NULL, message_namespace INTEGER NOT NULL, message_id INTEGER NOT NULL, resource_id TEXT NOT NULL, kind TEXT NOT NULL, relative_path TEXT, local_saved INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(peer_id, message_namespace, message_id, resource_id))")
        _ = database.execute("CREATE INDEX IF NOT EXISTS deleted_messages_deleted_at_idx ON deleted_messages(deleted_at DESC)")
        _ = database.execute("CREATE INDEX IF NOT EXISTS deleted_messages_peer_idx ON deleted_messages(peer_id, message_timestamp DESC)")

        self.rootPath = root.path
        self.database = database
        return (root.path, database)
    }

    func enqueue(message: Message, peer: Peer?, mediaBox: MediaBox) {
        var attachments: [AyuDeletedArchiveAttachment] = []
        for media in message.media {
            if let image = media as? TelegramMediaImage, let representation = largestImageRepresentation(image.representations) {
                attachments.append(AyuDeletedArchiveAttachment(kind: "photo", resource: representation.resource, fileExtension: "jpg"))
            } else if let file = media as? TelegramMediaFile, file.isVoice {
                attachments.append(AyuDeletedArchiveAttachment(kind: "voice", resource: file.resource, fileExtension: "ogg"))
            } else if let file = media as? TelegramMediaFile, file.isInstantVideo {
                attachments.append(AyuDeletedArchiveAttachment(kind: "video_message", resource: file.resource, fileExtension: "mp4"))
            }
        }

        let snapshot = AyuDeletedArchiveSnapshot(
            peerId: message.id.peerId.toInt64(),
            messageNamespace: message.id.namespace,
            messageId: message.id.id,
            chatTitle: peer?.debugDisplayTitle ?? "",
            chatUsername: peer?.addressName ?? "",
            authorId: message.author?.id.toInt64(),
            messageTimestamp: message.timestamp,
            deletedAt: Int64(Date().timeIntervalSince1970),
            text: message.text,
            attachments: attachments
        )

        self.queue.async { [weak self] in
            self?.store(snapshot: snapshot, mediaBox: mediaBox)
        }
    }

    private func store(snapshot: AyuDeletedArchiveSnapshot, mediaBox: MediaBox) {
        guard let (_, database) = self.prepare() else {
            return
        }

        let authorSql = snapshot.authorId.map(String.init) ?? "NULL"
        _ = database.execute("INSERT OR REPLACE INTO deleted_messages(peer_id, message_namespace, message_id, chat_title, chat_username, author_id, message_timestamp, deleted_at, text) VALUES (\(snapshot.peerId), \(snapshot.messageNamespace), \(snapshot.messageId), \(self.sql(snapshot.chatTitle)), \(self.sql(snapshot.chatUsername)), \(authorSql), \(snapshot.messageTimestamp), \(snapshot.deletedAt), \(self.sql(snapshot.text)))")

        for attachment in snapshot.attachments {
            let resourceId = attachment.resource.id.stringRepresentation
            _ = database.execute("INSERT OR IGNORE INTO attachments(peer_id, message_namespace, message_id, resource_id, kind, relative_path, local_saved) VALUES (\(snapshot.peerId), \(snapshot.messageNamespace), \(snapshot.messageId), \(self.sql(resourceId)), \(self.sql(attachment.kind)), NULL, 0)")

            // Do not auto-download deleted media and do not leave long-lived
            // resource watchers. Take exactly one MediaBox snapshot; if the media
            // is already local, copy it on the archive queue. Otherwise metadata is
            // still kept in SQLite and the retained Telegram message remains usable.
            let _ = (mediaBox.resourceData(attachment.resource)
            |> take(1)).start(next: { [weak self] data in
                guard let self, data.complete else {
                    return
                }
                self.queue.async {
                    guard let (rootPath, database) = self.prepare() else {
                        return
                    }
                    let subdirectory: String
                    switch attachment.kind {
                    case "photo":
                        subdirectory = "Photos"
                    case "voice":
                        subdirectory = "Voice"
                    default:
                        subdirectory = "Video Messages"
                    }
                    let safeResource = self.safeName(resourceId)
                    let filename = "\(snapshot.peerId)_\(snapshot.messageNamespace)_\(snapshot.messageId)_\(safeResource).\(attachment.fileExtension)"
                    let relative = "Saved attachments/\(subdirectory)/\(filename)"
                    let destination = (rootPath as NSString).appendingPathComponent(relative)
                    if !FileManager.default.fileExists(atPath: destination) {
                        let temp = destination + ".tmp-" + UUID().uuidString
                        do {
                            try FileManager.default.copyItem(atPath: data.path, toPath: temp)
                            if FileManager.default.fileExists(atPath: destination) {
                                try? FileManager.default.removeItem(atPath: temp)
                            } else {
                                try FileManager.default.moveItem(atPath: temp, toPath: destination)
                            }
                        } catch {
                            try? FileManager.default.removeItem(atPath: temp)
                            return
                        }
                    }
                    _ = database.execute("UPDATE attachments SET relative_path = \(self.sql(relative)), local_saved = 1 WHERE peer_id = \(snapshot.peerId) AND message_namespace = \(snapshot.messageNamespace) AND message_id = \(snapshot.messageId) AND resource_id = \(self.sql(resourceId))")
                }
            })
        }
    }
}

'''
    text = one(text, class_anchor, helpers + class_anchor, "archive helpers")

    loop_anchor = """                for id in resolvedMessageIds {\n                    guard touched.insert(id).inserted else {\n                        continue\n                    }\n                    transaction.updateMessage(id, update: { currentMessage in\n"""
    loop_new = """                for id in resolvedMessageIds {\n                    guard touched.insert(id).inserted else {\n                        continue\n                    }\n                    let ayuArchivePeer = transaction.getPeer(id.peerId)\n                    transaction.updateMessage(id, update: { currentMessage in\n                        AyuDeletedArchive.shared.enqueue(message: currentMessage, peer: ayuArchivePeer, mediaBox: self.postbox.mediaBox)\n"""
    text = one(text, loop_anchor, loop_new, "deleted archive event hook")

    path.write_text(text, encoding="utf-8")
    print("[ayu-deleted-archive] Documents/AyuGram archive + SQLite metadata installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
