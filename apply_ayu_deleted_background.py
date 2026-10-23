#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


MARK = "AYU_DELETED_DARK_BUBBLE_v2"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_deleted_background.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift"
    text = path.read_text(encoding="utf-8")

    if MARK not in text:
        text = one(
            text,
            "    private let backgroundNode: ChatMessageBackground\n    private var backgroundHighlightNode: ChatMessageBackground?\n",
            "    private let backgroundNode: ChatMessageBackground\n"
            f"    // {MARK}: a deleted-only tint layer, masked with Telegram's own bubble image.\n"
            "    private let ayuDeletedBackgroundNode: ASImageNode\n"
            "    private var backgroundHighlightNode: ChatMessageBackground?\n",
            "deleted bubble property",
        )
        text = one(
            text,
            "        self.backgroundNode = ChatMessageBackground()\n        self.backgroundNode.backdropNode = self.backgroundWallpaperNode\n        self.shadowNode = ChatMessageShadowNode()\n",
            "        self.backgroundNode = ChatMessageBackground()\n"
            "        self.backgroundNode.backdropNode = self.backgroundWallpaperNode\n"
            "        self.ayuDeletedBackgroundNode = ASImageNode()\n"
            "        self.ayuDeletedBackgroundNode.displaysAsynchronously = false\n"
            "        self.ayuDeletedBackgroundNode.displayWithoutProcessing = true\n"
            "        self.ayuDeletedBackgroundNode.isUserInteractionEnabled = false\n"
            "        self.ayuDeletedBackgroundNode.isHidden = true\n"
            "        self.shadowNode = ChatMessageShadowNode()\n",
            "deleted bubble init",
        )
        text = one(
            text,
            "        self.mainContextSourceNode.contentNode.addSubnode(self.backgroundWallpaperNode)\n        self.mainContextSourceNode.contentNode.addSubnode(self.backgroundNode)\n        self.mainContextSourceNode.contentNode.addSubnode(self.clippingNode)\n",
            "        self.mainContextSourceNode.contentNode.addSubnode(self.backgroundWallpaperNode)\n"
            "        self.mainContextSourceNode.contentNode.addSubnode(self.backgroundNode)\n"
            "        self.mainContextSourceNode.contentNode.addSubnode(self.ayuDeletedBackgroundNode)\n"
            "        self.mainContextSourceNode.contentNode.addSubnode(self.clippingNode)\n",
            "deleted bubble hierarchy",
        )
        anchor = (
            "        strongSelf.backgroundNode.setType(type: backgroundType, highlighted: false, graphics: graphics, maskMode: strongSelf.backgroundMaskMode, hasWallpaper: hasWallpaper, transition: legacyTransition, backgroundNode: presentationContext.backgroundNode)\n"
            "        strongSelf.backgroundWallpaperNode.setType(type: backgroundType, theme: item.presentationData.theme, essentialGraphics: graphics, maskMode: strongSelf.backgroundMaskMode, backgroundNode: presentationContext.backgroundNode)\n"
            "        strongSelf.shadowNode.setType(type: backgroundType, hasWallpaper: hasWallpaper, graphics: graphics)\n"
        )
        replacement = anchor + f'''        // {MARK}: custom choices remain dark-theme-only. "Telegram"
        // takes the real incoming/outgoing bubble fill from PresentationTheme.
        // Use fill[0], not the wallpaper backdrop or animated gradient, then
        // let the final message-node alpha provide the requested opacity 0.5.
        let ayuDeletedBubbleColor: UIColor?
        if AyuRuntimeSettings.isDeleted(item.message.id),
           !AyuRuntimeSettings.isInDeletedViewer(item.message.id) {{
            switch AyuDeletedMarkerColor(rawValue: AyuRuntimeSettings.snapshot.deletedMarkerColor) ?? .telegram {{
            case .red: ayuDeletedBubbleColor = item.presentationData.theme.theme.overallDarkAppearance ? UIColor.systemRed : nil
            case .orange: ayuDeletedBubbleColor = item.presentationData.theme.theme.overallDarkAppearance ? UIColor.systemOrange : nil
            case .gray: ayuDeletedBubbleColor = item.presentationData.theme.theme.overallDarkAppearance ? UIColor.systemGray : nil
            case .purple: ayuDeletedBubbleColor = item.presentationData.theme.theme.overallDarkAppearance ? UIColor.systemPurple : nil
            case .pink: ayuDeletedBubbleColor = item.presentationData.theme.theme.overallDarkAppearance ? UIColor.systemPink : nil
            case .magenta: ayuDeletedBubbleColor = item.presentationData.theme.theme.overallDarkAppearance ? UIColor(red: 0.86, green: 0.12, blue: 0.46, alpha: 1.0) : nil
            case .indigo: ayuDeletedBubbleColor = item.presentationData.theme.theme.overallDarkAppearance ? UIColor.systemIndigo : nil
            case .blue: ayuDeletedBubbleColor = item.presentationData.theme.theme.overallDarkAppearance ? UIColor.systemBlue : nil
            case .telegram:
                switch backgroundType {{
                case .incoming:
                    ayuDeletedBubbleColor = bubbleColorComponents(theme: item.presentationData.theme.theme, incoming: true, wallpaper: hasWallpaper).fill.first?.withAlphaComponent(1.0)
                case .outgoing:
                    ayuDeletedBubbleColor = bubbleColorComponents(theme: item.presentationData.theme.theme, incoming: false, wallpaper: hasWallpaper).fill.first?.withAlphaComponent(1.0)
                case .none:
                    ayuDeletedBubbleColor = nil
                }}
            }}
        }} else {{
            ayuDeletedBubbleColor = nil
        }}
        if let ayuDeletedBubbleColor,
           let maskImage = bubbleMaskForType(backgroundType, graphics: graphics),
           let tintedImage = generateTintedImage(image: maskImage, color: ayuDeletedBubbleColor) {{
            strongSelf.ayuDeletedBackgroundNode.image = tintedImage.resizableImage(withCapInsets: maskImage.capInsets, resizingMode: maskImage.resizingMode)
            strongSelf.ayuDeletedBackgroundNode.isHidden = false
        }} else {{
            strongSelf.ayuDeletedBackgroundNode.image = nil
            strongSelf.ayuDeletedBackgroundNode.isHidden = true
        }}
        animation.animator.updateFrame(layer: strongSelf.ayuDeletedBackgroundNode.layer, frame: backgroundFrame, completion: nil)
'''
        text = one(text, anchor, replacement, "deleted bubble render")
        path.write_text(text, encoding="utf-8")

    verify = path.read_text(encoding="utf-8")
    required = (
        MARK,
        "private let ayuDeletedBackgroundNode: ASImageNode",
        "bubbleMaskForType(backgroundType, graphics: graphics)",
        "bubbleColorComponents(theme: item.presentationData.theme.theme, incoming: true, wallpaper: hasWallpaper).fill.first?.withAlphaComponent(1.0)",
        "bubbleColorComponents(theme: item.presentationData.theme.theme, incoming: false, wallpaper: hasWallpaper).fill.first?.withAlphaComponent(1.0)",
    )
    for value in required:
        if value not in verify:
            raise RuntimeError(f"deleted dark bubble incomplete: {value}")

    print("[ayu-deleted-background] Telegram mode uses the native side-specific bubble fill; custom dark colors stay at effective alpha 0.5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
