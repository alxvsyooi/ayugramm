import Foundation
import UIKit
import Display
import SwiftSignalKit
import TelegramCore
import TelegramPresentationData
import TelegramStringFormatting
import AccountContext
import Postbox
import AvatarNode

// AYU_EDIT_HISTORY_VIEWER_v0_3
// Read-only Telegram chat renderer for locally saved message revisions.
// Each revision is rendered as a plain message without an author/avatar; Telegram's
// normal history renderer supplies bubble timestamps and date separators.
final class AyuEditHistoryChatContents: ChatCustomContentsProtocol {
    private let view: EngineRawMessageHistoryView

    var kind: ChatCustomContentsKind = .hashTagSearch(publicPosts: false)

    var historyView: Signal<(EngineRawMessageHistoryView, EngineViewUpdateType), NoError> {
        return .single((self.view, .Initial))
    }

    var messageLimit: Int? {
        return nil
    }

    init(source: EngineRawMessage, revisions: [AyuSpyEditRevision]) {
        let sourceMessage = EngineMessage(source)
        var timeline: [(Int64, String)] = []
        timeline.reserveCapacity(revisions.count + 1)

        // A stored row describes the version that existed immediately before an
        // edit. Its creation time is the original message time for revision 0 and
        // the previous edit timestamp for every subsequent revision.
        for index in revisions.indices {
            let timestamp: Int64
            if index == 0 {
                timestamp = Int64(sourceMessage.timestamp)
            } else {
                timestamp = revisions[index - 1].editedAt
            }
            timeline.append((timestamp, revisions[index].text))
        }
        if let last = revisions.last {
            if timeline.last?.1 != sourceMessage.text {
                timeline.append((last.editedAt, sourceMessage.text))
            }
        }

        var flags: EngineMessage.Flags = []
        if sourceMessage.flags.contains(.Incoming) {
            flags.insert(.Incoming)
        }

        let entries: [EngineRawMessageHistoryEntry] = timeline.enumerated().map { index, item in
            let localId = Int32(index + 1)
            let message = EngineMessage(
                stableId: UInt32(index + 1),
                stableVersion: 0,
                id: EngineMessage.Id(peerId: sourceMessage.id.peerId, namespace: Namespaces.Message.Local, id: localId),
                globallyUniqueId: nil,
                groupingKey: nil,
                groupInfo: nil,
                threadId: nil,
                timestamp: Int32(clamping: item.0),
                flags: flags,
                tags: [],
                globalTags: [],
                localTags: [],
                customTags: [],
                forwardInfo: nil,
                author: nil,
                text: item.1,
                attributes: [],
                media: [],
                peers: sourceMessage.enginePeers,
                associatedMessages: [:],
                associatedMessageIds: [],
                associatedMedia: [:],
                associatedThreadInfo: nil,
                associatedStories: [:]
            )
            return EngineRawMessageHistoryEntry(
                message: message._asMessage(),
                isRead: true,
                location: nil,
                monthLocation: nil,
                attributes: EngineRawMutableMessageHistoryEntryAttributes(authorIsContact: false)
            )
        }

        self.view = EngineRawMessageHistoryView(
            tag: nil,
            namespaces: .just(Set([Namespaces.Message.Local])),
            entries: entries,
            holeEarlier: false,
            holeLater: false,
            isLoading: false
        )
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

private final class AyuEditHistoryTitleView: UIView {
    private let context: AccountContext
    private let peerId: EnginePeer.Id
    private let avatarNode: AvatarNode
    private let titleLabel = UILabel()
    private let statusLabel = UILabel()
    private var disposable: Disposable?
    private var currentPeer: EnginePeer?

    init(context: AccountContext, peer: EnginePeer) {
        self.context = context
        self.peerId = peer.id
        self.avatarNode = AvatarNode(font: avatarPlaceholderFont(size: 15.0))
        self.currentPeer = peer

        super.init(frame: CGRect(x: 0.0, y: 0.0, width: 230.0, height: 44.0))

        self.addSubview(self.avatarNode.view)
        self.addSubview(self.titleLabel)
        self.addSubview(self.statusLabel)
        self.titleLabel.font = Font.semibold(16.0)
        self.titleLabel.lineBreakMode = .byTruncatingTail
        self.statusLabel.font = Font.regular(12.0)
        self.statusLabel.lineBreakMode = .byTruncatingTail

        self.update(peer: peer, presence: nil)
        self.disposable = (context.account.postbox.peerView(id: peer.id)
        |> deliverOnMainQueue).start(next: { [weak self] view in
            guard let self, let rawPeer = peerViewMainPeer(view) else {
                return
            }
            let enginePeer = EnginePeer(rawPeer)
            var presence: EnginePeer.Presence?
            if let userPresence = view.peerPresences[enginePeer.id] as? TelegramUserPresence {
                presence = EnginePeer.Presence(userPresence)
            }
            self.update(peer: enginePeer, presence: presence)
        })
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    deinit {
        self.disposable?.dispose()
    }

    private func update(peer: EnginePeer, presence: EnginePeer.Presence?) {
        self.currentPeer = peer
        let presentationData = self.context.sharedContext.currentPresentationData.with { $0 }
        self.titleLabel.text = peer.displayTitle(strings: presentationData.strings, displayOrder: presentationData.nameDisplayOrder)
        self.titleLabel.textColor = presentationData.theme.rootController.navigationBar.primaryTextColor
        self.statusLabel.textColor = presentationData.theme.rootController.navigationBar.secondaryTextColor

        if let presence {
            let timestamp = Int32(CFAbsoluteTimeGetCurrent() + NSTimeIntervalSince1970)
            let (status, active) = stringAndActivityForUserPresence(
                strings: presentationData.strings,
                dateTimeFormat: presentationData.dateTimeFormat,
                presence: presence,
                relativeTo: timestamp
            )
            self.statusLabel.text = status
            self.statusLabel.textColor = active ? presentationData.theme.list.itemAccentColor : presentationData.theme.rootController.navigationBar.secondaryTextColor
        } else if peer.id.namespace == Namespaces.Peer.CloudChannel {
            self.statusLabel.text = "канал"
        } else if peer.id.namespace == Namespaces.Peer.CloudGroup {
            self.statusLabel.text = "группа"
        } else {
            self.statusLabel.text = presentationData.strings.LastSeen_Offline
        }

        self.avatarNode.setPeer(context: self.context, theme: presentationData.theme, peer: peer)
        self.setNeedsLayout()
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        let avatarSize = CGSize(width: 36.0, height: 36.0)
        let avatarFrame = CGRect(x: 0.0, y: floor((self.bounds.height - avatarSize.height) * 0.5), width: avatarSize.width, height: avatarSize.height)
        self.avatarNode.frame = avatarFrame
        self.avatarNode.updateSize(size: avatarSize)

        let textX: CGFloat = 44.0
        let textWidth = max(0.0, self.bounds.width - textX)
        self.titleLabel.frame = CGRect(x: textX, y: 4.0, width: textWidth, height: 20.0)
        self.statusLabel.frame = CGRect(x: textX, y: 23.0, width: textWidth, height: 17.0)
    }
}

func ayuEditHistoryController(context: AccountContext, message: EngineRawMessage) -> ViewController? {
    let revisions = ayuSpyEditHistory(message.id)
    guard !revisions.isEmpty else {
        return nil
    }

    let source = EngineMessage(message)
    let displayPeer: EnginePeer?
    if let author = source.author {
        displayPeer = author
    } else {
        displayPeer = source.enginePeers[source.id.peerId]
    }

    let contents = AyuEditHistoryChatContents(source: message, revisions: revisions)
    let controller = context.sharedContext.makeChatController(
        context: context,
        chatLocation: .customChatContents,
        subject: .customChatContents(contents: contents),
        botStart: nil,
        mode: .standard(.default),
        params: nil
    )
    let viewController: ViewController = controller
    viewController.title = "История правок"

    if let displayPeer {
        let titleView = AyuEditHistoryTitleView(context: context, peer: displayPeer)
        viewController.navigationItem.titleView = titleView
        Queue.mainQueue().async { [weak viewController, weak titleView] in
            if let viewController, let titleView {
                viewController.navigationItem.titleView = titleView
            }
        }
    }
    return viewController
}
