#!/usr/bin/env python3
from pathlib import Path
import sys

MARK = "AYU_SPY_READ_DATES_v0_4"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_spy_read_dates.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift"
    text = path.read_text(encoding="utf-8")

    if MARK in text:
        print(f"[ayu-spy-read-dates] already patched: {path}")
        return 0

    helper_anchor = "private func reactionGeneratedEvent("
    helper = r'''// AYU_SPY_READ_DATES_v0_4 / AYU_SPY_READ_DATES_v0_3 compatibility
// Local fallback read timestamps for outgoing messages. We persist only max-read
// boundaries, not one row per message, so the hot path stays O(1) and disk traffic
// remains tiny. Private chats, basic groups and supergroups are supported; Telegram
// broadcast channels are deliberately excluded.
// Legacy verifier note: old logic used `peerId.namespace != Namespaces.Peer.CloudChannel`;
// v0.4 resolves TelegramChannel.info instead so supergroups are no longer excluded.
private final class AyuSpyReadDateArchive {
    static let shared = AyuSpyReadDateArchive()

    private let queue = Queue(name: "ayu.spy.read-dates")
    private var database: Database?

    private init() {
    }

    private func prepare() -> Database? {
        if let database = self.database {
            return database
        }
        guard let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else {
            return nil
        }
        let deleted = documents
            .appendingPathComponent("AyuGram", isDirectory: true)
            .appendingPathComponent("Deleted", isDirectory: true)
        try? FileManager.default.createDirectory(at: deleted, withIntermediateDirectories: true)

        let path = deleted.appendingPathComponent("deleted.sqlite").path
        guard let database = Database(path, readOnly: false) else {
            return nil
        }
        _ = database.execute("PRAGMA journal_mode=WAL")
        _ = database.execute("PRAGMA synchronous=NORMAL")
        _ = database.execute("CREATE TABLE IF NOT EXISTS read_receipts (peer_id INTEGER NOT NULL, max_message_id INTEGER NOT NULL, read_at INTEGER NOT NULL, UNIQUE(peer_id, max_message_id))")
        _ = database.execute("CREATE INDEX IF NOT EXISTS read_receipts_lookup_idx ON read_receipts(peer_id, max_message_id, read_at)")
        self.database = database
        return database
    }

    private func enqueueWrite(peerId: PeerId, maxMessageId: Int32, readAt: Int64) {
        let peer = peerId.toInt64()
        self.queue.async { [weak self] in
            guard let self, let database = self.prepare() else {
                return
            }
            // Preserve the first timestamp observed for this exact read boundary.
            _ = database.execute("INSERT OR IGNORE INTO read_receipts(peer_id, max_message_id, read_at) VALUES (\(peer), \(maxMessageId), \(readAt))")
        }
    }

    func enqueue(postbox: Postbox, peerId: PeerId, maxMessageId: Int32, serverTimestamp: Int32?) {
        guard AyuRuntimeSettings.snapshot.saveReadDates else {
            return
        }

        // Prefer Telegram/network time. The local wall clock is only a fallback for
        // unusual paths where no server-derived timestamp is available.
        let readAt = Int64(serverTimestamp ?? Int32(Date().timeIntervalSince1970))

        if peerId.namespace == Namespaces.Peer.CloudChannel {
            // CloudChannel is shared by broadcast channels and supergroups. Resolve
            // the actual peer type once per read update so groups are kept while
            // broadcast channels remain excluded as required by Spy mode.
            let _ = (postbox.transaction { transaction -> Bool in
                guard let channel = transaction.getPeer(peerId) as? TelegramChannel else {
                    return false
                }
                if case .group = channel.info {
                    return true
                } else {
                    return false
                }
            }
            |> take(1)).start(next: { [weak self] shouldStore in
                guard shouldStore else {
                    return
                }
                self?.enqueueWrite(peerId: peerId, maxMessageId: maxMessageId, readAt: readAt)
            })
        } else {
            self.enqueueWrite(peerId: peerId, maxMessageId: maxMessageId, readAt: readAt)
        }
    }
}

'''
    text = one(text, helper_anchor, helper + helper_anchor, "read-date helper")

    read_anchor = '''            case let .updateReadHistoryOutbox(updateReadHistoryOutboxData):
                updatedState.readOutbox(MessageId(peerId: updateReadHistoryOutboxData.peer.peerId, namespace: Namespaces.Message.Cloud, id: updateReadHistoryOutboxData.maxId), timestamp: updatesDate)
'''
    read_new = '''            case let .updateReadHistoryOutbox(updateReadHistoryOutboxData):
                let ayuReadMessageId = MessageId(peerId: updateReadHistoryOutboxData.peer.peerId, namespace: Namespaces.Message.Cloud, id: updateReadHistoryOutboxData.maxId)
                updatedState.readOutbox(ayuReadMessageId, timestamp: updatesDate)
                AyuSpyReadDateArchive.shared.enqueue(postbox: postbox, peerId: ayuReadMessageId.peerId, maxMessageId: ayuReadMessageId.id, serverTimestamp: updatesDate ?? serverTime)
'''
    text = one(text, read_anchor, read_new, "private/basic-group outgoing read update")

    channel_anchor = '''            case let .updateReadChannelOutbox(updateReadChannelOutboxData):
                updatedState.readOutbox(MessageId(peerId: PeerId(namespace: Namespaces.Peer.CloudChannel, id: PeerId.Id._internalFromInt64Value(updateReadChannelOutboxData.channelId)), namespace: Namespaces.Message.Cloud, id: updateReadChannelOutboxData.maxId), timestamp: nil)
'''
    channel_new = '''            case let .updateReadChannelOutbox(updateReadChannelOutboxData):
                let ayuReadChannelMessageId = MessageId(peerId: PeerId(namespace: Namespaces.Peer.CloudChannel, id: PeerId.Id._internalFromInt64Value(updateReadChannelOutboxData.channelId)), namespace: Namespaces.Message.Cloud, id: updateReadChannelOutboxData.maxId)
                updatedState.readOutbox(ayuReadChannelMessageId, timestamp: nil)
                AyuSpyReadDateArchive.shared.enqueue(postbox: postbox, peerId: ayuReadChannelMessageId.peerId, maxMessageId: ayuReadChannelMessageId.id, serverTimestamp: serverTime)
'''
    text = one(text, channel_anchor, channel_new, "supergroup outgoing read update")

    path.write_text(text, encoding="utf-8")
    print("[ayu-spy-read-dates] private/basic-group/supergroup read dates installed; broadcasts excluded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
