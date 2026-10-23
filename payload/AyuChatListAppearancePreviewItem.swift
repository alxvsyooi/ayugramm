import Foundation
import UIKit
import AsyncDisplayKit
import Display
import SwiftSignalKit
import TelegramCore
import TelegramPresentationData
import ItemListUI
import AccountContext
import ChatListTitleView

struct AyuFolderPreview: Equatable {
    let title: String
    let icon: String?
    let unreadCount: Int
}

enum AyuChatListAppearancePreview: Equatable {
    case header(title: String, status: NetworkStatusTitle.Status?, snow: Bool)
    case folders(items: [AyuFolderPreview], mode: Int32, showUnread: Bool)
}

final class AyuChatListAppearancePreviewItem: ListViewItem, ItemListItem {
    let context: AccountContext
    let theme: PresentationTheme
    let strings: PresentationStrings
    let preview: AyuChatListAppearancePreview
    let sectionId: ItemListSectionId

    init(context: AccountContext, theme: PresentationTheme, strings: PresentationStrings, preview: AyuChatListAppearancePreview, sectionId: ItemListSectionId) {
        self.context = context
        self.theme = theme
        self.strings = strings
        self.preview = preview
        self.sectionId = sectionId
    }

    func nodeConfiguredForParams(async: @escaping (@escaping () -> Void) -> Void, params: ListViewItemLayoutParams, synchronousLoads: Bool, previousItem: ListViewItem?, nextItem: ListViewItem?, completion: @escaping (ListViewItemNode, @escaping () -> (Signal<Void, NoError>?, (ListViewItemApply) -> Void)) -> Void) {
        async {
            let node = AyuChatListAppearancePreviewItemNode()
            let (layout, apply) = node.asyncLayout()(self, params, itemListNeighbors(item: self, topItem: previousItem as? ItemListItem, bottomItem: nextItem as? ItemListItem))
            node.contentSize = layout.contentSize
            node.insets = layout.insets
            Queue.mainQueue().async {
                completion(node, { (nil, { _ in apply() }) })
            }
        }
    }

    func updateNode(async: @escaping (@escaping () -> Void) -> Void, node: @escaping () -> ListViewItemNode, params: ListViewItemLayoutParams, previousItem: ListViewItem?, nextItem: ListViewItem?, animation: ListViewItemUpdateAnimation, completion: @escaping (ListViewItemNodeLayout, @escaping (ListViewItemApply) -> Void) -> Void) {
        Queue.mainQueue().async {
            guard let node = node() as? AyuChatListAppearancePreviewItemNode else {
                return
            }
            let makeLayout = node.asyncLayout()
            async {
                let (layout, apply) = makeLayout(self, params, itemListNeighbors(item: self, topItem: previousItem as? ItemListItem, bottomItem: nextItem as? ItemListItem))
                Queue.mainQueue().async {
                    completion(layout, { _ in apply() })
                }
            }
        }
    }
}

private final class AyuChatListPreviewSnowView: UIView {
    private let emitter = CAEmitterLayer()
    private let cell = CAEmitterCell()
    private let fadeMask = CAGradientLayer()
    private var currentIsDark: Bool?

    override init(frame: CGRect) {
        super.init(frame: frame)
        self.isUserInteractionEnabled = false
        self.clipsToBounds = true

        self.cell.birthRate = 5.0
        self.cell.lifetime = 3.0
        self.cell.lifetimeRange = 0.35
        // Keep horizontal velocity at zero and use only downward gravity.
        self.cell.velocity = 0.0
        self.cell.velocityRange = 0.0
        self.cell.xAcceleration = 0.0
        self.cell.yAcceleration = 24.0
        self.cell.emissionRange = 0.0
        self.cell.scale = 0.5
        self.cell.scaleRange = 0.12
        self.cell.alphaSpeed = -0.12

        self.emitter.emitterShape = .line
        self.emitter.emitterMode = .surface
        self.emitter.emitterCells = [self.cell]
        self.layer.addSublayer(self.emitter)

        self.fadeMask.colors = [UIColor.clear.cgColor, UIColor.black.cgColor, UIColor.black.cgColor, UIColor.clear.cgColor]
        self.fadeMask.startPoint = CGPoint(x: 0.5, y: 0.0)
        self.fadeMask.endPoint = CGPoint(x: 0.5, y: 1.0)
        self.fadeMask.locations = [0.0, 0.12, 0.55, 1.0]
        self.layer.mask = self.fadeMask
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func update(isDark: Bool) {
        guard self.currentIsDark != isDark else {
            return
        }
        self.currentIsDark = isDark
        let size = CGSize(width: 4.0, height: 4.0)
        UIGraphicsBeginImageContextWithOptions(size, false, 0.0)
        (isDark ? UIColor.white : UIColor.black).setFill()
        UIBezierPath(ovalIn: CGRect(x: 1.0, y: 1.0, width: 2.0, height: 2.0)).fill()
        self.cell.contents = UIGraphicsGetImageFromCurrentImageContext()?.cgImage
        UIGraphicsEndImageContext()
        self.emitter.emitterCells = [self.cell]
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        self.emitter.frame = self.bounds
        self.emitter.emitterPosition = CGPoint(x: self.bounds.midX, y: -1.0)
        self.emitter.emitterSize = CGSize(width: self.bounds.width, height: 1.0)
        self.fadeMask.frame = self.bounds
    }
}

private final class AyuChatListAppearancePreviewItemNode: ListViewItemNode {
    private let backgroundNode = ASDisplayNode()
    private let topStripeNode = ASDisplayNode()
    private let bottomStripeNode = ASDisplayNode()
    private let maskNode = ASImageNode()
    private let previewCard = UIView()
    private var titleView: ChatListTitleView?
    private var snowView: AyuChatListPreviewSnowView?
    private var folderViews: [UIView] = []

    init() {
        super.init(layerBacked: false)
        self.backgroundNode.isLayerBacked = true
        self.topStripeNode.isLayerBacked = true
        self.bottomStripeNode.isLayerBacked = true
    }

    override func didLoad() {
        super.didLoad()
        self.previewCard.isUserInteractionEnabled = false
        self.previewCard.layer.cornerRadius = 15.0
        self.previewCard.clipsToBounds = true
        self.view.addSubview(self.previewCard)
    }

    private func clearFolders() {
        for view in self.folderViews {
            view.removeFromSuperview()
        }
        self.folderViews.removeAll()
    }

    private func updateHeader(item: AyuChatListAppearancePreviewItem, frame: CGRect, title: String, status: NetworkStatusTitle.Status?, snow: Bool) {
        self.clearFolders()
        let titleView: ChatListTitleView
        if let current = self.titleView {
            titleView = current
            titleView.theme = item.theme
            titleView.strings = item.strings
        } else {
            titleView = ChatListTitleView(
                context: item.context,
                theme: item.theme,
                strings: item.strings,
                animationCache: item.context.animationCache,
                animationRenderer: item.context.animationRenderer
            )
            titleView.manualLayout = true
            self.previewCard.addSubview(titleView)
            self.titleView = titleView
        }
        titleView.isHidden = false
        if snow {
            let snowView: AyuChatListPreviewSnowView
            if let current = self.snowView {
                snowView = current
            } else {
                snowView = AyuChatListPreviewSnowView()
                self.snowView = snowView
                self.previewCard.insertSubview(snowView, belowSubview: titleView)
            }
            snowView.update(isDark: item.theme.overallDarkAppearance)
            snowView.frame = CGRect(x: 0.0, y: 0.0, width: self.previewCard.bounds.width, height: min(54.0, self.previewCard.bounds.height))
            snowView.isHidden = false
        } else {
            self.snowView?.isHidden = true
        }
        titleView.title = NetworkStatusTitle(
            text: title,
            activity: false,
            hasProxy: false,
            connectsViaProxy: false,
            isPasscodeSet: false,
            isManuallyLocked: false,
            peerStatus: status
        )
        titleView.frame = frame
        let _ = titleView.updateLayout(availableSize: frame.size, transition: .immediate)
    }

    private func updateFolders(item: AyuChatListAppearancePreviewItem, folders: [AyuFolderPreview], mode: Int32, showUnread: Bool, frame: CGRect) {
        self.titleView?.isHidden = true
        self.clearFolders()
        let values = Array(folders.prefix(3))
        let count = max(1, values.count)
        let spacing: CGFloat = 7.0
        let width = floor((frame.width - spacing * CGFloat(count - 1)) / CGFloat(count))
        for index in 0 ..< count {
            let value = index < values.count ? values[index] : AyuFolderPreview(title: "Все чаты", icon: "💬", unreadCount: 0)
            let pill = UIView(frame: CGRect(x: frame.minX + CGFloat(index) * (width + spacing), y: frame.minY, width: width, height: frame.height))
            pill.layer.cornerRadius = frame.height * 0.5
            pill.backgroundColor = index == 0 ? item.theme.list.itemAccentColor.withAlphaComponent(0.16) : item.theme.list.itemHighlightedBackgroundColor

            let label = UILabel()
            label.font = Font.medium(13.0)
            label.textColor = index == 0 ? item.theme.list.itemAccentColor : item.theme.list.itemSecondaryTextColor
            label.textAlignment = .center
            label.lineBreakMode = .byTruncatingTail
            switch mode {
            case 1:
                label.text = value.title
            case 2:
                label.text = value.icon ?? "📁"
            default:
                if let icon = value.icon, !icon.isEmpty {
                    label.text = "\(icon) \(value.title)"
                } else {
                    label.text = value.title
                }
            }
            let badgeWidth: CGFloat = showUnread && value.unreadCount > 0 ? 27.0 : 0.0
            label.frame = CGRect(x: 8.0, y: 0.0, width: pill.bounds.width - 16.0 - badgeWidth, height: pill.bounds.height)
            pill.addSubview(label)

            if badgeWidth > 0.0 {
                let badge = UILabel(frame: CGRect(x: pill.bounds.width - badgeWidth - 5.0, y: floor((pill.bounds.height - 20.0) * 0.5), width: badgeWidth, height: 20.0))
                badge.font = Font.semibold(11.0)
                badge.textAlignment = .center
                badge.textColor = item.theme.list.itemCheckColors.foregroundColor
                badge.backgroundColor = item.theme.list.itemCheckColors.fillColor
                badge.layer.cornerRadius = 10.0
                badge.clipsToBounds = true
                badge.text = "\(value.unreadCount)"
                pill.addSubview(badge)
            }
            self.previewCard.addSubview(pill)
            self.folderViews.append(pill)
        }
    }

    func asyncLayout() -> (_ item: AyuChatListAppearancePreviewItem, _ params: ListViewItemLayoutParams, _ neighbors: ItemListNeighbors) -> (ListViewItemNodeLayout, () -> Void) {
        return { item, params, neighbors in
            let contentSize = CGSize(width: params.width, height: 94.0)
            let insets = itemListNeighborsGroupedInsets(neighbors, params)
            return (ListViewItemNodeLayout(contentSize: contentSize, insets: insets), { [weak self] in
                guard let self else {
                    return
                }
                self.backgroundNode.backgroundColor = item.theme.list.itemBlocksBackgroundColor
                self.topStripeNode.backgroundColor = item.theme.list.itemBlocksSeparatorColor
                self.bottomStripeNode.backgroundColor = item.theme.list.itemBlocksSeparatorColor
                if self.backgroundNode.supernode == nil { self.insertSubnode(self.backgroundNode, at: 0) }
                if self.topStripeNode.supernode == nil { self.insertSubnode(self.topStripeNode, at: 1) }
                if self.bottomStripeNode.supernode == nil { self.insertSubnode(self.bottomStripeNode, at: 2) }
                if self.maskNode.supernode == nil { self.insertSubnode(self.maskNode, at: 3) }

                let hasCorners = itemListHasRoundedBlockLayout(params)
                let topCorners: Bool
                switch neighbors.top {
                case .sameSection(false):
                    topCorners = false
                    self.topStripeNode.isHidden = true
                default:
                    topCorners = true
                    self.topStripeNode.isHidden = hasCorners
                }
                let bottomCorners: Bool
                let bottomInset: CGFloat
                switch neighbors.bottom {
                case .sameSection(false):
                    bottomCorners = false
                    bottomInset = params.leftInset + 16.0
                    self.bottomStripeNode.isHidden = false
                default:
                    bottomCorners = true
                    bottomInset = 0.0
                    self.bottomStripeNode.isHidden = hasCorners
                }
                self.maskNode.image = hasCorners ? PresentationResourcesItemList.cornersImage(item.theme, top: topCorners, bottom: bottomCorners) : nil
                let pixel = UIScreenPixel
                self.backgroundNode.frame = CGRect(x: 0.0, y: -min(insets.top, pixel), width: params.width, height: contentSize.height + min(insets.top, pixel) + min(insets.bottom, pixel))
                self.maskNode.frame = self.backgroundNode.frame.insetBy(dx: params.leftInset, dy: 0.0)
                self.topStripeNode.frame = CGRect(x: 0.0, y: -min(insets.top, pixel), width: params.width, height: pixel)
                self.bottomStripeNode.frame = CGRect(x: bottomInset, y: contentSize.height - pixel, width: params.width - bottomInset, height: pixel)

                let left = params.leftInset + 16.0
                let width = params.width - params.leftInset - params.rightInset - 32.0
                self.previewCard.frame = CGRect(x: left, y: 12.0, width: width, height: 70.0)
                self.previewCard.backgroundColor = item.theme.list.itemHighlightedBackgroundColor
                switch item.preview {
                case let .header(title, status, snow):
                    self.updateHeader(item: item, frame: CGRect(x: 10.0, y: 10.0, width: width - 20.0, height: 50.0), title: title, status: status, snow: snow)
                case let .folders(folders, mode, showUnread):
                    self.updateFolders(item: item, folders: folders, mode: mode, showUnread: showUnread, frame: CGRect(x: 8.0, y: 15.0, width: width - 16.0, height: 40.0))
                }
            })
        }
    }
}
