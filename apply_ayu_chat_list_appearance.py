#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
from pathlib import Path


MARK = "AYU_CHAT_LIST_APPEARANCE_v4"


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
        "public struct AyuRuntimeSnapshot: Equatable {\n",
        """// AYU_CHAT_LIST_APPEARANCE_v4
public enum AyuChatListTitleMode: Int32, CaseIterable {
    case ayuGram = 0
    case username = 1
    case firstName = 2
    case chats = 3
}

public enum AyuFolderTitleMode: Int32, CaseIterable {
    case namesAndIcons = 0
    case namesOnly = 1
    case iconsOnly = 2
}

public struct AyuRuntimeSnapshot: Equatable {
""",
        "runtime enums",
    )
    text = one(
        text,
        '    private static let profileAvatarCornerPercentKey = keyPrefix + "appearance.profileAvatarCornerPercent"\n',
        '''    private static let profileAvatarCornerPercentKey = keyPrefix + "appearance.profileAvatarCornerPercent"
    private static let chatListForceSnowKey = keyPrefix + "appearance.chatListForceSnow"
    private static let chatListHideStatusKey = keyPrefix + "appearance.chatListHideStatus"
    private static let chatListHideStoriesKey = keyPrefix + "appearance.chatListHideStories"
    private static let chatListTitleModeKey = keyPrefix + "appearance.chatListTitleMode"
    private static let folderTitleModeKey = keyPrefix + "appearance.folderTitleMode"
    private static let folderUnreadBadgeKey = keyPrefix + "appearance.folderUnreadBadge"
''',
        "appearance keys",
    )
    text = one(
        text,
        '''    private static let profileAvatarCornerPercentState = Atomic<Int32>(value: {
        let defaults = UserDefaults.standard
        guard defaults.object(forKey: profileAvatarCornerPercentKey) != nil else { return 100 }
        return Int32(max(0, min(100, defaults.integer(forKey: profileAvatarCornerPercentKey))))
    }())
''',
        '''    private static let profileAvatarCornerPercentState = Atomic<Int32>(value: {
        let defaults = UserDefaults.standard
        guard defaults.object(forKey: profileAvatarCornerPercentKey) != nil else { return 100 }
        return Int32(max(0, min(100, defaults.integer(forKey: profileAvatarCornerPercentKey))))
    }())
    private static let chatListForceSnowState = Atomic<Bool>(value: UserDefaults.standard.bool(forKey: chatListForceSnowKey))
    private static let chatListHideStatusState = Atomic<Bool>(value: UserDefaults.standard.bool(forKey: chatListHideStatusKey))
    private static let chatListHideStoriesState = Atomic<Bool>(value: UserDefaults.standard.bool(forKey: chatListHideStoriesKey))
    private static let chatListTitleModeState = Atomic<Int32>(value: Int32(UserDefaults.standard.integer(forKey: chatListTitleModeKey)))
    private static let folderTitleModeState = Atomic<Int32>(value: Int32(UserDefaults.standard.integer(forKey: folderTitleModeKey)))
    private static let folderUnreadBadgeState = Atomic<Bool>(value: {
        let defaults = UserDefaults.standard
        guard defaults.object(forKey: folderUnreadBadgeKey) != nil else { return true }
        return defaults.bool(forKey: folderUnreadBadgeKey)
    }())
    private static let chatListIdentityState = Atomic<(String, String)>(value: ("", ""))
''',
        "appearance states",
    )
    text = one(
        text,
        '''    public static var unifiedAvatarCorners: Bool {
        return unifiedAvatarCornersState.with { $0 }
    }
''',
        '''    public static var unifiedAvatarCorners: Bool {
        return unifiedAvatarCornersState.with { $0 }
    }

    public static let chatListAppearanceDidChange = Notification.Name("AyuChatListAppearanceDidChange")

    public static var chatListForceSnow: Bool { chatListForceSnowState.with { $0 } }
    public static var chatListHideStatus: Bool { chatListHideStatusState.with { $0 } }
    public static var chatListHideStories: Bool { chatListHideStoriesState.with { $0 } }
    public static var chatListTitleMode: Int32 { chatListTitleModeState.with { $0 } }
    public static var folderTitleMode: Int32 { folderTitleModeState.with { $0 } }
    public static var folderUnreadBadge: Bool { folderUnreadBadgeState.with { $0 } }

    public static var chatListTitleModeTitle: String {
        switch AyuChatListTitleMode(rawValue: chatListTitleMode) ?? .ayuGram {
        case .ayuGram: return "AyuGram"
        case .username: return "Имя пользователя"
        case .firstName: return "Имя"
        case .chats: return "Чаты"
        }
    }

    public static var folderTitleModeTitle: String {
        switch AyuFolderTitleMode(rawValue: folderTitleMode) ?? .namesAndIcons {
        case .namesAndIcons: return "Названия и иконки"
        case .namesOnly: return "Только названия"
        case .iconsOnly: return "Только иконки"
        }
    }

    public static var chatListHeaderTitle: String {
        let identity = chatListIdentityState.with { $0 }
        switch AyuChatListTitleMode(rawValue: chatListTitleMode) ?? .ayuGram {
        case .ayuGram:
            return "AyuGram"
        case .username:
            return identity.0.isEmpty ? "AyuGram" : identity.0
        case .firstName:
            return identity.1.isEmpty ? "AyuGram" : identity.1
        case .chats:
            return "Чаты"
        }
    }

    public static func updateChatListIdentity(username: String, firstName: String) {
        let previous = chatListIdentityState.swap((username, firstName))
        if (previous.0 != username || previous.1 != firstName) && chatListTitleMode != AyuChatListTitleMode.ayuGram.rawValue && chatListTitleMode != AyuChatListTitleMode.chats.rawValue {
            notifyChatListAppearanceChanged()
        }
    }

    private static func notifyChatListAppearanceChanged() {
        NotificationCenter.default.post(name: chatListAppearanceDidChange, object: nil)
    }
''',
        "appearance getters",
    )
    text = one(
        text,
        '''    public static func setUnifiedAvatarCorners(_ value: Bool) {
        let previous = unifiedAvatarCornersState.swap(value)
        if previous != value {
            UserDefaults.standard.set(value, forKey: unifiedAvatarCornersKey)
        }
    }
''',
        '''    public static func setUnifiedAvatarCorners(_ value: Bool) {
        let previous = unifiedAvatarCornersState.swap(value)
        if previous != value {
            UserDefaults.standard.set(value, forKey: unifiedAvatarCornersKey)
        }
    }

    public static func setChatListForceSnow(_ value: Bool) {
        if chatListForceSnowState.swap(value) != value {
            UserDefaults.standard.set(value, forKey: chatListForceSnowKey)
            notifyChatListAppearanceChanged()
        }
    }

    public static func setChatListHideStatus(_ value: Bool) {
        if chatListHideStatusState.swap(value) != value {
            UserDefaults.standard.set(value, forKey: chatListHideStatusKey)
            notifyChatListAppearanceChanged()
        }
    }

    public static func setChatListHideStories(_ value: Bool) {
        if chatListHideStoriesState.swap(value) != value {
            UserDefaults.standard.set(value, forKey: chatListHideStoriesKey)
            notifyChatListAppearanceChanged()
        }
    }

    public static func setChatListTitleMode(_ value: Int32) {
        let normalized = AyuChatListTitleMode(rawValue: value)?.rawValue ?? AyuChatListTitleMode.ayuGram.rawValue
        if chatListTitleModeState.swap(normalized) != normalized {
            UserDefaults.standard.set(Int(normalized), forKey: chatListTitleModeKey)
            notifyChatListAppearanceChanged()
        }
    }

    public static func setFolderTitleMode(_ value: Int32) {
        let normalized = AyuFolderTitleMode(rawValue: value)?.rawValue ?? AyuFolderTitleMode.namesAndIcons.rawValue
        if folderTitleModeState.swap(normalized) != normalized {
            UserDefaults.standard.set(Int(normalized), forKey: folderTitleModeKey)
            notifyChatListAppearanceChanged()
        }
    }

    public static func setFolderUnreadBadge(_ value: Bool) {
        if folderUnreadBadgeState.swap(value) != value {
            UserDefaults.standard.set(value, forKey: folderUnreadBadgeKey)
            notifyChatListAppearanceChanged()
        }
    }
''',
        "appearance setters",
    )
    if MARK not in text:
        text = text.replace("// AYU_CHAT_LIST_APPEARANCE_v4\n", f"// {MARK}\n", 1)
    path.write_text(text, encoding="utf-8")


def patch_chat_list_controller(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return
    anchor = '''                guard case let .user(user) = peer else {
                    return nil
                }
                if let emojiStatus = user.emojiStatus {
'''
    replacement = '''                guard case let .user(user) = peer else {
                    return nil
                }
                // AYU_CHAT_LIST_APPEARANCE_v4: account identity is refreshed only
                // when Telegram's own peer signal changes, never during scrolling.
                AyuRuntimeSettings.updateChatListIdentity(username: user.username ?? "", firstName: user.firstName ?? "")
                if let emojiStatus = user.emojiStatus {
'''
    text = one(text, anchor, replacement, "account identity")
    text = one(
        text,
        '''        super.init(context: context, navigationBarPresentationData: nil)
        
        self.accessoryPanelContainer = ASDisplayNode()
''',
        '''        super.init(context: context, navigationBarPresentationData: nil)

        NotificationCenter.default.addObserver(self, selector: #selector(self.ayuChatListAppearanceChanged), name: AyuRuntimeSettings.chatListAppearanceDidChange, object: nil)
        
        self.accessoryPanelContainer = ASDisplayNode()
''',
        "chat list observer",
    )
    text = one(
        text,
        '''    required public init(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    deinit {
''',
        '''    @objc private func ayuChatListAppearanceChanged() {
        guard case .chatList(.root) = self.location else {
            return
        }
        self.primaryContext?.ayuRefreshAppearance()
        self.reloadFilters()
        self.requestLayout(transition: .immediate)
    }

    required public init(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    deinit {
        NotificationCenter.default.removeObserver(self)
''',
        "chat list refresh",
    )
    text = one(
        text,
        '''    private var initializedFilters = false
    private func reloadFilters(firstUpdate: (() -> Void)? = nil) {
''',
        r'''    private func ayuFolderTabTitle(_ title: ChatFolderTitle, emoticon: String?) -> ChatFolderTitle {
        switch AyuFolderTitleMode(rawValue: AyuRuntimeSettings.folderTitleMode) ?? .namesAndIcons {
        case .namesAndIcons:
            guard let emoticon, !emoticon.isEmpty else {
                return title
            }
            let prefix = "\(emoticon) "
            let offset = prefix.utf16.count
            let entities = title.entities.map { entity in
                MessageTextEntity(range: (entity.range.lowerBound + offset) ..< (entity.range.upperBound + offset), type: entity.type)
            }
            return ChatFolderTitle(text: prefix + title.text, entities: entities, enableAnimations: title.enableAnimations)
        case .namesOnly:
            return title
        case .iconsOnly:
            return ChatFolderTitle(text: (emoticon?.isEmpty == false ? emoticon! : "📁"), entities: [], enableAnimations: false)
        }
    }

    private var initializedFilters = false
    private func reloadFilters(firstUpdate: (() -> Void)? = nil) {
''',
        "folder title preparation",
    )
    text = one(
        text,
        '''                    case let .filter(id, title, _, _):
                        filterItems.append(.filter(id: id, text: title, unread: ChatListFilterTabEntryUnreadCount(value: unreadCount, hasUnmuted: hasUnmutedUnread)))
''',
        '''                    case let .filter(id, title, emoticon, _):
                        let ayuUnreadCount = AyuRuntimeSettings.folderUnreadBadge ? unreadCount : 0
                        filterItems.append(.filter(id: id, text: strongSelf.ayuFolderTabTitle(title, emoticon: emoticon), unread: ChatListFilterTabEntryUnreadCount(value: ayuUnreadCount, hasUnmuted: hasUnmutedUnread)))
''',
        "folder title application",
    )
    text = one(
        text,
        '''    private(set) var chatListTitle: NetworkStatusTitle?
    
    var leftButton: AnyComponentWithIdentity<NavigationButtonComponentEnvironment>?
''',
        '''    private(set) var chatListTitle: NetworkStatusTitle?
    private var ayuRootPeerStatus: NetworkStatusTitle.Status?

    func ayuRefreshAppearance() {
        guard case .chatList(.root) = self.location, var title = self.chatListTitle else {
            return
        }
        if !title.activity {
            title.text = AyuRuntimeSettings.chatListHeaderTitle
        }
        title.peerStatus = AyuRuntimeSettings.chatListHideStatus ? nil : self.ayuRootPeerStatus
        self.chatListTitle = title
    }
    
    var leftButton: AnyComponentWithIdentity<NavigationButtonComponentEnvironment>?
''',
        "root title model refresh",
    )
    text = one(
        text,
        '''            self.chatListTitle = titleContent
            
            if case .chatList(.root) = self.location, checkProxy {
''',
        '''            if case .chatList(.root) = self.location {
                self.ayuRootPeerStatus = peerStatus
                if !titleContent.activity {
                    titleContent.text = AyuRuntimeSettings.chatListHeaderTitle
                }
                titleContent.peerStatus = AyuRuntimeSettings.chatListHideStatus ? nil : peerStatus
            }
            self.chatListTitle = titleContent
            
            if case .chatList(.root) = self.location, checkProxy {
''',
        "root title model",
    )
    path.write_text(text, encoding="utf-8")


def patch_title_view(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return
    text = one(
        text,
        "    private let animationRenderer: MultiAnimationRenderer\n",
        '''    private let animationRenderer: MultiAnimationRenderer

    // AYU_CHAT_LIST_APPEARANCE_v4
    private var ayuRootTitleSource: NetworkStatusTitle?
''',
        "title source property",
    )
    text = one(
        text,
        '''    public func setTitle(_ title: NetworkStatusTitle, animated: Bool) {
        let oldValue = self._title
        self._title = title
''',
        '''    public func setTitle(_ inputTitle: NetworkStatusTitle, animated: Bool) {
        var title = inputTitle
        if !inputTitle.activity && inputTitle.text == "AyuGram" {
            self.ayuRootTitleSource = inputTitle
            title.text = AyuRuntimeSettings.chatListHeaderTitle
            if AyuRuntimeSettings.chatListHideStatus {
                title.peerStatus = nil
            }
        }
        let oldValue = self._title
        self._title = title
''',
        "title transform",
    )
    text = one(
        text,
        '''        super.init(frame: CGRect())
        
        self.isAccessibilityElement = false
''',
        '''        super.init(frame: CGRect())

        NotificationCenter.default.addObserver(self, selector: #selector(self.ayuChatListAppearanceChanged), name: AyuRuntimeSettings.chatListAppearanceDidChange, object: nil)
        
        self.isAccessibilityElement = false
''',
        "title observer",
    )
    text = one(
        text,
        '''    required public init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
''',
        '''    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    @objc private func ayuChatListAppearanceChanged() {
        guard !self._title.activity, let source = self.ayuRootTitleSource else {
            return
        }
        self.setTitle(source, animated: true)
        self.setNeedsLayout()
    }

    required public init?(coder aDecoder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
''',
        "title refresh",
    )
    text = one(
        text,
        "        let combinedWidth = titleSize.width\n",
        "        let combinedWidth = titleSize.width\n",
        "smart title width",
    )
    path.write_text(text, encoding="utf-8")


def patch_header_component(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return
    text = one(
        text,
        '''                    if let chatListTitle = primaryContent.chatListTitle {
                        primaryTitle = chatListTitle.text
                        primaryTitleHasLock = chatListTitle.isPasscodeSet
                        primaryTitleHasActivity = chatListTitle.activity
                        if let peerStatus = chatListTitle.peerStatus {
                            switch peerStatus {
                            case .premium:
                                primaryTitlePeerStatus = .premium
                            case let .emoji(status):
                                primaryTitlePeerStatus = .emoji(status)
                            }
                        }
''',
        '''                    if let chatListTitle = primaryContent.chatListTitle {
                        let ayuIsRootTitle = !chatListTitle.activity && chatListTitle.text == "AyuGram"
                        primaryTitle = ayuIsRootTitle ? AyuRuntimeSettings.chatListHeaderTitle : chatListTitle.text
                        primaryTitleHasLock = chatListTitle.isPasscodeSet
                        primaryTitleHasActivity = chatListTitle.activity
                        if (!ayuIsRootTitle || !AyuRuntimeSettings.chatListHideStatus), let peerStatus = chatListTitle.peerStatus {
                            switch peerStatus {
                            case .premium:
                                primaryTitlePeerStatus = .premium
                            case let .emoji(status):
                                primaryTitlePeerStatus = .emoji(status)
                            }
                        }
''',
        "stories title and status",
    )
    text = one(
        text,
        '''                    containerSize: CGSize(width: availableSize.width, height: ChatListNavigationBar.storiesScrollHeight)
                )
            }
            
            var secondaryContentTransition = transition
''',
        '''                    containerSize: CGSize(width: availableSize.width, height: ChatListNavigationBar.storiesScrollHeight)
                )
            } else if let storyPeerList = self.storyPeerList {
                self.storyPeerList = nil
                storyPeerList.view?.removeFromSuperview()
            }
            
            var secondaryContentTransition = transition
''',
        "remove hidden stories view",
    )
    text = "// AYU_CHAT_LIST_APPEARANCE_v4\n" + text
    path.write_text(text, encoding="utf-8")


def patch_navigation_bar(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return
    class_anchor = "public final class ChatListNavigationBar: Component {\n"
    snow = r'''// AYU_CHAT_LIST_APPEARANCE_v4: Core Animation owns every frame. No
// display link, timer, Swift particle loop or scroll callback is used.
private final class AyuChatListSnowView: UIView {
    private let emitter = CAEmitterLayer()
    private let cell = CAEmitterCell()
    private let fadeMask = CAGradientLayer()
    private var currentIsDark: Bool?

    private static func particleImage(color: UIColor) -> CGImage? {
        let imageSize = CGSize(width: 4.0, height: 4.0)
        UIGraphicsBeginImageContextWithOptions(imageSize, false, 0.0)
        color.setFill()
        UIBezierPath(ovalIn: CGRect(x: 1.0, y: 1.0, width: 2.0, height: 2.0)).fill()
        let image = UIGraphicsGetImageFromCurrentImageContext()?.cgImage
        UIGraphicsEndImageContext()
        return image
    }

    override init(frame: CGRect) {
        super.init(frame: frame)
        self.isUserInteractionEnabled = false
        self.clipsToBounds = true

        self.cell.birthRate = 7.0
        self.cell.lifetime = 3.2
        self.cell.lifetimeRange = 0.4
        // Gravity, rather than an emission angle, guarantees a vertical path
        // in the layer's coordinate system and leaves no horizontal velocity.
        self.cell.velocity = 0.0
        self.cell.velocityRange = 0.0
        self.cell.xAcceleration = 0.0
        self.cell.yAcceleration = 24.0
        self.cell.emissionRange = 0.0
        self.cell.scale = 0.55
        self.cell.scaleRange = 0.15
        self.cell.alphaSpeed = -0.075
        self.cell.spinRange = .pi

        self.emitter.emitterShape = .line
        self.emitter.emitterMode = .surface
        self.emitter.emitterCells = [self.cell]
        self.layer.addSublayer(self.emitter)

        self.fadeMask.colors = [
            UIColor.clear.cgColor,
            UIColor.black.cgColor,
            UIColor.black.cgColor,
            UIColor.clear.cgColor
        ]
        self.fadeMask.startPoint = CGPoint(x: 0.5, y: 0.0)
        self.fadeMask.endPoint = CGPoint(x: 0.5, y: 1.0)
        self.fadeMask.locations = [0.0, 0.12, 0.55, 1.0]
        self.layer.mask = self.fadeMask
        self.update(isDark: true)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func update(isDark: Bool) {
        guard self.currentIsDark != isDark else {
            return
        }
        self.currentIsDark = isDark
        let color = isDark ? UIColor.white : UIColor.black
        self.cell.contents = AyuChatListSnowView.particleImage(color: color)
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

public final class ChatListNavigationBar: Component {
'''
    text = one(text, class_anchor, snow, "snow class")
    text = one(
        text,
        "        private var pinnedFraction: CGFloat = 0.0\n",
        '''        private var pinnedFraction: CGFloat = 0.0
        private var ayuSnowView: AyuChatListSnowView?
''',
        "snow property",
    )
    text = one(
        text,
        '''            self.addSubview(self.edgeEffectView)
            self.addSubview(self.bottomContentsContainer)
''',
        '''            self.addSubview(self.edgeEffectView)
            self.addSubview(self.bottomContentsContainer)
            NotificationCenter.default.addObserver(self, selector: #selector(self.ayuChatListAppearanceChanged), name: AyuRuntimeSettings.chatListAppearanceDidChange, object: nil)
''',
        "snow observer",
    )
    text = one(
        text,
        '''        required init?(coder: NSCoder) {
            fatalError("init(coder:) has not been implemented")
        }
''',
        '''        deinit {
            NotificationCenter.default.removeObserver(self)
        }

        @objc private func ayuChatListAppearanceChanged() {
            self.ayuUpdateSnow()
            self.state?.updated(transition: .immediate)
            if let rawScrollOffset = self.rawScrollOffset {
                self.applyScroll(offset: rawScrollOffset, allowAvatarsExpansion: self.currentAllowAvatarsExpansion, forceUpdate: true, transition: .immediate)
            }
        }

        private func ayuUpdateSnow() {
            guard let component = self.component else {
                return
            }
            let enabled = AyuRuntimeSettings.chatListForceSnow && component.activeSearch == nil
            if enabled {
                let snowView: AyuChatListSnowView
                if let current = self.ayuSnowView {
                    snowView = current
                } else {
                    snowView = AyuChatListSnowView()
                    self.ayuSnowView = snowView
                    if self.headerBackgroundContainer.superview != nil {
                        self.insertSubview(snowView, aboveSubview: self.headerBackgroundContainer)
                    } else {
                        self.addSubview(snowView)
                    }
                }
                snowView.update(isDark: component.theme.overallDarkAppearance)
                let navigationHeight = self.currentLayout?.size.height ?? self.bounds.height
                let availableTitleHeight = max(0.0, navigationHeight - component.statusBarHeight)
                snowView.frame = CGRect(x: 0.0, y: component.statusBarHeight, width: self.bounds.width, height: min(54.0, availableTitleHeight))
                snowView.isHidden = false
            } else if let snowView = self.ayuSnowView {
                snowView.isHidden = true
            }
        }

        required init?(coder: NSCoder) {
            fatalError("init(coder:) has not been implemented")
        }
''',
        "snow refresh",
    )
    text = one(
        text,
        '''            self.edgeEffectView.isHidden = !component.hasEdgeEffect
            
            return size
''',
        '''            self.edgeEffectView.isHidden = !component.hasEdgeEffect
            self.ayuUpdateSnow()
            
            return size
''',
        "snow layout",
    )
    text = one(
        text,
        '''            guard let component = self.component, let currentLayout = self.currentLayout else {
                return
            }
            
            let themeUpdated = component.theme !== self.scrollTheme || component.strings !== self.scrollStrings
''',
        '''            guard let component = self.component, let currentLayout = self.currentLayout else {
                return
            }
            
            let themeUpdated = component.theme !== self.scrollTheme || component.strings !== self.scrollStrings
''',
        "hidden stories source",
    )
    text = one(
        text,
        "            if allowAvatarsExpansion, transition.animation.isImmediate, let storySubscriptions = component.storySubscriptions, !storySubscriptions.items.isEmpty {\n",
        "            let ayuStorySubscriptions = AyuRuntimeSettings.chatListHideStories && storiesOffsetFraction < 0.01 ? nil : component.storySubscriptions\n\n            if allowAvatarsExpansion, transition.animation.isImmediate, let storySubscriptions = ayuStorySubscriptions, !storySubscriptions.items.isEmpty {\n",
        "hidden stories haptic",
    )
    text = one(
        text,
        '''                networkStatus: nil,
                storySubscriptions: component.storySubscriptions,
                storiesIncludeHidden: component.storiesIncludeHidden,
''',
        '''                networkStatus: nil,
                storySubscriptions: ayuStorySubscriptions,
                storiesIncludeHidden: component.storiesIncludeHidden,
''',
        "hidden stories header",
    )
    path.write_text(text, encoding="utf-8")


def patch_folder_tabs(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return
    helper_anchor = "private final class ItemNode: ASDisplayNode {\n"
    helper = r'''// AYU_CHAT_LIST_APPEARANCE_v4
private func ayuFolderDisplayTitle(_ source: ChatFolderTitle, isAllChats: Bool) -> ChatFolderTitle {
    return source
}

private final class ItemNode: ASDisplayNode {
'''
    text = one(text, helper_anchor, helper, "folder title helper")
    text = one(
        text,
        '''    func updateText(strings: PresentationStrings, title: ChatFolderTitle, shortTitle: ChatFolderTitle, unreadCount: Int, unreadHasUnmuted: Bool, isNoFilter: Bool, selectionFraction: CGFloat, isEditing: Bool, isReordering: Bool, canReorderAllChats: Bool, isDisabled: Bool, presentationData: PresentationData, transition: ContainedViewLayoutTransition) {
        self.isEditing = isEditing
''',
        '''    func updateText(strings: PresentationStrings, title sourceTitle: ChatFolderTitle, shortTitle sourceShortTitle: ChatFolderTitle, unreadCount sourceUnreadCount: Int, unreadHasUnmuted: Bool, isNoFilter: Bool, selectionFraction: CGFloat, isEditing: Bool, isReordering: Bool, canReorderAllChats: Bool, isDisabled: Bool, presentationData: PresentationData, transition: ContainedViewLayoutTransition) {
        let title = ayuFolderDisplayTitle(sourceTitle, isAllChats: isNoFilter)
        let shortTitle = ayuFolderDisplayTitle(sourceShortTitle, isAllChats: isNoFilter)
        let unreadCount = AyuRuntimeSettings.folderUnreadBadge ? sourceUnreadCount : 0
        self.isEditing = isEditing
''',
        "folder mode hot path",
    )
    text = one(
        text,
        "    private var currentParams: (size: CGSize, sideInset: CGFloat, filters: [ChatListFilterTabEntry], selectedFilter: ChatListFilterTabEntryId?, isReordering: Bool, isEditing: Bool, canReorderAllChats: Bool, filtersLimit: Int32?, transitionFraction: CGFloat, presentationData: PresentationData)?\n",
        '''    private var currentParams: (size: CGSize, sideInset: CGFloat, filters: [ChatListFilterTabEntry], selectedFilter: ChatListFilterTabEntryId?, isReordering: Bool, isEditing: Bool, canReorderAllChats: Bool, filtersLimit: Int32?, transitionFraction: CGFloat, presentationData: PresentationData)?
''',
        "folder params marker",
    )
    text = one(
        text,
        '''        super.init()
        
        self.view.addSubview(self.backgroundContainerView)
''',
        '''        super.init()

        NotificationCenter.default.addObserver(self, selector: #selector(self.ayuChatListAppearanceChanged), name: AyuRuntimeSettings.chatListAppearanceDidChange, object: nil)
        
        self.view.addSubview(self.backgroundContainerView)
''',
        "folder observer",
    )
    text = one(
        text,
        '''    private var previousSelectedAbsFrame: CGRect?
''',
        '''    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    @objc private func ayuChatListAppearanceChanged() {
        guard let (size, sideInset, filters, selectedFilter, isReordering, isEditing, canReorderAllChats, filtersLimit, transitionFraction, presentationData) = self.currentParams else {
            return
        }
        self.update(size: size, sideInset: sideInset, filters: filters, selectedFilter: selectedFilter, isReordering: isReordering, isEditing: isEditing, canReorderAllChats: canReorderAllChats, filtersLimit: filtersLimit, transitionFraction: transitionFraction, presentationData: presentationData, transition: .immediate)
    }

    private var previousSelectedAbsFrame: CGRect?
''',
        "folder refresh",
    )
    path.write_text(text, encoding="utf-8")


def patch_settings(path: Path, build_path: Path, payload: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return
    text = one(text, "import AvatarNode\n", "import AvatarNode\nimport ChatListUI\nimport ChatListTitleView\n", "settings imports")
    start = text.find("// AYU_AVATAR_ROUNDING_v1 / AYU_CHAT_AVATAR_ROUNDING_v2 / AYU_AVATAR_ROUNDING_SCOPES_v3")
    end = text.find("private final class AyuExteraArguments {", start)
    if start < 0 or end < 0:
        raise RuntimeError("appearance block missing")
    block = r'''// AYU_AVATAR_ROUNDING_v1 / AYU_CHAT_AVATAR_ROUNDING_v2 / AYU_AVATAR_ROUNDING_SCOPES_v3 / AYU_CHAT_LIST_APPEARANCE_v4
private final class AyuAppearanceArguments {
    let context: AccountContext
    let updateListCornerPercent: (Int32) -> Void
    let updateUnified: (Bool) -> Void
    let updateChatCornerPercent: (Int32) -> Void
    let updateProfileCornerPercent: (Int32) -> Void
    let updateForceSnow: (Bool) -> Void
    let updateHideStatus: (Bool) -> Void
    let updateHideStories: (Bool) -> Void
    let selectTitleMode: () -> Void
    let selectFolderMode: () -> Void
    let updateFolderUnread: (Bool) -> Void

    init(context: AccountContext, updateListCornerPercent: @escaping (Int32) -> Void, updateUnified: @escaping (Bool) -> Void, updateChatCornerPercent: @escaping (Int32) -> Void, updateProfileCornerPercent: @escaping (Int32) -> Void, updateForceSnow: @escaping (Bool) -> Void, updateHideStatus: @escaping (Bool) -> Void, updateHideStories: @escaping (Bool) -> Void, selectTitleMode: @escaping () -> Void, selectFolderMode: @escaping () -> Void, updateFolderUnread: @escaping (Bool) -> Void) {
        self.context = context
        self.updateListCornerPercent = updateListCornerPercent
        self.updateUnified = updateUnified
        self.updateChatCornerPercent = updateChatCornerPercent
        self.updateProfileCornerPercent = updateProfileCornerPercent
        self.updateForceSnow = updateForceSnow
        self.updateHideStatus = updateHideStatus
        self.updateHideStories = updateHideStories
        self.selectTitleMode = selectTitleMode
        self.selectFolderMode = selectFolderMode
        self.updateFolderUnread = updateFolderUnread
    }
}

private enum AyuAppearanceSection: Int32 {
    case avatars
    case chatAvatar
    case profileAvatar
    case chatList
    case folders
}

private enum AyuAppearanceEntry: ItemListNodeEntry {
    case avatarsHeader
    case listRounding(Int32)
    case unified(Bool)
    case avatarInfo
    case chatRounding(Int32)
    case profileRounding(Int32)
    case chatListHeader
    case chatListPreview(String, NetworkStatusTitle.Status?, Bool)
    case forceSnow(Bool)
    case hideStatus(Bool)
    case hideStories(Bool)
    case titleText(String)
    case foldersHeader
    case foldersPreview([AyuFolderPreview], Int32, Bool)
    case folderTitles(String)
    case folderUnread(Bool)
    case foldersInfo

    var section: ItemListSectionId {
        switch self {
        case .avatarsHeader, .listRounding, .unified, .avatarInfo: return AyuAppearanceSection.avatars.rawValue
        case .chatRounding: return AyuAppearanceSection.chatAvatar.rawValue
        case .profileRounding: return AyuAppearanceSection.profileAvatar.rawValue
        case .chatListHeader, .chatListPreview, .forceSnow, .hideStatus, .hideStories, .titleText: return AyuAppearanceSection.chatList.rawValue
        case .foldersHeader, .foldersPreview, .folderTitles, .folderUnread, .foldersInfo: return AyuAppearanceSection.folders.rawValue
        }
    }

    var stableId: Int32 {
        switch self {
        case .avatarsHeader: return 0
        case .listRounding: return 1
        case .unified: return 2
        case .avatarInfo: return 3
        case .chatRounding: return 4
        case .profileRounding: return 5
        case .chatListHeader: return 6
        case .chatListPreview: return 7
        case .forceSnow: return 8
        case .hideStatus: return 9
        case .hideStories: return 10
        case .titleText: return 11
        case .foldersHeader: return 12
        case .foldersPreview: return 13
        case .folderTitles: return 14
        case .folderUnread: return 15
        case .foldersInfo: return 16
        }
    }

    static func <(lhs: AyuAppearanceEntry, rhs: AyuAppearanceEntry) -> Bool {
        lhs.stableId < rhs.stableId
    }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let arguments = arguments as! AyuAppearanceArguments
        switch self {
        case .avatarsHeader:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "АВАТАРЫ", sectionId: self.section)
        case let .listRounding(value):
            return AyuAvatarRoundingItem(theme: presentationData.theme, value: value, preview: .chatList, sectionId: self.section, updated: arguments.updateListCornerPercent)
        case let .unified(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Единое закругление", value: value, sectionId: self.section, style: .blocks, updated: arguments.updateUnified)
        case .avatarInfo:
            return ItemListTextItem(presentationData: presentationData, text: .plain("При включении форумы в списке чатов используют то же закругление."), sectionId: self.section)
        case let .chatRounding(value):
            return AyuAvatarRoundingItem(theme: presentationData.theme, value: value, preview: .chatMessage, sectionId: self.section, updated: arguments.updateChatCornerPercent)
        case let .profileRounding(value):
            return AyuAvatarRoundingItem(theme: presentationData.theme, value: value, preview: .profile, sectionId: self.section, updated: arguments.updateProfileCornerPercent)
        case .chatListHeader:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "СПИСОК ЧАТОВ", sectionId: self.section)
        case let .chatListPreview(title, status, snow):
            return AyuChatListAppearancePreviewItem(context: arguments.context, theme: presentationData.theme, strings: presentationData.strings, preview: .header(title: title, status: status, snow: snow), sectionId: self.section)
        case let .forceSnow(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Принудительный снег", value: value, sectionId: self.section, style: .blocks, updated: arguments.updateForceSnow)
        case let .hideStatus(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Скрыть статус", value: value, sectionId: self.section, style: .blocks, updated: arguments.updateHideStatus)
        case let .hideStories(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Скрыть истории", value: value, sectionId: self.section, style: .blocks, updated: arguments.updateHideStories)
        case let .titleText(value):
            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: "Текст в заголовке", label: value, sectionId: self.section, style: .blocks, action: arguments.selectTitleMode)
        case .foldersHeader:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "ПАПКИ С ЧАТАМИ", sectionId: self.section)
        case let .foldersPreview(folders, mode, showUnread):
            return AyuChatListAppearancePreviewItem(context: arguments.context, theme: presentationData.theme, strings: presentationData.strings, preview: .folders(items: folders, mode: mode, showUnread: showUnread), sectionId: self.section)
        case let .folderTitles(value):
            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: "Заголовки папок", label: value, sectionId: self.section, style: .blocks, action: arguments.selectFolderMode)
        case let .folderUnread(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Счётчик уведомлений", value: value, sectionId: self.section, style: .blocks, updated: arguments.updateFolderUnread)
        case .foldersInfo:
            return ItemListTextItem(presentationData: presentationData, text: .plain("Иконки папок синхронизируются с вашим аккаунтом."), sectionId: self.section)
        }
    }
}

private func ayuExteraAppearanceSettingsController(context: AccountContext) -> ViewController {
    let revision = ValuePromise<Int32>(0, ignoreRepeated: false)
    var revisionValue: Int32 = 0
    let bump: () -> Void = { revisionValue &+= 1; revision.set(revisionValue) }
    let controllerBox = AyuWeakControllerBox()

    let presentTitleMode: () -> Void = {
        guard let host = controllerBox.value else { return }
        let presentationData = context.sharedContext.currentPresentationData.with { $0 }
        let actionSheet = ActionSheetController(presentationData: presentationData)
        let dismiss: () -> Void = { [weak actionSheet] in actionSheet?.dismissAnimated() }
        let current = AyuChatListTitleMode(rawValue: AyuRuntimeSettings.chatListTitleMode) ?? .ayuGram
        let options: [(AyuChatListTitleMode, String)] = [
            (.ayuGram, "AyuGram"),
            (.username, "Имя пользователя"),
            (.firstName, "Имя"),
            (.chats, "Чаты")
        ]
        let items: [ActionSheetItem] = options.map { mode, title in
            ActionSheetButtonItem(title: mode == current ? "✓ \(title)" : title, action: {
                dismiss()
                AyuRuntimeSettings.setChatListTitleMode(mode.rawValue)
                bump()
            })
        }
        actionSheet.setItemGroups([
            ActionSheetItemGroup(items: items),
            ActionSheetItemGroup(items: [ActionSheetButtonItem(title: presentationData.strings.Common_Cancel, color: .accent, font: .bold, action: dismiss)])
        ])
        host.present(actionSheet, in: .window(.root))
    }

    let presentFolderMode: () -> Void = {
        guard let host = controllerBox.value else { return }
        let presentationData = context.sharedContext.currentPresentationData.with { $0 }
        let actionSheet = ActionSheetController(presentationData: presentationData)
        let dismiss: () -> Void = { [weak actionSheet] in actionSheet?.dismissAnimated() }
        let current = AyuFolderTitleMode(rawValue: AyuRuntimeSettings.folderTitleMode) ?? .namesAndIcons
        let options: [(AyuFolderTitleMode, String)] = [
            (.namesAndIcons, "Названия и иконки"),
            (.namesOnly, "Только названия"),
            (.iconsOnly, "Только иконки")
        ]
        let items: [ActionSheetItem] = options.map { mode, title in
            ActionSheetButtonItem(title: mode == current ? "✓ \(title)" : title, action: {
                dismiss()
                AyuRuntimeSettings.setFolderTitleMode(mode.rawValue)
                bump()
            })
        }
        actionSheet.setItemGroups([
            ActionSheetItemGroup(items: items),
            ActionSheetItemGroup(items: [ActionSheetButtonItem(title: presentationData.strings.Common_Cancel, color: .accent, font: .bold, action: dismiss)])
        ])
        host.present(actionSheet, in: .window(.root))
    }

    let arguments = AyuAppearanceArguments(
        context: context,
        updateListCornerPercent: { value in
            AyuRuntimeSettings.setAvatarCornerPercent(value)
            ayuRefreshVisibleAvatarRounding()
        },
        updateUnified: { value in
            AyuRuntimeSettings.setUnifiedAvatarCorners(value)
            ayuRefreshVisibleAvatarRounding()
            bump()
        },
        updateChatCornerPercent: { value in
            AyuRuntimeSettings.setChatAvatarCornerPercent(value)
            ayuRefreshVisibleAvatarRounding()
        },
        updateProfileCornerPercent: { value in
            AyuRuntimeSettings.setProfileAvatarCornerPercent(value)
            ayuRefreshVisibleAvatarRounding()
        },
        updateForceSnow: { value in
            AyuRuntimeSettings.setChatListForceSnow(value)
            bump()
        },
        updateHideStatus: { value in
            AyuRuntimeSettings.setChatListHideStatus(value)
            bump()
        },
        updateHideStories: { value in
            AyuRuntimeSettings.setChatListHideStories(value)
            bump()
        },
        selectTitleMode: presentTitleMode,
        selectFolderMode: presentFolderMode,
        updateFolderUnread: { value in
            AyuRuntimeSettings.setFolderUnreadBadge(value)
            bump()
        }
    )

    let peerData = context.engine.data.subscribe(TelegramEngine.EngineData.Item.Peer.Peer(id: context.account.peerId))
    |> map { peer -> NetworkStatusTitle.Status? in
        guard case let .user(user) = peer else { return nil }
        AyuRuntimeSettings.updateChatListIdentity(username: user.username ?? "", firstName: user.firstName ?? "")
        if let emojiStatus = user.emojiStatus {
            return .emoji(emojiStatus)
        } else if user.isPremium {
            return .premium
        } else {
            return nil
        }
    }

    let folderData = chatListFilterItems(context: context)
    |> map { totalUnread, items -> [AyuFolderPreview] in
        var result: [AyuFolderPreview] = [AyuFolderPreview(title: "Все чаты", icon: "💬", unreadCount: totalUnread)]
        for (filter, unreadCount, _) in items {
            if case let .filter(_, title, emoticon, _) = filter {
                result.append(AyuFolderPreview(title: title.text, icon: emoticon, unreadCount: unreadCount))
            }
        }
        return result
    }

    let signal = combineLatest(context.sharedContext.presentationData, revision.get(), peerData, folderData)
    |> deliverOnMainQueue
    |> map { presentationData, _, peerStatus, folders -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let entries: [AyuAppearanceEntry] = [
            .avatarsHeader,
            .listRounding(AyuRuntimeSettings.avatarCornerPercent),
            .unified(AyuRuntimeSettings.unifiedAvatarCorners),
            .avatarInfo,
            .chatRounding(AyuRuntimeSettings.chatAvatarCornerPercent),
            .profileRounding(AyuRuntimeSettings.profileAvatarCornerPercent),
            .chatListHeader,
            .chatListPreview(AyuRuntimeSettings.chatListHeaderTitle, AyuRuntimeSettings.chatListHideStatus ? nil : peerStatus, AyuRuntimeSettings.chatListForceSnow),
            .forceSnow(AyuRuntimeSettings.chatListForceSnow),
            .hideStatus(AyuRuntimeSettings.chatListHideStatus),
            .hideStories(AyuRuntimeSettings.chatListHideStories),
            .titleText(AyuRuntimeSettings.chatListTitleModeTitle),
            .foldersHeader,
            .foldersPreview(folders, AyuRuntimeSettings.folderTitleMode, AyuRuntimeSettings.folderUnreadBadge),
            .folderTitles(AyuRuntimeSettings.folderTitleModeTitle),
            .folderUnread(AyuRuntimeSettings.folderUnreadBadge),
            .foldersInfo
        ]
        let controllerState = ItemListControllerState(presentationData: ItemListPresentationData(presentationData), title: .text("Оформление"), leftNavigationButton: nil, rightNavigationButton: nil, backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back))
        return (controllerState, (ItemListNodeState(presentationData: ItemListPresentationData(presentationData), entries: entries, style: .blocks, animateChanges: true), arguments))
    }
    let controller = ItemListController(context: context, state: signal)
    controllerBox.value = controller
    return controller
}

'''
    text = text[:start] + block + text[end:]
    text = f"// {MARK}\n" + text
    path.write_text(text, encoding="utf-8")

    build = build_path.read_text(encoding="utf-8")
    dependency = '        "//submodules/TelegramUI/Components/ChatListTitleView",\n'
    if dependency not in build:
        build = one(build, '        "//submodules/TelegramUI/Components/ChatListHeaderComponent",\n', '        "//submodules/TelegramUI/Components/ChatListHeaderComponent",\n' + dependency, "title view dependency")
        build_path.write_text(build, encoding="utf-8")

    shutil.copyfile(payload, path.parent / "AyuChatListAppearancePreviewItem.swift")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_chat_list_appearance.py <Telegram-iOS root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    patch_runtime(root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift")
    patch_chat_list_controller(root / "submodules/ChatListUI/Sources/ChatListController.swift")
    patch_title_view(root / "submodules/TelegramUI/Components/ChatListTitleView/Sources/ChatListTitleView.swift")
    patch_header_component(root / "submodules/TelegramUI/Components/ChatListHeaderComponent/Sources/ChatListHeaderComponent.swift")
    patch_navigation_bar(root / "submodules/TelegramUI/Components/ChatListHeaderComponent/Sources/ChatListNavigationBar.swift")
    patch_folder_tabs(root / "submodules/TelegramUI/Components/ChatList/ChatListFilterTabContainerNode/Sources/ChatListFilterTabContainerNode.swift")
    here = Path(__file__).resolve().parent
    patch_settings(
        root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift",
        root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/BUILD",
        (here / "payload/AyuChatListAppearancePreviewItem.swift") if (here / "payload/AyuChatListAppearancePreviewItem.swift").is_file() else (here / "AyuChatListAppearancePreviewItem.swift"),
    )

    required = (
        (root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift", "chatListAppearanceDidChange"),
        (root / "submodules/ChatListUI/Sources/ChatListController.swift", "updateChatListIdentity"),
        (root / "submodules/TelegramUI/Components/ChatListTitleView/Sources/ChatListTitleView.swift", "ayuRootTitleSource"),
        (root / "submodules/TelegramUI/Components/ChatListHeaderComponent/Sources/ChatListHeaderComponent.swift", "ayuIsRootTitle"),
        (root / "submodules/TelegramUI/Components/ChatListHeaderComponent/Sources/ChatListNavigationBar.swift", "CAEmitterLayer"),
        (root / "submodules/TelegramUI/Components/ChatList/ChatListFilterTabContainerNode/Sources/ChatListFilterTabContainerNode.swift", "ayuFolderDisplayTitle"),
        (root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift", "ПАПКИ С ЧАТАМИ"),
    )
    for path, token in required:
        if token not in path.read_text(encoding="utf-8"):
            raise RuntimeError(f"appearance v4 incomplete: {token}")

    print("[ayu-chat-list-v4] live header title/status, fixed GPU snow, synced folder titles and stock unread pills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
