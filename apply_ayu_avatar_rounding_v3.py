#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
from pathlib import Path


MARK = "AYU_AVATAR_ROUNDING_SCOPES_v3"


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
        '    private static let chatAvatarCornerPercentKey = keyPrefix + "appearance.chatAvatarCornerPercent"\n',
        '    private static let chatAvatarCornerPercentKey = keyPrefix + "appearance.chatAvatarCornerPercent"\n'
        '    // AYU_AVATAR_ROUNDING_SCOPES_v3\n'
        '    private static let profileAvatarCornerPercentKey = keyPrefix + "appearance.profileAvatarCornerPercent"\n',
        "profile key",
    )
    text = one(
        text,
        '''    private static let chatAvatarCornerPercentState = Atomic<Int32>(value: {
        let defaults = UserDefaults.standard
        guard defaults.object(forKey: chatAvatarCornerPercentKey) != nil else { return 100 }
        return Int32(max(0, min(100, defaults.integer(forKey: chatAvatarCornerPercentKey))))
    }())
''',
        '''    private static let chatAvatarCornerPercentState = Atomic<Int32>(value: {
        let defaults = UserDefaults.standard
        guard defaults.object(forKey: chatAvatarCornerPercentKey) != nil else { return 100 }
        return Int32(max(0, min(100, defaults.integer(forKey: chatAvatarCornerPercentKey))))
    }())
    private static let profileAvatarCornerPercentState = Atomic<Int32>(value: {
        let defaults = UserDefaults.standard
        guard defaults.object(forKey: profileAvatarCornerPercentKey) != nil else { return 100 }
        return Int32(max(0, min(100, defaults.integer(forKey: profileAvatarCornerPercentKey))))
    }())
''',
        "profile state",
    )
    text = one(
        text,
        '''    public static var chatAvatarCornerPercent: Int32 {
        return chatAvatarCornerPercentState.with { $0 }
    }
''',
        '''    public static var chatAvatarCornerPercent: Int32 {
        return chatAvatarCornerPercentState.with { $0 }
    }

    public static var profileAvatarCornerPercent: Int32 {
        return profileAvatarCornerPercentState.with { $0 }
    }
''',
        "profile getter",
    )
    text = one(
        text,
        '''    public static var avatarCornerConfiguration: Int32 {
        let percent = avatarCornerPercent
        return unifiedAvatarCorners ? percent | 0x100 : percent
    }
''',
        '''    public static var avatarCornerConfiguration: Int32 {
        // Scoped layer clipping owns customization. Keep generated avatars on
        // Telegram's stable cache identity and avoid global redraws.
        return 0
    }
''',
        "stable avatar cache identity",
    )
    text = one(
        text,
        '''    public static func setUnifiedAvatarCorners(_ value: Bool) {
''',
        '''    public static func setProfileAvatarCornerPercent(_ value: Int32) {
        let normalized = max(0, min(100, value))
        let previous = profileAvatarCornerPercentState.swap(normalized)
        if previous != normalized {
            UserDefaults.standard.set(Int(normalized), forKey: profileAvatarCornerPercentKey)
        }
    }

    public static func setUnifiedAvatarCorners(_ value: Bool) {
''',
        "profile setter",
    )
    path.write_text(text, encoding="utf-8")


def patch_avatar_node(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return
    old_helper = '''// AYU_AVATAR_ROUNDING_v1: one Atomic-backed calculation per avatar configuration/render, never per frame.
public func ayuAvatarCornerRadius(clipStyle: AvatarNodeClipStyle, size: CGSize) -> CGFloat {
    let edge = min(size.width, size.height)
    switch clipStyle {
    case .round:
        return floor(edge * 0.5 * CGFloat(AyuRuntimeSettings.avatarCornerPercent) / 100.0)
    case .roundedRect:
        if AyuRuntimeSettings.unifiedAvatarCorners {
            return floor(edge * 0.5 * CGFloat(AyuRuntimeSettings.avatarCornerPercent) / 100.0)
        } else {
            return floor(edge * 0.25)
        }
    case .none, .bubble:
        return 0.0
    }
}
'''
    new_helper = '''// AYU_AVATAR_ROUNDING_v1 / AYU_AVATAR_ROUNDING_SCOPES_v3:
// generated avatars retain Telegram's native geometry. Customization is scoped
// to chat-list, message, and profile presentation layers below.
public func ayuAvatarCornerRadius(clipStyle: AvatarNodeClipStyle, size: CGSize) -> CGFloat {
    let edge = min(size.width, size.height)
    switch clipStyle {
    case .round:
        return floor(edge * 0.5)
    case .roundedRect:
        return floor(edge * 0.25)
    case .none, .bubble:
        return 0.0
    }
}

public func ayuProfileAvatarCornerRadius(size: CGSize) -> CGFloat {
    let edge = min(size.width, size.height)
    return floor(edge * 0.5 * CGFloat(AyuRuntimeSettings.profileAvatarCornerPercent) / 100.0)
}

public enum AyuAvatarRoundingScope {
    case chatList(isForum: Bool)
    case chatMessage
    case profile
}

// Weak, main-thread-only registry. It is touched only when an avatar is bound or
// a setting changes; there is no timer, display link, polling, or per-frame work.
private let ayuScopedAvatarNodes = NSHashTable<AvatarNode>.weakObjects()

public func ayuRefreshVisibleAvatarRounding() {
    assert(Thread.isMainThread)
    for node in ayuScopedAvatarNodes.allObjects {
        node.ayuApplyRoundingScope()
    }
}
'''
    text = one(text, old_helper, new_helper, "stock global helper and scoped registry")

    text = one(
        text,
        '''    public let contentNode: ContentNode
    private var storyIndicator: ComponentView<Empty>?
''',
        '''    public let contentNode: ContentNode
    private var ayuRoundingScope: AyuAvatarRoundingScope?
    private var ayuRoundingSize: CGSize = .zero
    private var storyIndicator: ComponentView<Empty>?
''',
        "scope storage",
    )
    method_anchor = '''    public var imageNode: ImageNode {
        return self.contentNode.imageNode
    }
    
'''
    methods = method_anchor + '''    public func ayuSetRoundingScope(_ scope: AyuAvatarRoundingScope?, size: CGSize) {
        assert(Thread.isMainThread)
        self.ayuRoundingScope = scope
        self.ayuRoundingSize = size
        if scope == nil {
            ayuScopedAvatarNodes.remove(self)
        } else {
            ayuScopedAvatarNodes.add(self)
        }
        self.ayuApplyRoundingScope()
    }

    fileprivate func ayuApplyRoundingScope() {
        guard let scope = self.ayuRoundingScope else {
            self.contentNode.clipsToBounds = false
            self.contentNode.cornerRadius = 0.0
            return
        }
        let edge = min(self.ayuRoundingSize.width, self.ayuRoundingSize.height)
        let percent: Int32
        switch scope {
        case let .chatList(isForum):
            if isForum && !AyuRuntimeSettings.unifiedAvatarCorners {
                self.contentNode.clipsToBounds = true
                self.contentNode.cornerRadius = floor(edge * 0.25)
                return
            }
            percent = AyuRuntimeSettings.avatarCornerPercent
        case .chatMessage:
            percent = AyuRuntimeSettings.chatAvatarCornerPercent
        case .profile:
            percent = AyuRuntimeSettings.profileAvatarCornerPercent
        }
        self.contentNode.clipsToBounds = true
        self.contentNode.cornerRadius = floor(edge * 0.5 * CGFloat(percent) / 100.0)
    }

'''
    text = one(text, method_anchor, methods, "scope methods")
    text = one(
        text,
        '''        self.contentNode.updateSize(size: size)
        
        self.updateStoryIndicator(transition: .immediate)
''',
        '''        self.contentNode.updateSize(size: size)
        if self.ayuRoundingScope != nil {
            self.ayuRoundingSize = size
            self.ayuApplyRoundingScope()
        }
        
        self.updateStoryIndicator(transition: .immediate)
''',
        "scope size refresh",
    )
    path.write_text(text, encoding="utf-8")


def patch_chat_list(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return
    style_anchor = '''            if peerIsMonoforum {
                avatarClipStyle = .bubble
            } else if isForumAvatar {
                avatarClipStyle = .roundedRect
            } else {
                avatarClipStyle = .round
            }

            if item.useCommunityViewLayout {
'''
    style_new = '''            if peerIsMonoforum {
                avatarClipStyle = .bubble
            } else if isForumAvatar {
                avatarClipStyle = .roundedRect
            } else {
                avatarClipStyle = .round
            }
            // AYU_AVATAR_ROUNDING_SCOPES_v3: keep the source unrounded so a
            // smaller radius can reveal corners immediately. Monoforum bubbles
            // retain Telegram's non-corner-radius mask.
            let ayuAvatarClipStyle: AvatarNodeClipStyle = peerIsMonoforum ? avatarClipStyle : .none

            if item.useCommunityViewLayout {
'''
    text = one(text, style_anchor, style_new, "chat-list unrounded source")
    if text.count("clipStyle: avatarClipStyle, synchronousLoad:") != 3:
        raise RuntimeError("chat-list clip style calls changed")
    text = text.replace("clipStyle: avatarClipStyle, synchronousLoad:", "clipStyle: ayuAvatarClipStyle, synchronousLoad:")
    end_anchor = '''                self.avatarNode.setPeer(context: item.context, theme: item.presentationData.theme, peer: avatarPeer, overrideImage: overrideImage, emptyColor: item.presentationData.theme.list.mediaPlaceholderColor, clipStyle: ayuAvatarClipStyle, synchronousLoad: synchronousLoads, displayDimensions: CGSize(width: 60.0, height: 60.0))
            }
            
            if peer.isPremium && peer.id != item.context.account.peerId {
'''
    end_new = '''                self.avatarNode.setPeer(context: item.context, theme: item.presentationData.theme, peer: avatarPeer, overrideImage: overrideImage, emptyColor: item.presentationData.theme.list.mediaPlaceholderColor, clipStyle: ayuAvatarClipStyle, synchronousLoad: synchronousLoads, displayDimensions: CGSize(width: 60.0, height: 60.0))
            }
            if peerIsMonoforum {
                self.avatarNode.ayuSetRoundingScope(nil, size: CGSize(width: avatarDiameter, height: avatarDiameter))
            } else {
                self.avatarNode.ayuSetRoundingScope(.chatList(isForum: isForumAvatar), size: CGSize(width: avatarDiameter, height: avatarDiameter))
            }
            
            if peer.isPremium && peer.id != item.context.account.peerId {
'''
    text = one(text, end_anchor, end_new, "chat-list live scope")
    path.write_text(text, encoding="utf-8")


def patch_chat_message(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return
    text = one(
        text,
        '''    // AYU_CHAT_AVATAR_ROUNDING_v2: layer clipping keeps the chat-only
    // radius independent from generated avatars used everywhere else.
    private func applyAyuChatCornerRadius() {
        let size = CGSize(width: avatarHeaderSize(), height: avatarHeaderSize())
        self.avatarNode.contentNode.clipsToBounds = true
        self.avatarNode.contentNode.cornerRadius = ayuChatAvatarCornerRadius(size: size)
    }
''',
        '''    // AYU_CHAT_AVATAR_ROUNDING_v2 / AYU_AVATAR_ROUNDING_SCOPES_v3
    private func applyAyuChatCornerRadius() {
        let size = CGSize(width: avatarHeaderSize(), height: avatarHeaderSize())
        self.avatarNode.ayuSetRoundingScope(.chatMessage, size: size)
    }
''',
        "message live scope",
    )
    text = one(
        text,
        "            videoNode.updateLayout(size: self.avatarNode.bounds.size, cornerRadius: ayuChatAvatarCornerRadius(size: self.avatarNode.bounds.size), transition: .immediate)\n",
        "            videoNode.updateLayout(size: self.avatarNode.bounds.size, cornerRadius: 0.0, transition: .immediate)\n",
        "unrounded message video source",
    )
    path.write_text(text, encoding="utf-8")


def patch_profiles(root: Path) -> None:
    source_dir = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources"
    names = (
        "PeerInfoAvatarTransformContainerNode.swift",
        "PeerInfoEditingAvatarNode.swift",
        "PeerInfoHeaderNode.swift",
        "PeerInfoEditingAvatarOverlayNode.swift",
    )
    for name in names:
        path = source_dir / name
        text = path.read_text(encoding="utf-8")
        if MARK in text:
            continue
        text = text.replace(
            "ayuAvatarCornerRadius(clipStyle: isForum ? .roundedRect : .round, size: CGSize(width: avatarSize, height: avatarSize))",
            "ayuProfileAvatarCornerRadius(size: CGSize(width: avatarSize, height: avatarSize))",
        )
        text = text.replace(
            "ayuAvatarCornerRadius(clipStyle: clipStyle, size: CGSize(width: avatarSize, height: avatarSize))",
            "ayuProfileAvatarCornerRadius(size: CGSize(width: avatarSize, height: avatarSize))",
        )
        if name == "PeerInfoAvatarTransformContainerNode.swift":
            anchor = "            self.avatarNode.setPeer(context: self.context, theme: theme, peer: peer, overrideImage: overrideImage, clipStyle: .none, synchronousLoad: self.isFirstAvatarLoading, displayDimensions: CGSize(width: avatarSize, height: avatarSize), storeUnrounded: true)\n"
            text = one(text, anchor, anchor + "            self.avatarNode.ayuSetRoundingScope(.profile, size: CGSize(width: avatarSize, height: avatarSize))\n", "transform profile scope")
        elif name == "PeerInfoEditingAvatarNode.swift":
            anchor = "        self.avatarNode.setPeer(context: self.context, theme: theme, peer: peer, overrideImage: overrideImage, clipStyle: .none, synchronousLoad: false, displayDimensions: CGSize(width: avatarSize, height: avatarSize))\n"
            text = one(text, anchor, anchor + "        self.avatarNode.ayuSetRoundingScope(.profile, size: CGSize(width: avatarSize, height: avatarSize))\n", "editing profile scope")
        else:
            text = f"// {MARK}\n" + text
        if name == "PeerInfoEditingAvatarOverlayNode.swift":
            text = one(text, "            clipStyle = .roundedRect\n", "            clipStyle = .none\n", "forum upload source")
            text = one(text, "            clipStyle = .round\n", "            clipStyle = .none\n", "regular upload source")
            frame_anchor = "        self.imageNode.frame = CGRect(origin: CGPoint(x: -avatarSize / 2.0, y: -avatarSize / 2.0), size: CGSize(width: avatarSize, height: avatarSize))\n        self.updatingAvatarOverlay.frame = self.imageNode.frame\n"
            text = one(text, frame_anchor, frame_anchor + "        self.imageNode.clipsToBounds = true\n        self.imageNode.cornerRadius = ayuProfileAvatarCornerRadius(size: CGSize(width: avatarSize, height: avatarSize))\n", "upload image profile radius")
        if "ayuProfileAvatarCornerRadius" not in text:
            raise RuntimeError(f"profile radius missing: {name}")
        if MARK not in text:
            text = f"// {MARK}\n" + text
        path.write_text(text, encoding="utf-8")


def patch_settings(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return
    text = one(text, "import Display\n", "import Display\nimport AvatarNode\n", "AvatarNode import")
    start = text.find("// AYU_AVATAR_ROUNDING_v1: exteraGram appearance settings")
    end = text.find("private final class AyuExteraArguments {", start)
    if start < 0 or end < 0:
        raise RuntimeError("appearance controller block missing")
    block = '''// AYU_AVATAR_ROUNDING_v1 / AYU_CHAT_AVATAR_ROUNDING_v2 / AYU_AVATAR_ROUNDING_SCOPES_v3
private final class AyuAppearanceArguments {
    let updateListCornerPercent: (Int32) -> Void
    let updateUnified: (Bool) -> Void
    let updateChatCornerPercent: (Int32) -> Void
    let updateProfileCornerPercent: (Int32) -> Void

    init(updateListCornerPercent: @escaping (Int32) -> Void, updateUnified: @escaping (Bool) -> Void, updateChatCornerPercent: @escaping (Int32) -> Void, updateProfileCornerPercent: @escaping (Int32) -> Void) {
        self.updateListCornerPercent = updateListCornerPercent
        self.updateUnified = updateUnified
        self.updateChatCornerPercent = updateChatCornerPercent
        self.updateProfileCornerPercent = updateProfileCornerPercent
    }
}

private enum AyuAppearanceSection: Int32 {
    case list
    case chat
    case profile
}

private enum AyuAppearanceEntry: ItemListNodeEntry {
    case header
    case listRounding(Int32)
    case unified(Bool)
    case info
    case chatRounding(Int32)
    case profileRounding(Int32)

    var section: ItemListSectionId {
        switch self {
        case .header, .listRounding, .unified, .info:
            return AyuAppearanceSection.list.rawValue
        case .chatRounding:
            return AyuAppearanceSection.chat.rawValue
        case .profileRounding:
            return AyuAppearanceSection.profile.rawValue
        }
    }
    var stableId: Int32 {
        switch self {
        case .header: return 0
        case .listRounding: return 1
        case .unified: return 2
        case .info: return 3
        case .chatRounding: return 4
        case .profileRounding: return 5
        }
    }
    static func <(lhs: AyuAppearanceEntry, rhs: AyuAppearanceEntry) -> Bool { lhs.stableId < rhs.stableId }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let arguments = arguments as! AyuAppearanceArguments
        switch self {
        case .header:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "АВАТАРЫ", sectionId: self.section)
        case let .listRounding(value):
            return AyuAvatarRoundingItem(theme: presentationData.theme, value: value, preview: .chatList, sectionId: self.section, updated: arguments.updateListCornerPercent)
        case let .unified(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Единое закругление", value: value, sectionId: self.section, style: .blocks, updated: arguments.updateUnified)
        case .info:
            return ItemListTextItem(presentationData: presentationData, text: .plain("При включении форумы в списке чатов используют то же закругление."), sectionId: self.section)
        case let .chatRounding(value):
            return AyuAvatarRoundingItem(theme: presentationData.theme, value: value, preview: .chatMessage, sectionId: self.section, updated: arguments.updateChatCornerPercent)
        case let .profileRounding(value):
            return AyuAvatarRoundingItem(theme: presentationData.theme, value: value, preview: .profile, sectionId: self.section, updated: arguments.updateProfileCornerPercent)
        }
    }
}

private func ayuExteraAppearanceSettingsController(context: AccountContext) -> ViewController {
    let revision = ValuePromise<Int32>(0, ignoreRepeated: false)
    var revisionValue: Int32 = 0
    let bump: () -> Void = { revisionValue &+= 1; revision.set(revisionValue) }
    let arguments = AyuAppearanceArguments(updateListCornerPercent: { value in
        AyuRuntimeSettings.setAvatarCornerPercent(value)
        ayuRefreshVisibleAvatarRounding()
    }, updateUnified: { value in
        AyuRuntimeSettings.setUnifiedAvatarCorners(value)
        ayuRefreshVisibleAvatarRounding()
        bump()
    }, updateChatCornerPercent: { value in
        AyuRuntimeSettings.setChatAvatarCornerPercent(value)
        ayuRefreshVisibleAvatarRounding()
    }, updateProfileCornerPercent: { value in
        AyuRuntimeSettings.setProfileAvatarCornerPercent(value)
        ayuRefreshVisibleAvatarRounding()
    })
    let signal = combineLatest(context.sharedContext.presentationData, revision.get())
    |> deliverOnMainQueue
    |> map { presentationData, _ -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let entries: [AyuAppearanceEntry] = [
            .header,
            .listRounding(AyuRuntimeSettings.avatarCornerPercent),
            .unified(AyuRuntimeSettings.unifiedAvatarCorners),
            .info,
            .chatRounding(AyuRuntimeSettings.chatAvatarCornerPercent),
            .profileRounding(AyuRuntimeSettings.profileAvatarCornerPercent)
        ]
        let controllerState = ItemListControllerState(presentationData: ItemListPresentationData(presentationData), title: .text("Оформление"), leftNavigationButton: nil, rightNavigationButton: nil, backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back))
        return (controllerState, (ItemListNodeState(presentationData: ItemListPresentationData(presentationData), entries: entries, style: .blocks, animateChanges: true), arguments))
    }
    return ItemListController(context: context, state: signal)
}

'''
    text = text[:start] + block + text[end:]
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_avatar_rounding_v3.py <Telegram-iOS root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    patch_runtime(root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift")
    patch_avatar_node(root / "submodules/AvatarNode/Sources/AvatarNode.swift")
    patch_chat_list(root / "submodules/ChatListUI/Sources/Node/ChatListItem.swift")
    patch_chat_message(root / "submodules/TelegramUI/Components/Chat/ChatMessageItemImpl/Sources/ChatMessageDateHeader.swift")
    patch_profiles(root)
    patch_settings(root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift")
    shutil.copyfile(Path(__file__).resolve().parent / "payload/AyuAvatarRoundingItem.swift", root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuAvatarRoundingItem.swift")

    runtime = (root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift").read_text(encoding="utf-8")
    avatar = (root / "submodules/AvatarNode/Sources/AvatarNode.swift").read_text(encoding="utf-8")
    chat_list = (root / "submodules/ChatListUI/Sources/Node/ChatListItem.swift").read_text(encoding="utf-8")
    settings = (root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift").read_text(encoding="utf-8")
    checks = (
        (runtime, "profileAvatarCornerPercentState"),
        (avatar, "ayuRefreshVisibleAvatarRounding"),
        (avatar, "case chatList(isForum: Bool)"),
        (chat_list, ".ayuSetRoundingScope(.chatList(isForum: isForumAvatar)"),
        (settings, "preview: .profile"),
        (settings, "case .profileRounding"),
    )
    for source, value in checks:
        if value not in source:
            raise RuntimeError(f"avatar scope patch incomplete: {value}")
    print("[ayu-avatar-rounding-v3] list/chat/profile scopes; immediate event refresh; zero per-frame work")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
