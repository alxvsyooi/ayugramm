#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
from pathlib import Path


MARK = "AYU_AVATAR_ROUNDING_v1"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def patch_runtime(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return
    anchor = "    public static func setDeletedMarkerStyle(_ value: Int32) {\n"
    block = f'''    // {MARK}: defaults preserve exact Telegram behavior: regular avatars are
    // circles (100), while forum avatars retain Telegram's rounded rectangle until
    // unified rounding is explicitly enabled. Hot paths only read Atomics.
    private static let avatarCornerPercentKey = keyPrefix + "appearance.avatarCornerPercent"
    private static let unifiedAvatarCornersKey = keyPrefix + "appearance.unifiedAvatarCorners"
    private static let avatarCornerPercentState = Atomic<Int32>(value: {{
        let defaults = UserDefaults.standard
        guard defaults.object(forKey: avatarCornerPercentKey) != nil else {{ return 100 }}
        return Int32(max(0, min(100, defaults.integer(forKey: avatarCornerPercentKey))))
    }}())
    private static let unifiedAvatarCornersState = Atomic<Bool>(value: UserDefaults.standard.bool(forKey: unifiedAvatarCornersKey))

    public static var avatarCornerPercent: Int32 {{
        return avatarCornerPercentState.with {{ $0 }}
    }}

    public static var unifiedAvatarCorners: Bool {{
        return unifiedAvatarCornersState.with {{ $0 }}
    }}

    public static var avatarCornerConfiguration: Int32 {{
        let percent = avatarCornerPercent
        return unifiedAvatarCorners ? percent | 0x100 : percent
    }}

    public static func setAvatarCornerPercent(_ value: Int32) {{
        let normalized = max(0, min(100, value))
        let previous = avatarCornerPercentState.swap(normalized)
        if previous != normalized {{
            UserDefaults.standard.set(Int(normalized), forKey: avatarCornerPercentKey)
        }}
    }}

    public static func setUnifiedAvatarCorners(_ value: Bool) {{
        let previous = unifiedAvatarCornersState.swap(value)
        if previous != value {{
            UserDefaults.standard.set(value, forKey: unifiedAvatarCornersKey)
        }}
    }}

'''
    text = one(text, anchor, block + anchor, "runtime avatar settings")
    path.write_text(text, encoding="utf-8")


def patch_avatar_node(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return
    enum_anchor = '''public enum AvatarNodeClipStyle {
    case none
    case round
    case roundedRect
    case bubble
}
'''
    helper = enum_anchor + f'''
// {MARK}: one Atomic-backed calculation per avatar configuration/render, never per frame.
public func ayuAvatarCornerRadius(clipStyle: AvatarNodeClipStyle, size: CGSize) -> CGFloat {{
    let edge = min(size.width, size.height)
    switch clipStyle {{
    case .round:
        return floor(edge * 0.5 * CGFloat(AyuRuntimeSettings.avatarCornerPercent) / 100.0)
    case .roundedRect:
        if AyuRuntimeSettings.unifiedAvatarCorners {{
            return floor(edge * 0.5 * CGFloat(AyuRuntimeSettings.avatarCornerPercent) / 100.0)
        }} else {{
            return floor(edge * 0.25)
        }}
    case .none, .bubble:
        return 0.0
    }}
}}
'''
    text = one(text, enum_anchor, helper, "avatar radius helper")

    text = one(text,
        "            let clipStyle: AvatarNodeClipStyle\n            \n            init(\n",
        "            let clipStyle: AvatarNodeClipStyle\n            let ayuCornerConfiguration: Int32\n            \n            init(\n",
        "V2 configuration field")
    text = one(text,
        "                displayDimensions: CGSize,\n                clipStyle: AvatarNodeClipStyle\n            ) {",
        "                displayDimensions: CGSize,\n                clipStyle: AvatarNodeClipStyle,\n                ayuCornerConfiguration: Int32\n            ) {",
        "V2 configuration init")
    text = one(text,
        "                self.displayDimensions = displayDimensions\n                self.clipStyle = clipStyle\n",
        "                self.displayDimensions = displayDimensions\n                self.clipStyle = clipStyle\n                self.ayuCornerConfiguration = ayuCornerConfiguration\n",
        "V2 configuration assign")
    text = one(text,
        "                displayDimensions: displayDimensions,\n                clipStyle: clipStyle\n            )",
        "                displayDimensions: displayDimensions,\n                clipStyle: clipStyle,\n                ayuCornerConfiguration: AyuRuntimeSettings.avatarCornerConfiguration\n            )",
        "V2 configuration call")
    text = one(text,
        '''            case .round:
                self.imageNode.clipsToBounds = true
                self.imageNode.cornerRadius = displayDimensions.height * 0.5
            case .roundedRect:
                self.imageNode.clipsToBounds = true
                self.imageNode.cornerRadius = displayDimensions.height * 0.25
''',
        '''            case .round, .roundedRect:
                self.imageNode.clipsToBounds = true
                self.imageNode.cornerRadius = ayuAvatarCornerRadius(clipStyle: clipStyle, size: displayDimensions)
''',
        "V2 live corner radius")

    old_draw = '''                if case .round = parameters.clipStyle {
                    context.beginPath()
                    context.addEllipse(in: CGRect(x: 0.0, y: 0.0, width: bounds.size.width, height:
                        bounds.size.height))
                    context.clip()
                } else if case .roundedRect = parameters.clipStyle {
                    context.beginPath()
                    context.addPath(UIBezierPath(roundedRect: CGRect(x: 0.0, y: 0.0, width: bounds.size.width, height: bounds.size.height), cornerRadius: floor(bounds.size.width * 0.25)).cgPath)
                    context.clip()
                } else if case .bubble = parameters.clipStyle {
'''
    new_draw = '''                if case .round = parameters.clipStyle {
                    context.beginPath()
                    context.addPath(UIBezierPath(roundedRect: bounds, cornerRadius: ayuAvatarCornerRadius(clipStyle: parameters.clipStyle, size: bounds.size)).cgPath)
                    context.clip()
                } else if case .roundedRect = parameters.clipStyle {
                    context.beginPath()
                    context.addPath(UIBezierPath(roundedRect: bounds, cornerRadius: ayuAvatarCornerRadius(clipStyle: parameters.clipStyle, size: bounds.size)).cgPath)
                    context.clip()
                } else if case .bubble = parameters.clipStyle {
'''
    text = one(text, old_draw, new_draw, "placeholder corner radius")
    path.write_text(text, encoding="utf-8")


def patch_peer_avatar(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return

    first_pair = '''                            case .round:
                                if displayDimensions.width != 60.0 {
                                    context.addEllipse(in: CGRect(origin: CGPoint(), size: displayDimensions).insetBy(dx: inset, dy: inset))
                                    context.clip()
                                }
                            case .roundedRect:
                                context.addPath(UIBezierPath(roundedRect: CGRect(x: 0.0, y: 0.0, width: displayDimensions.width, height: displayDimensions.height).insetBy(dx: inset, dy: inset), cornerRadius: floor(displayDimensions.width * 0.25)).cgPath)
                                context.clip()
'''
    first_new = f'''                            case .round, .roundedRect:
                                // {MARK}
                                let rect = CGRect(origin: CGPoint(), size: displayDimensions).insetBy(dx: inset, dy: inset)
                                context.addPath(UIBezierPath(roundedRect: rect, cornerRadius: ayuAvatarCornerRadius(clipStyle: clipStyle, size: rect.size)).cgPath)
                                context.clip()
'''
    text = one(text, first_pair, first_new, "loaded avatar clip")

    post_mask = '''                            case .round:
                                if displayDimensions.width == 60.0 {
                                    context.setBlendMode(.destinationOut)
                                    context.draw(roundCorners.cgImage!, in: CGRect(origin: CGPoint(), size: displayDimensions).insetBy(dx: inset, dy: inset))
                                }
                            case .roundedRect:
                                break
'''
    text = one(text, post_mask, '''                            case .round, .roundedRect:
                                break
''', "remove fixed round mask")

    fill_pair = '''                                case .round:
                                    context.fillEllipse(in: CGRect(origin: CGPoint(), size: displayDimensions).insetBy(dx: inset, dy: inset))
                                case .roundedRect:
                                    context.beginPath()
                                    context.addPath(UIBezierPath(roundedRect: CGRect(x: 0.0, y: 0.0, width: displayDimensions.width, height: displayDimensions.height).insetBy(dx: inset, dy: inset), cornerRadius: floor(displayDimensions.width * 0.25)).cgPath)
                                    context.fillPath()
'''
    fill_new = '''                                case .round, .roundedRect:
                                    let rect = CGRect(origin: CGPoint(), size: displayDimensions).insetBy(dx: inset, dy: inset)
                                    context.beginPath()
                                    context.addPath(UIBezierPath(roundedRect: rect, cornerRadius: ayuAvatarCornerRadius(clipStyle: clipStyle, size: rect.size)).cgPath)
                                    context.fillPath()
'''
    text = one(text, fill_pair, fill_new, "decoded empty avatar fill")

    unrounded_pair = '''                            case .round:
                                context.fillEllipse(in: CGRect(origin: CGPoint(), size: displayDimensions).insetBy(dx: inset, dy: inset))
                            case .roundedRect:
                                context.beginPath()
                                context.addPath(UIBezierPath(roundedRect: CGRect(x: 0.0, y: 0.0, width: displayDimensions.width, height: displayDimensions.height).insetBy(dx: inset, dy: inset), cornerRadius: floor(displayDimensions.width * 0.25)).cgPath)
                                context.fillPath()
'''
    unrounded_new = '''                            case .round, .roundedRect:
                                let rect = CGRect(origin: CGPoint(), size: displayDimensions).insetBy(dx: inset, dy: inset)
                                context.beginPath()
                                context.addPath(UIBezierPath(roundedRect: rect, cornerRadius: ayuAvatarCornerRadius(clipStyle: clipStyle, size: rect.size)).cgPath)
                                context.fillPath()
'''
    text = one(text, unrounded_pair, unrounded_new, "unrounded empty fill")
    outer_pair = '''                        case .round:
                            context.fillEllipse(in: CGRect(origin: CGPoint(), size: displayDimensions).insetBy(dx: inset, dy: inset))
                        case .roundedRect:
                            context.beginPath()
                            context.addPath(UIBezierPath(roundedRect: CGRect(x: 0.0, y: 0.0, width: displayDimensions.width, height: displayDimensions.height).insetBy(dx: inset, dy: inset), cornerRadius: floor(displayDimensions.width * 0.25)).cgPath)
                            context.fillPath()
'''
    outer_new = '''                        case .round, .roundedRect:
                            let rect = CGRect(origin: CGPoint(), size: displayDimensions).insetBy(dx: inset, dy: inset)
                            context.beginPath()
                            context.addPath(UIBezierPath(roundedRect: rect, cornerRadius: ayuAvatarCornerRadius(clipStyle: clipStyle, size: rect.size)).cgPath)
                            context.fillPath()
'''
    text = one(text, outer_pair, outer_new, "outer empty avatar fill")
    round_mask_start = text.find("private let roundCorners = { () -> UIImage in\n")
    round_mask_end = text.find("\npublic enum PeerAvatarImageType", round_mask_start)
    if round_mask_start < 0 or round_mask_end < 0:
        raise RuntimeError("obsolete fixed round mask declaration missing")
    text = text[:round_mask_start] + text[round_mask_end + 1:]
    path.write_text(text, encoding="utf-8")


def patch_profile_corners(root: Path) -> None:
    replacements = (
        ("PeerInfoAvatarTransformContainerNode.swift", '''            var isForum = false
            let avatarCornerRadius: CGFloat
            if case let .channel(channel) = peer, channel.isForumOrMonoForum {
                avatarCornerRadius = floor(avatarSize * 0.25)
                isForum = true
            } else {
                avatarCornerRadius = avatarSize / 2.0
            }
''', '''            var isForum = false
            if case let .channel(channel) = peer, channel.isForumOrMonoForum {
                isForum = true
            }
            let avatarCornerRadius = ayuAvatarCornerRadius(clipStyle: isForum ? .roundedRect : .round, size: CGSize(width: avatarSize, height: avatarSize))
'''),
        ("PeerInfoEditingAvatarNode.swift", '''        var isForum = false
        let avatarCornerRadius: CGFloat
        if case let .channel(channel) = peer, channel.isForumOrMonoForum {
            isForum = true
            avatarCornerRadius = floor(avatarSize * 0.25)
        } else {
            avatarCornerRadius = avatarSize / 2.0
        }
''', '''        var isForum = false
        if case let .channel(channel) = peer, channel.isForumOrMonoForum {
            isForum = true
        }
        let avatarCornerRadius = ayuAvatarCornerRadius(clipStyle: isForum ? .roundedRect : .round, size: CGSize(width: avatarSize, height: avatarSize))
'''),
        ("PeerInfoHeaderNode.swift", "        let avatarCornerRadius: CGFloat = isForum ? floor(avatarSize * 0.25) : avatarSize / 2.0\n", "        let avatarCornerRadius = ayuAvatarCornerRadius(clipStyle: isForum ? .roundedRect : .round, size: CGSize(width: avatarSize, height: avatarSize))\n"),
    )
    source_dir = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources"
    for name, old, new in replacements:
        path = source_dir / name
        text = path.read_text(encoding="utf-8")
        if new in text:
            continue
        text = one(text, old, new, f"profile corner: {name}")
        path.write_text(text, encoding="utf-8")

    overlay = source_dir / "PeerInfoEditingAvatarOverlayNode.swift"
    text = overlay.read_text(encoding="utf-8")
    old = '''                case .round:
                    self.updatingAvatarOverlay.image = generateFilledCircleImage(diameter: avatarSize, color: UIColor(white: 0.0, alpha: 0.4), backgroundColor: nil)
                case .roundedRect:
                    self.updatingAvatarOverlay.image = generateFilledRoundedRectImage(size: CGSize(width: avatarSize, height: avatarSize), cornerRadius: avatarSize * 0.25, color: UIColor(white: 0.0, alpha: 0.4), backgroundColor: nil)
'''
    new = '''                case .round, .roundedRect:
                    self.updatingAvatarOverlay.image = generateFilledRoundedRectImage(size: CGSize(width: avatarSize, height: avatarSize), cornerRadius: ayuAvatarCornerRadius(clipStyle: clipStyle, size: CGSize(width: avatarSize, height: avatarSize)), color: UIColor(white: 0.0, alpha: 0.4), backgroundColor: nil)
'''
    if new not in text:
        text = one(text, old, new, "editing overlay corner")
        overlay.write_text(text, encoding="utf-8")


def patch_settings(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return
    text = one(text,
        '''private final class AyuExteraArguments {
    let openChats: () -> Void
    init(openChats: @escaping () -> Void) {
        self.openChats = openChats
    }
}
''',
        '''private final class AyuExteraArguments {
    let openAppearance: () -> Void
    let openChats: () -> Void
    init(openAppearance: @escaping () -> Void, openChats: @escaping () -> Void) {
        self.openAppearance = openAppearance
        self.openChats = openChats
    }
}
''', "extera arguments")
    text = one(text, "    case header\n    case chats\n", "    case header\n    case appearance\n    case chats\n", "appearance entry")
    text = one(text,
        '''        case .header: return 0
        case .chats: return 1
''',
        '''        case .header: return 0
        case .appearance: return 1
        case .chats: return 2
''', "appearance ordering")
    text = one(text,
        '''        case .header:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "КАТЕГОРИИ", sectionId: self.section)
        case .chats:
''',
        '''        case .header:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "КАТЕГОРИИ", sectionId: self.section)
        case .appearance:
            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: "Оформление", label: "", sectionId: self.section, style: .blocks, action: arguments.openAppearance)
        case .chats:
''', "appearance row")
    text = one(text,
        '''    let arguments = AyuExteraArguments(openChats: {
        controllerBox.value?.push(ayuExteraChatsSettingsController(context: context))
    })
''',
        '''    let arguments = AyuExteraArguments(openAppearance: {
        controllerBox.value?.push(ayuExteraAppearanceSettingsController(context: context))
    }, openChats: {
        controllerBox.value?.push(ayuExteraChatsSettingsController(context: context))
    })
''', "appearance navigation")
    text = one(text, "        let entries: [AyuExteraEntry] = [.header, .chats]\n", "        let entries: [AyuExteraEntry] = [.header, .appearance, .chats]\n", "appearance before camera")

    controller_anchor = "private final class AyuExteraArguments {\n"
    appearance = f'''// {MARK}: exteraGram appearance settings, placed above Chats/Camera.
private final class AyuAppearanceArguments {{
    let updateCornerPercent: (Int32) -> Void
    let updateUnified: (Bool) -> Void
    init(updateCornerPercent: @escaping (Int32) -> Void, updateUnified: @escaping (Bool) -> Void) {{
        self.updateCornerPercent = updateCornerPercent
        self.updateUnified = updateUnified
    }}
}}

private enum AyuAppearanceSection: Int32 {{ case avatars }}

private enum AyuAppearanceEntry: ItemListNodeEntry {{
    case header
    case rounding(Int32)
    case unified(Bool)
    case info

    var section: ItemListSectionId {{ AyuAppearanceSection.avatars.rawValue }}
    var stableId: Int32 {{
        switch self {{
        case .header: return 0
        case .rounding: return 1
        case .unified: return 2
        case .info: return 3
        }}
    }}
    static func <(lhs: AyuAppearanceEntry, rhs: AyuAppearanceEntry) -> Bool {{ lhs.stableId < rhs.stableId }}

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {{
        let arguments = arguments as! AyuAppearanceArguments
        switch self {{
        case .header:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "АВАТАРЫ", sectionId: self.section)
        case let .rounding(value):
            return AyuAvatarRoundingItem(theme: presentationData.theme, value: value, sectionId: self.section, updated: arguments.updateCornerPercent)
        case let .unified(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Единое закругление", value: value, sectionId: self.section, style: .blocks, updated: arguments.updateUnified)
        case .info:
            return ItemListTextItem(presentationData: presentationData, text: .plain("Форумы будут иметь ту же форму, что и чаты."), sectionId: self.section)
        }}
    }}
}}

private func ayuExteraAppearanceSettingsController(context: AccountContext) -> ViewController {{
    let revision = ValuePromise<Int32>(0, ignoreRepeated: false)
    var revisionValue: Int32 = 0
    let bump: () -> Void = {{ revisionValue &+= 1; revision.set(revisionValue) }}
    let arguments = AyuAppearanceArguments(updateCornerPercent: {{ value in
        AyuRuntimeSettings.setAvatarCornerPercent(value)
    }}, updateUnified: {{ value in
        AyuRuntimeSettings.setUnifiedAvatarCorners(value)
        bump()
    }})
    let signal = combineLatest(context.sharedContext.presentationData, revision.get())
    |> deliverOnMainQueue
    |> map {{ presentationData, _ -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let entries: [AyuAppearanceEntry] = [.header, .rounding(AyuRuntimeSettings.avatarCornerPercent), .unified(AyuRuntimeSettings.unifiedAvatarCorners), .info]
        let controllerState = ItemListControllerState(presentationData: ItemListPresentationData(presentationData), title: .text("Оформление"), leftNavigationButton: nil, rightNavigationButton: nil, backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back))
        return (controllerState, (ItemListNodeState(presentationData: ItemListPresentationData(presentationData), entries: entries, style: .blocks, animateChanges: true), arguments))
    }}
    return ItemListController(context: context, state: signal)
}}

'''
    text = one(text, controller_anchor, appearance + controller_anchor, "appearance controller")
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_avatar_rounding.py <Telegram-iOS root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    patch_runtime(root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift")
    patch_avatar_node(root / "submodules/AvatarNode/Sources/AvatarNode.swift")
    patch_peer_avatar(root / "submodules/AvatarNode/Sources/PeerAvatar.swift")
    patch_profile_corners(root)
    patch_settings(root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift")
    shutil.copyfile(Path(__file__).resolve().parent / "payload/AyuAvatarRoundingItem.swift", root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuAvatarRoundingItem.swift")
    runtime = (root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift").read_text(encoding="utf-8")
    settings = (root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift").read_text(encoding="utf-8")
    avatar = (root / "submodules/AvatarNode/Sources/AvatarNode.swift").read_text(encoding="utf-8")
    peer_avatar = (root / "submodules/AvatarNode/Sources/PeerAvatar.swift").read_text(encoding="utf-8")
    checks = (
        (runtime, "guard defaults.object(forKey: avatarCornerPercentKey) != nil else { return 100 }"),
        (runtime, "unifiedAvatarCornersState = Atomic<Bool>"),
        (settings, 'let entries: [AyuExteraEntry] = [.header, .appearance, .chats]'),
        (settings, 'title: "Единое закругление"'),
        (avatar, "public func ayuAvatarCornerRadius"),
    )
    for source, value in checks:
        if value not in source:
            raise RuntimeError(f"avatar rounding patch incomplete: {value}")
    if "private let roundCorners" in peer_avatar:
        raise RuntimeError("obsolete fixed-circle image mask remains")
    print("[ayu-avatar-rounding] Appearance above Chats; default circle 100, unified forums off; no polling")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
