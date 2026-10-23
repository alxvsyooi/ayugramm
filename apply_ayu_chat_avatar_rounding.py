#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
from pathlib import Path


MARK = "AYU_CHAT_AVATAR_ROUNDING_v2"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def patch_runtime(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return
    text = one(
        text,
        '    private static let unifiedAvatarCornersKey = keyPrefix + "appearance.unifiedAvatarCorners"\n',
        '    private static let unifiedAvatarCornersKey = keyPrefix + "appearance.unifiedAvatarCorners"\n'
        '    // AYU_CHAT_AVATAR_ROUNDING_v2\n'
        '    private static let chatAvatarCornerPercentKey = keyPrefix + "appearance.chatAvatarCornerPercent"\n',
        "chat avatar key",
    )
    text = one(
        text,
        '    private static let unifiedAvatarCornersState = Atomic<Bool>(value: UserDefaults.standard.bool(forKey: unifiedAvatarCornersKey))\n',
        '    private static let unifiedAvatarCornersState = Atomic<Bool>(value: UserDefaults.standard.bool(forKey: unifiedAvatarCornersKey))\n'
        '    private static let chatAvatarCornerPercentState = Atomic<Int32>(value: {\n'
        '        let defaults = UserDefaults.standard\n'
        '        guard defaults.object(forKey: chatAvatarCornerPercentKey) != nil else { return 100 }\n'
        '        return Int32(max(0, min(100, defaults.integer(forKey: chatAvatarCornerPercentKey))))\n'
        '    }())\n',
        "chat avatar state",
    )
    getter_anchor = '''    public static var unifiedAvatarCorners: Bool {
        return unifiedAvatarCornersState.with { $0 }
    }
'''
    getter = '''    public static var chatAvatarCornerPercent: Int32 {
        return chatAvatarCornerPercentState.with { $0 }
    }

'''
    text = one(text, getter_anchor, getter + getter_anchor, "chat avatar getter")
    setter_anchor = '''    public static func setUnifiedAvatarCorners(_ value: Bool) {
'''
    setter = '''    public static func setChatAvatarCornerPercent(_ value: Int32) {
        let normalized = max(0, min(100, value))
        let previous = chatAvatarCornerPercentState.swap(normalized)
        if previous != normalized {
            UserDefaults.standard.set(Int(normalized), forKey: chatAvatarCornerPercentKey)
        }
    }

'''
    text = one(text, setter_anchor, setter + setter_anchor, "chat avatar setter")
    path.write_text(text, encoding="utf-8")


def patch_avatar_helper(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return
    anchor = "\nprivate class AvatarNodeParameters: NSObject {\n"
    helper = '''
// AYU_CHAT_AVATAR_ROUNDING_v2: used only by message-author avatars.
public func ayuChatAvatarCornerRadius(size: CGSize) -> CGFloat {
    let edge = min(size.width, size.height)
    return floor(edge * 0.5 * CGFloat(AyuRuntimeSettings.chatAvatarCornerPercent) / 100.0)
}
'''
    text = one(text, anchor, helper + anchor, "chat avatar helper")
    path.write_text(text, encoding="utf-8")


def patch_chat_avatar(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return

    first = "emptyColor: .black, synchronousLoad:"
    if text.count(first) != 2:
        raise RuntimeError(f"chat black avatar calls: expected 2, found {text.count(first)}")
    text = text.replace(first, "emptyColor: .black, clipStyle: .none, synchronousLoad:")

    second = "emptyColor: emptyColor, synchronousLoad:"
    if text.count(second) != 2:
        raise RuntimeError(f"chat regular avatar calls: expected 2, found {text.count(second)}")
    text = text.replace(second, "emptyColor: emptyColor, clipStyle: .none, synchronousLoad:")

    custom = '''        self.avatarNode.setCustomLetters(letters, icon: !letters.isEmpty ? nil : .phone)
'''
    text = one(text, custom, custom + "        self.applyAyuChatCornerRadius()\n", "custom chat avatar")

    update_block = '''            } else {
                self.avatarNode.setPeer(context: self.context, theme: self.presentationData.theme.theme, peer: EnginePeer(peer), authorOfMessage: self.messageReference, overrideImage: nil, emptyColor: .black, clipStyle: .none, synchronousLoad: false, displayDimensions: CGSize(width: avatarHeaderSize(), height: avatarHeaderSize()))
            }
'''
    text = one(text, update_block, update_block + "            self.applyAyuChatCornerRadius()\n", "updated chat avatar")

    set_block = '''        } else {
            self.avatarNode.setPeer(context: context, theme: theme, peer: EnginePeer(peer), authorOfMessage: authorOfMessage, overrideImage: overrideImage, emptyColor: emptyColor, clipStyle: .none, synchronousLoad: synchronousLoad, displayDimensions: CGSize(width: avatarHeaderSize(), height: avatarHeaderSize()))
        }
'''
    text = one(text, set_block, set_block + "        self.applyAyuChatCornerRadius()\n", "initial chat avatar")

    visibility_anchor = '''    private func updateVideoVisibility() {
'''
    helper = '''    // AYU_CHAT_AVATAR_ROUNDING_v2: layer clipping keeps the chat-only
    // radius independent from generated avatars used everywhere else.
    private func applyAyuChatCornerRadius() {
        let size = CGSize(width: avatarHeaderSize(), height: avatarHeaderSize())
        self.avatarNode.contentNode.clipsToBounds = true
        self.avatarNode.contentNode.cornerRadius = ayuChatAvatarCornerRadius(size: size)
    }

'''
    text = one(text, visibility_anchor, helper + visibility_anchor, "chat layer helper")
    text = one(
        text,
        "            videoNode.updateLayout(size: self.avatarNode.bounds.size, cornerRadius: self.avatarNode.bounds.size.width / 2.0, transition: .immediate)\n",
        "            videoNode.updateLayout(size: self.avatarNode.bounds.size, cornerRadius: ayuChatAvatarCornerRadius(size: self.avatarNode.bounds.size), transition: .immediate)\n",
        "chat video avatar radius",
    )
    path.write_text(text, encoding="utf-8")


def patch_settings(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return
    text = one(
        text,
        '''    let updateCornerPercent: (Int32) -> Void
    let updateUnified: (Bool) -> Void
    init(updateCornerPercent: @escaping (Int32) -> Void, updateUnified: @escaping (Bool) -> Void) {
        self.updateCornerPercent = updateCornerPercent
        self.updateUnified = updateUnified
    }
''',
        '''    let updateCornerPercent: (Int32) -> Void
    let updateUnified: (Bool) -> Void
    let updateChatCornerPercent: (Int32) -> Void
    init(updateCornerPercent: @escaping (Int32) -> Void, updateUnified: @escaping (Bool) -> Void, updateChatCornerPercent: @escaping (Int32) -> Void) {
        self.updateCornerPercent = updateCornerPercent
        self.updateUnified = updateUnified
        self.updateChatCornerPercent = updateChatCornerPercent
    }
''',
        "appearance arguments",
    )
    text = one(text, "    case unified(Bool)\n    case info\n", "    case unified(Bool)\n    case chatRounding(Int32)\n    case info\n", "chat slider entry")
    text = one(
        text,
        '''        case .unified: return 2
        case .info: return 3
''',
        '''        case .unified: return 2
        case .chatRounding: return 3
        case .info: return 4
''',
        "chat slider ordering",
    )
    text = one(
        text,
        "            return AyuAvatarRoundingItem(theme: presentationData.theme, value: value, sectionId: self.section, updated: arguments.updateCornerPercent)\n",
        "            return AyuAvatarRoundingItem(theme: presentationData.theme, value: value, isChat: false, sectionId: self.section, updated: arguments.updateCornerPercent)\n",
        "outside-chat slider",
    )
    switch_anchor = '''        case let .unified(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Единое закругление", value: value, sectionId: self.section, style: .blocks, updated: arguments.updateUnified)
        case .info:
            return ItemListTextItem(presentationData: presentationData, text: .plain("Форумы будут иметь ту же форму, что и чаты."), sectionId: self.section)
'''
    switch_new = '''        case let .unified(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Единое закругление", value: value, sectionId: self.section, style: .blocks, updated: arguments.updateUnified)
        case let .chatRounding(value):
            return AyuAvatarRoundingItem(theme: presentationData.theme, value: value, isChat: true, sectionId: self.section, updated: arguments.updateChatCornerPercent)
        case .info:
            return ItemListTextItem(presentationData: presentationData, text: .plain("Форумы будут иметь ту же форму, что и аватарки вне чата."), sectionId: self.section)
'''
    text = one(text, switch_anchor, switch_new, "chat slider item")
    text = one(
        text,
        '''    }, updateUnified: { value in
        AyuRuntimeSettings.setUnifiedAvatarCorners(value)
        bump()
    })
''',
        '''    }, updateUnified: { value in
        AyuRuntimeSettings.setUnifiedAvatarCorners(value)
        bump()
    }, updateChatCornerPercent: { value in
        AyuRuntimeSettings.setChatAvatarCornerPercent(value)
    })
''',
        "chat slider callback",
    )
    text = one(
        text,
        "        let entries: [AyuAppearanceEntry] = [.header, .rounding(AyuRuntimeSettings.avatarCornerPercent), .unified(AyuRuntimeSettings.unifiedAvatarCorners), .info]\n",
        "        let entries: [AyuAppearanceEntry] = [.header, .rounding(AyuRuntimeSettings.avatarCornerPercent), .unified(AyuRuntimeSettings.unifiedAvatarCorners), .chatRounding(AyuRuntimeSettings.chatAvatarCornerPercent), .info]\n",
        "chat slider entries",
    )
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_chat_avatar_rounding.py <Telegram-iOS root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    patch_runtime(root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift")
    patch_avatar_helper(root / "submodules/AvatarNode/Sources/AvatarNode.swift")
    patch_chat_avatar(root / "submodules/TelegramUI/Components/Chat/ChatMessageItemImpl/Sources/ChatMessageDateHeader.swift")
    patch_settings(root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift")
    shutil.copyfile(Path(__file__).resolve().parent / "payload/AyuAvatarRoundingItem.swift", root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuAvatarRoundingItem.swift")

    runtime = (root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift").read_text(encoding="utf-8")
    settings = (root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift").read_text(encoding="utf-8")
    chat = (root / "submodules/TelegramUI/Components/Chat/ChatMessageItemImpl/Sources/ChatMessageDateHeader.swift").read_text(encoding="utf-8")
    for source, value in (
        (runtime, "guard defaults.object(forKey: chatAvatarCornerPercentKey) != nil else { return 100 }"),
        (settings, "case chatRounding(Int32)"),
        (settings, 'isChat: true'),
        (chat, "AYU_CHAT_AVATAR_ROUNDING_v2"),
        (chat, "ayuChatAvatarCornerRadius"),
    ):
        if value not in source:
            raise RuntimeError(f"chat avatar rounding incomplete: {value}")
    print("[ayu-chat-avatar-rounding] independent outside/chat sliders installed; both default to Telegram circle 100")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
