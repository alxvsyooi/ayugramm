import Foundation
import UIKit
import AsyncDisplayKit
import Display
import SwiftSignalKit
import TelegramPresentationData
import LegacyComponents
import ItemListUI

enum AyuAvatarRoundingPreview: Equatable {
    case chatList
    case chatMessage
    case profile
}

final class AyuAvatarRoundingItem: ListViewItem, ItemListItem {
    let theme: PresentationTheme
    let value: Int32
    let preview: AyuAvatarRoundingPreview
    let sectionId: ItemListSectionId
    let updated: (Int32) -> Void

    init(theme: PresentationTheme, value: Int32, preview: AyuAvatarRoundingPreview, sectionId: ItemListSectionId, updated: @escaping (Int32) -> Void) {
        self.theme = theme
        self.value = value
        self.preview = preview
        self.sectionId = sectionId
        self.updated = updated
    }

    func nodeConfiguredForParams(async: @escaping (@escaping () -> Void) -> Void, params: ListViewItemLayoutParams, synchronousLoads: Bool, previousItem: ListViewItem?, nextItem: ListViewItem?, completion: @escaping (ListViewItemNode, @escaping () -> (Signal<Void, NoError>?, (ListViewItemApply) -> Void)) -> Void) {
        async {
            let node = AyuAvatarRoundingItemNode()
            let (layout, apply) = node.asyncLayout()(self, params, itemListNeighbors(item: self, topItem: previousItem as? ItemListItem, bottomItem: nextItem as? ItemListItem))
            node.contentSize = layout.contentSize
            node.insets = layout.insets
            Queue.mainQueue().async { completion(node, { (nil, { _ in apply() }) }) }
        }
    }

    func updateNode(async: @escaping (@escaping () -> Void) -> Void, node: @escaping () -> ListViewItemNode, params: ListViewItemLayoutParams, previousItem: ListViewItem?, nextItem: ListViewItem?, animation: ListViewItemUpdateAnimation, completion: @escaping (ListViewItemNodeLayout, @escaping (ListViewItemApply) -> Void) -> Void) {
        Queue.mainQueue().async {
            guard let node = node() as? AyuAvatarRoundingItemNode else { return }
            let makeLayout = node.asyncLayout()
            async {
                let (layout, apply) = makeLayout(self, params, itemListNeighbors(item: self, topItem: previousItem as? ItemListItem, bottomItem: nextItem as? ItemListItem))
                Queue.mainQueue().async { completion(layout, { _ in apply() }) }
            }
        }
    }
}

private final class AyuCenteredValueLabel: UILabel {
    override func drawText(in rect: CGRect) {
        let fitting = self.sizeThatFits(rect.size)
        let height = min(rect.height, ceil(fitting.height))
        super.drawText(in: CGRect(x: rect.minX, y: rect.minY + floor((rect.height - height) * 0.5), width: rect.width, height: height))
    }
}

private final class AyuAvatarRoundingItemNode: ListViewItemNode {
    private let backgroundNode = ASDisplayNode()
    private let topStripeNode = ASDisplayNode()
    private let bottomStripeNode = ASDisplayNode()
    private let maskNode = ASImageNode()
    private var sliderView: TGPhotoEditorSliderView?
    private let titleLabel = UILabel()
    private let valueLabel = AyuCenteredValueLabel()
    private let squareLabel = UILabel()
    private let circleLabel = UILabel()
    private let previewCard = UIView()
    private let previewBubble = UIView()
    private let previewAvatar = UIView()
    private let previewLine1 = UIView()
    private let previewLine2 = UIView()
    private let previewBadge = UIView()
    private var item: AyuAvatarRoundingItem?
    private var layoutParams: ListViewItemLayoutParams?

    init() {
        super.init(layerBacked: false)
        self.backgroundNode.isLayerBacked = true
        self.topStripeNode.isLayerBacked = true
        self.bottomStripeNode.isLayerBacked = true
    }

    override func didLoad() {
        super.didLoad()
        for label in [self.titleLabel, self.valueLabel, self.squareLabel, self.circleLabel] {
            label.backgroundColor = .clear
            self.view.addSubview(label)
        }
        self.titleLabel.font = Font.medium(17.0)
        self.valueLabel.font = Font.semibold(14.0)
        self.valueLabel.textAlignment = .center
        self.valueLabel.baselineAdjustment = .alignCenters
        self.valueLabel.adjustsFontSizeToFitWidth = true
        self.valueLabel.minimumScaleFactor = 0.8
        self.valueLabel.layer.cornerRadius = 9.0
        self.valueLabel.clipsToBounds = true
        self.squareLabel.font = Font.regular(13.0)
        self.squareLabel.text = "Квадрат"
        self.circleLabel.font = Font.regular(13.0)
        self.circleLabel.textAlignment = .right
        self.circleLabel.text = "Круг"

        let sliderView = TGPhotoEditorSliderView()
        sliderView.enablePanHandling = true
        sliderView.trackCornerRadius = 1.0
        sliderView.lineSize = 2.0
        sliderView.minimumValue = 0.0
        sliderView.startValue = 0.0
        sliderView.maximumValue = 100.0
        sliderView.disablesInteractiveTransitionGestureRecognizer = true
        sliderView.addTarget(self, action: #selector(self.sliderValueChanged), for: .valueChanged)
        self.view.addSubview(sliderView)
        self.sliderView = sliderView

        self.previewCard.isUserInteractionEnabled = false
        self.previewCard.layer.cornerRadius = 15.0
        self.previewCard.clipsToBounds = true
        self.view.addSubview(self.previewCard)
        self.previewBubble.isUserInteractionEnabled = false
        self.previewBubble.clipsToBounds = true
        self.previewCard.addSubview(self.previewBubble)
        self.previewAvatar.clipsToBounds = true
        self.previewCard.addSubview(self.previewAvatar)
        for line in [self.previewLine1, self.previewLine2, self.previewBadge] {
            line.layer.cornerRadius = 4.0
            self.previewBubble.addSubview(line)
        }
        self.updateViews()
    }

    private func updatePreview(value: Int32) {
        self.valueLabel.text = "\(value)"
        let edge = min(self.previewAvatar.bounds.width, self.previewAvatar.bounds.height)
        self.previewAvatar.layer.cornerRadius = floor(edge * 0.5 * CGFloat(max(0, min(100, value))) / 100.0)
        self.valueLabel.setNeedsDisplay()
    }

    private func updateViews() {
        guard let item = self.item, let params = self.layoutParams else { return }
        let theme = item.theme
        switch item.preview {
        case .chatList:
            self.titleLabel.text = "Аватарки в списке чатов"
        case .chatMessage:
            self.titleLabel.text = "Аватарки в чате"
        case .profile:
            self.titleLabel.text = "Аватарки в профиле"
        }
        self.titleLabel.textColor = theme.list.itemPrimaryTextColor
        self.valueLabel.textColor = theme.list.itemAccentColor
        self.valueLabel.backgroundColor = theme.list.itemAccentColor.withAlphaComponent(0.12)
        self.squareLabel.textColor = theme.list.itemSecondaryTextColor
        self.circleLabel.textColor = theme.list.itemSecondaryTextColor
        self.previewCard.backgroundColor = theme.list.itemHighlightedBackgroundColor
        self.previewBubble.backgroundColor = item.preview == .chatMessage ? theme.list.itemBlocksBackgroundColor : .clear
        self.previewBubble.layer.cornerRadius = item.preview == .chatMessage ? 14.0 : 0.0
        self.previewAvatar.backgroundColor = theme.list.itemAccentColor
        self.previewLine1.backgroundColor = theme.list.itemSecondaryTextColor.withAlphaComponent(0.45)
        self.previewLine2.backgroundColor = theme.list.itemSecondaryTextColor.withAlphaComponent(0.28)
        self.previewBadge.backgroundColor = theme.list.itemAccentColor.withAlphaComponent(0.45)
        if let sliderView = self.sliderView {
            sliderView.value = CGFloat(item.value)
            sliderView.backgroundColor = theme.list.itemBlocksBackgroundColor
            sliderView.backColor = theme.list.itemSwitchColors.frameColor
            sliderView.trackColor = theme.list.itemAccentColor
            sliderView.knobImage = PresentationResourcesItemList.knobImage(theme)
            sliderView.frame = CGRect(x: params.leftInset + 16.0, y: 61.0, width: params.width - params.leftInset - params.rightInset - 32.0, height: 44.0)
        }
        self.updatePreview(value: item.value)
    }

    func asyncLayout() -> (_ item: AyuAvatarRoundingItem, _ params: ListViewItemLayoutParams, _ neighbors: ItemListNeighbors) -> (ListViewItemNodeLayout, () -> Void) {
        return { item, params, neighbors in
            let contentHeight: CGFloat = item.preview == .profile ? 218.0 : 183.0
            let contentSize = CGSize(width: params.width, height: contentHeight)
            let insets = itemListNeighborsGroupedInsets(neighbors, params)
            let layout = ListViewItemNodeLayout(contentSize: contentSize, insets: insets)
            return (layout, { [weak self] in
                guard let self else { return }
                self.item = item
                self.layoutParams = params
                self.backgroundNode.backgroundColor = item.theme.list.itemBlocksBackgroundColor
                self.topStripeNode.backgroundColor = item.theme.list.itemBlocksSeparatorColor
                self.bottomStripeNode.backgroundColor = item.theme.list.itemBlocksSeparatorColor
                if self.backgroundNode.supernode == nil { self.insertSubnode(self.backgroundNode, at: 0) }
                if self.topStripeNode.supernode == nil { self.insertSubnode(self.topStripeNode, at: 1) }
                if self.bottomStripeNode.supernode == nil { self.insertSubnode(self.bottomStripeNode, at: 2) }
                if self.maskNode.supernode == nil { self.insertSubnode(self.maskNode, at: 3) }
                let hasCorners = itemListHasRoundedBlockLayout(params)
                let topCorners: Bool
                switch neighbors.top { case .sameSection(false): topCorners = false; self.topStripeNode.isHidden = true; default: topCorners = true; self.topStripeNode.isHidden = hasCorners }
                let bottomCorners: Bool
                let bottomInset: CGFloat
                switch neighbors.bottom { case .sameSection(false): bottomCorners = false; bottomInset = params.leftInset + 16.0; self.bottomStripeNode.isHidden = false; default: bottomCorners = true; bottomInset = 0.0; self.bottomStripeNode.isHidden = hasCorners }
                self.maskNode.image = hasCorners ? PresentationResourcesItemList.cornersImage(item.theme, top: topCorners, bottom: bottomCorners) : nil
                let pixel = UIScreenPixel
                self.backgroundNode.frame = CGRect(x: 0.0, y: -min(insets.top, pixel), width: params.width, height: contentSize.height + min(insets.top, pixel) + min(insets.bottom, pixel))
                self.maskNode.frame = self.backgroundNode.frame.insetBy(dx: params.leftInset, dy: 0.0)
                self.topStripeNode.frame = CGRect(x: 0.0, y: -min(insets.top, pixel), width: params.width, height: pixel)
                self.bottomStripeNode.frame = CGRect(x: bottomInset, y: contentSize.height - pixel, width: params.width - bottomInset, height: pixel)
                let left = params.leftInset + 16.0
                let right = params.width - params.rightInset - 16.0
                self.titleLabel.frame = CGRect(x: left, y: 13.0, width: right - left - 62.0, height: 24.0)
                self.valueLabel.frame = CGRect(x: right - 52.0, y: 11.0, width: 52.0, height: 28.0)
                self.squareLabel.frame = CGRect(x: left, y: 42.0, width: 90.0, height: 20.0)
                self.circleLabel.frame = CGRect(x: right - 90.0, y: 42.0, width: 90.0, height: 20.0)

                switch item.preview {
                case .chatList:
                    self.previewCard.frame = CGRect(x: left, y: 109.0, width: right - left, height: 60.0)
                    self.previewBubble.frame = self.previewCard.bounds
                    self.previewAvatar.frame = CGRect(x: 8.0, y: 8.0, width: 44.0, height: 44.0)
                    self.previewLine1.frame = CGRect(x: 68.0, y: 15.0, width: min(145.0, self.previewCard.bounds.width - 124.0), height: 8.0)
                    self.previewLine2.frame = CGRect(x: 68.0, y: 35.0, width: min(105.0, self.previewCard.bounds.width - 124.0), height: 8.0)
                    self.previewBadge.frame = CGRect(x: self.previewCard.bounds.width - 58.0, y: 17.0, width: 42.0, height: 18.0)
                case .chatMessage:
                    self.previewCard.frame = CGRect(x: left, y: 109.0, width: right - left, height: 60.0)
                    self.previewAvatar.frame = CGRect(x: 8.0, y: 8.0, width: 44.0, height: 44.0)
                    self.previewBubble.frame = CGRect(x: 62.0, y: 5.0, width: self.previewCard.bounds.width - 70.0, height: 50.0)
                    self.previewLine1.frame = CGRect(x: 12.0, y: 10.0, width: min(126.0, self.previewBubble.bounds.width - 72.0), height: 8.0)
                    self.previewLine2.frame = CGRect(x: 12.0, y: 30.0, width: min(92.0, self.previewBubble.bounds.width - 72.0), height: 8.0)
                    self.previewBadge.frame = CGRect(x: self.previewBubble.bounds.width - 52.0, y: 26.0, width: 40.0, height: 14.0)
                case .profile:
                    self.previewCard.frame = CGRect(x: left, y: 109.0, width: right - left, height: 95.0)
                    self.previewBubble.frame = self.previewCard.bounds
                    self.previewAvatar.frame = CGRect(x: floor((self.previewCard.bounds.width - 52.0) * 0.5), y: 8.0, width: 52.0, height: 52.0)
                    self.previewLine1.frame = CGRect(x: floor((self.previewCard.bounds.width - 96.0) * 0.5), y: 68.0, width: 96.0, height: 7.0)
                    self.previewLine2.frame = CGRect(x: floor((self.previewCard.bounds.width - 62.0) * 0.5), y: 80.0, width: 62.0, height: 6.0)
                    self.previewBadge.frame = .zero
                }
                self.updateViews()
            })
        }
    }

    @objc private func sliderValueChanged() {
        guard let sliderView = self.sliderView else { return }
        let value = Int32(max(0, min(100, Int(sliderView.value.rounded()))))
        self.updatePreview(value: value)
        self.item?.updated(value)
    }
}
