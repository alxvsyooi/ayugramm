#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_account_state_manager(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    old = """        func addUpdates(_ updates: Api.Updates) {\n            self.queue.async {\n                self.updateService?.addUpdates(updates)\n            }\n        }\n"""

    new = r'''        // AYU_IOS_DELETED_REALTIME_v0_3: keep the normal Postbox-driven UI
        // update path even though remote deletes themselves are suppressed. This is
        // event-driven: work happens only when Telegram receives a delete update.
        private func ayuRefreshPreservedDeletedMessages(_ updates: Api.Updates) {
            guard AyuRuntimeSettings.keepDeletedMessages else {
                return
            }

            var globalIds: [Int32] = []
            var messageIds: [MessageId] = []

            func collect(_ update: Api.Update) {
                switch update {
                case let .updateDeleteMessages(data):
                    globalIds.append(contentsOf: data.messages)
                case let .updateDeleteChannelMessages(data):
                    let peerId = PeerId(namespace: Namespaces.Peer.CloudChannel, id: PeerId.Id._internalFromInt64Value(data.channelId))
                    messageIds.append(contentsOf: data.messages.map {
                        MessageId(peerId: peerId, namespace: Namespaces.Message.Cloud, id: $0)
                    })
                default:
                    break
                }
            }

            switch updates {
            case let .updates(data):
                for update in data.updates {
                    collect(update)
                }
            case let .updatesCombined(data):
                for update in data.updates {
                    collect(update)
                }
            case let .updateShort(data):
                collect(data.update)
            case .updateShortChatMessage, .updateShortMessage, .updateShortSentMessage, .updatesTooLong:
                break
            }

            guard !globalIds.isEmpty || !messageIds.isEmpty else {
                return
            }

            // Mark first, before touching Postbox, so the normal chat relayout sees
            // the deleted state on its very first refresh.
            AyuRuntimeSettings.markDeletedGlobalIds(globalIds)
            AyuRuntimeSettings.markDeletedMessageIds(messageIds)

            let directMessageIds = messageIds
            let _ = (self.postbox.transaction { transaction -> [DeletedMessageId] in
                var resolvedMessageIds = directMessageIds
                if !globalIds.isEmpty {
                    let resolvedGlobalIds = transaction.messageIdsForGlobalIds(globalIds)
                    if !resolvedGlobalIds.isEmpty {
                        resolvedMessageIds.append(contentsOf: resolvedGlobalIds)
                        AyuRuntimeSettings.markDeletedMessageIds(resolvedGlobalIds)
                    }
                }

                // Keep the early raw-update invalidation for the fastest common path.
                // A second guaranteed invalidation is performed from final-state events
                // below, after Telegram has fully processed the update/difference.
                var touched = Set<MessageId>()
                for id in resolvedMessageIds {
                    guard touched.insert(id).inserted else {
                        continue
                    }
                    transaction.updateMessage(id, update: { currentMessage in
                        return .update(StoreMessage(
                            id: currentMessage.id,
                            customStableId: nil,
                            globallyUniqueId: currentMessage.globallyUniqueId,
                            groupingKey: currentMessage.groupingKey,
                            threadId: currentMessage.threadId,
                            timestamp: currentMessage.timestamp,
                            flags: StoreMessageFlags(currentMessage.flags),
                            tags: currentMessage.tags,
                            globalTags: currentMessage.globalTags,
                            localTags: currentMessage.localTags,
                            forwardInfo: currentMessage.forwardInfo.flatMap(StoreMessageForwardInfo.init),
                            authorId: currentMessage.author?.id,
                            text: currentMessage.text,
                            attributes: currentMessage.attributes,
                            media: currentMessage.media
                        ))
                    })
                }

                var deletedEvents = globalIds.map { DeletedMessageId.global($0) }
                deletedEvents.append(contentsOf: directMessageIds.map { DeletedMessageId.messageId($0) })
                return deletedEvents
            }
            |> deliverOn(self.queue)).start(next: { [weak self] deletedEvents in
                guard let self, !deletedEvents.isEmpty else {
                    return
                }
                self.deletedMessagesPipe.putNext(deletedEvents)
            })
        }

        // AYU_IOS_DELETED_REALTIME_FINAL_v0_3
        // Raw addUpdates is not the only source of deletions: gaps/differences and
        // channel synchronization can produce them later through AccountFinalStateEvents.
        // Refresh from that canonical event too. This guarantees that the visible
        // message changes immediately without a long-press or reopening the chat.
        private func ayuRefreshPreservedDeletedEventIds(_ deletedIds: [DeletedMessageId]) {
            guard AyuRuntimeSettings.keepDeletedMessages, !deletedIds.isEmpty else {
                return
            }

            var globalIds: [Int32] = []
            var directMessageIds: [MessageId] = []
            for id in deletedIds {
                switch id {
                case let .global(globalId):
                    globalIds.append(globalId)
                case let .messageId(messageId):
                    directMessageIds.append(messageId)
                }
            }

            AyuRuntimeSettings.markDeletedGlobalIds(globalIds)
            AyuRuntimeSettings.markDeletedMessageIds(directMessageIds)

            let _ = self.postbox.transaction { transaction -> Void in
                var resolvedMessageIds = directMessageIds
                if !globalIds.isEmpty {
                    let resolvedGlobalIds = transaction.messageIdsForGlobalIds(globalIds)
                    if !resolvedGlobalIds.isEmpty {
                        resolvedMessageIds.append(contentsOf: resolvedGlobalIds)
                        AyuRuntimeSettings.markDeletedMessageIds(resolvedGlobalIds)
                    }
                }

                var touched = Set<MessageId>()
                // Keep this loop structurally distinct from the raw-update loop above:
                // apply_ayu_deleted_archive.py intentionally hooks the raw loop only.
                for messageId in resolvedMessageIds {
                    guard touched.insert(messageId).inserted else {
                        continue
                    }
                    transaction.updateMessage(messageId, update: { currentMessage in
                        // Toggle one private local tag bit instead of re-storing an
                        // identical message. Postbox therefore cannot coalesce this
                        // update and every active history view receives a real change.
                        let ayuRefreshTag = LocalMessageTags(rawValue: 1 << 29)
                        var ayuLocalTags = currentMessage.localTags
                        if ayuLocalTags.contains(ayuRefreshTag) {
                            ayuLocalTags.remove(ayuRefreshTag)
                        } else {
                            ayuLocalTags.insert(ayuRefreshTag)
                        }
                        return .update(StoreMessage(
                            id: currentMessage.id,
                            customStableId: nil,
                            globallyUniqueId: currentMessage.globallyUniqueId,
                            groupingKey: currentMessage.groupingKey,
                            threadId: currentMessage.threadId,
                            timestamp: currentMessage.timestamp,
                            flags: StoreMessageFlags(currentMessage.flags),
                            tags: currentMessage.tags,
                            globalTags: currentMessage.globalTags,
                            localTags: ayuLocalTags,
                            forwardInfo: currentMessage.forwardInfo.flatMap(StoreMessageForwardInfo.init),
                            authorId: currentMessage.author?.id,
                            text: currentMessage.text,
                            attributes: currentMessage.attributes,
                            media: currentMessage.media
                        ))
                    })
                }
            }.start()
        }

        func addUpdates(_ updates: Api.Updates) {
            self.queue.async {
                self.ayuRefreshPreservedDeletedMessages(updates)
                self.updateService?.addUpdates(updates)
            }
        }
'''

    text = replace_once(text, old, new, "AccountStateManager.addUpdates")

    old_events = """                if !events.deletedMessageIds.isEmpty {\n                    self.deletedMessagesPipe.putNext(events.deletedMessageIds)\n                }\n"""
    new_events = """                if !events.deletedMessageIds.isEmpty {\n                    self.deletedMessagesPipe.putNext(events.deletedMessageIds)\n                    self.ayuRefreshPreservedDeletedEventIds(events.deletedMessageIds)\n                }\n"""
    text = replace_once(text, old_events, new_events, "AccountFinalStateEvents.deletedMessageIds")

    path.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_deleted_realtime.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramCore/Sources/State/AccountStateManager.swift"
    if not path.exists():
        raise RuntimeError(f"missing Telegram source: {path}")

    patch_account_state_manager(path)
    print("[ayu-deleted-realtime] raw + final-state event refresh installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
