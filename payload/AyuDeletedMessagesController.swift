import Foundation
import UIKit
import Display
import SwiftSignalKit
import TelegramCore
import AccountContext
import Postbox

/// Read-only chat-like history that reuses Telegram's stock message renderer.
/// Deleted messages remain real Postbox messages, so replies/media/bubbles keep
/// the exact same layout as the ordinary chat. The only difference is that this
/// view filters the history to Ayu-marked ids and renders them at full opacity.
final class AyuDeletedMessagesChatContents: ChatCustomContentsProtocol {
    private final class Impl {
        let queue: Queue
        let context: AccountContext
        let peerId: PeerId

        private var disposable: Disposable?
        private(set) var currentHistoryView: EngineRawMessageHistoryView?
        let historyViewStream = ValuePipe<(EngineRawMessageHistoryView, EngineViewUpdateType)>()

        init(queue: Queue, context: AccountContext, peerId: PeerId) {
            self.queue = queue
            self.context = context
            self.peerId = peerId
            self.reload()
        }

        deinit {
            self.disposable?.dispose()
        }

        private func emptyView() -> EngineRawMessageHistoryView {
            return EngineRawMessageHistoryView(
                tag: nil,
                namespaces: .just(Set([Namespaces.Message.Cloud])),
                entries: [],
                holeEarlier: false,
                holeLater: false,
                isLoading: false
            )
        }

        func reload() {
            self.disposable?.dispose()

            let ids = AyuRuntimeSettings.deletedMessageIds(peerId: self.peerId)
            guard !ids.isEmpty else {
                let view = self.emptyView()
                self.currentHistoryView = view
                self.historyViewStream.putNext((view, .Initial))
                return
            }

            self.disposable = (self.context.engine.data.get(
                EngineDataList(ids.map(TelegramEngine.EngineData.Item.Messages.Message.init(id:)))
            )
            |> deliverOn(self.queue)).start(next: { [weak self] result in
                guard let self else {
                    return
                }

                let messages = result.compactMap { $0 }.sorted(by: { lhs, rhs in
                    return lhs.index < rhs.index
                })
                let entries = messages.map { message in
                    return EngineRawMessageHistoryEntry(
                        message: message._asMessage(),
                        isRead: true,
                        location: nil,
                        monthLocation: nil,
                        attributes: EngineRawMutableMessageHistoryEntryAttributes(authorIsContact: false)
                    )
                }
                let view = EngineRawMessageHistoryView(
                    tag: nil,
                    namespaces: .just(Set([Namespaces.Message.Cloud])),
                    entries: entries,
                    holeEarlier: false,
                    holeLater: false,
                    isLoading: false
                )
                self.currentHistoryView = view
                self.historyViewStream.putNext((view, .Initial))
            })
        }

        func enqueueMessages(messages: [EnqueueMessage]) {
        }

        func deleteMessages(ids: [EngineMessage.Id]) {
        }

        func editMessage(id: EngineMessage.Id, text: String, media: RequestEditMessageMedia, entities: TextEntitiesMessageAttribute?, webpagePreviewAttribute: WebpagePreviewMessageAttribute?, disableUrlPreview: Bool) {
        }
    }

    var kind: ChatCustomContentsKind = .hashTagSearch(publicPosts: false)

    var historyView: Signal<(EngineRawMessageHistoryView, EngineViewUpdateType), NoError> {
        return self.impl.signalWith { impl, subscriber in
            if let currentHistoryView = impl.currentHistoryView {
                subscriber.putNext((currentHistoryView, .Initial))
            }
            return impl.historyViewStream.signal().start(next: subscriber.putNext)
        }
    }

    var messageLimit: Int? {
        return nil
    }

    private let peerId: PeerId
    private let queue: Queue
    private let impl: QueueLocalObject<Impl>

    init(context: AccountContext, peerId: PeerId) {
        self.peerId = peerId
        let queue = Queue()
        self.queue = queue
        self.impl = QueueLocalObject(queue: queue, generate: {
            return Impl(queue: queue, context: context, peerId: peerId)
        })
        AyuRuntimeSettings.beginDeletedViewer(peerId: peerId)
    }

    deinit {
        AyuRuntimeSettings.endDeletedViewer(peerId: self.peerId)
    }

    func enqueueMessages(messages: [EnqueueMessage]) {
    }

    func deleteMessages(ids: [EngineMessage.Id]) {
    }

    func editMessage(id: EngineMessage.Id, text: String, media: RequestEditMessageMedia, entities: TextEntitiesMessageAttribute?, webpagePreviewAttribute: WebpagePreviewMessageAttribute?, disableUrlPreview: Bool) {
    }

    func quickReplyUpdateShortcut(value: String) {
    }

    func businessLinkUpdate(message: String, entities: [MessageTextEntity], title: String?) {
    }

    func loadMore() {
    }

    func hashtagSearchUpdate(query: String) {
    }

    var hashtagSearchResultsUpdate: ((SearchMessagesResult, SearchMessagesState)) -> Void = { _ in }
}

func ayuDeletedMessagesController(context: AccountContext, peerId: PeerId) -> ViewController? {
    let contents = AyuDeletedMessagesChatContents(context: context, peerId: peerId)
    let controller = context.sharedContext.makeChatController(
        context: context,
        chatLocation: .customChatContents,
        subject: .customChatContents(contents: contents),
        botStart: nil,
        mode: .standard(.default),
        params: nil
    )
    let viewController: ViewController = controller
    viewController.title = "Удалёнки"
    return viewController
}
