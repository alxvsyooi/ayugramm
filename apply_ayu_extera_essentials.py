#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

MARK = "AYU_ESSENTIALS_v1"


def replace_count(text: str, old: str, new: str, label: str, count: int) -> str:
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchors, found {found}")
    return text.replace(old, new)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    return replace_count(text, old, new, label, 1)


def patch_runtime(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print(f"[ayu-essentials] already patched: {path}")
        return

    # 1) Snapshot fields.
    struct_anchor = """    public var deletedMarkerStyle: Int32
    public var deletedMarkerColor: Int32
}
"""
    struct_new = """    public var deletedMarkerStyle: Int32
    public var deletedMarkerColor: Int32
    public var disableNumberRounding: Bool
    public var timeWithSeconds: Bool
    public var zalgoFilter: Bool
    public var relativeOnlineTime: Bool
    public var hidePhoneNumber: Bool
    public var peerIdStyle: Int32
}
"""
    text = replace_once(text, struct_anchor, struct_new, "snapshot fields")

    load_anchor = """            deletedMarkerStyle: style,
            deletedMarkerColor: color
        )
    }
"""
    load_new = """            deletedMarkerStyle: style,
            deletedMarkerColor: color,
            disableNumberRounding: loadEssentialsBool("numberRounding", defaults: defaults),
            timeWithSeconds: loadEssentialsBool("timeWithSeconds", defaults: defaults),
            zalgoFilter: loadEssentialsBool("zalgoFilter", defaults: defaults),
            relativeOnlineTime: loadEssentialsBool("relativeOnlineTime", defaults: defaults),
            hidePhoneNumber: loadEssentialsBool("hidePhoneNumber", defaults: defaults),
            peerIdStyle: loadEssentialsPeerIdStyle(defaults: defaults)
        )
    }
"""
    text = replace_once(text, load_anchor, load_new, "snapshot loading")

    api_anchor = """    public static var suppressReadMessages: Bool {
"""
    api_block = """    // AYU_ESSENTIALS_v1: exteraGram-style essentials. One Atomic read per use;
    // UserDefaults is touched only when a value changes or at startup.

    private static func essentialsKey(_ name: String) -> String {
        return keyPrefix + "essentials." + name
    }

    private static func loadEssentialsBool(_ name: String, defaults: UserDefaults) -> Bool {
        if defaults.object(forKey: essentialsKey(name)) != nil {
            return defaults.bool(forKey: essentialsKey(name))
        }
        return false
    }

    private static func loadEssentialsPeerIdStyle(defaults: UserDefaults) -> Int32 {
        if defaults.object(forKey: essentialsKey("peerIdStyle")) != nil {
            let value = defaults.integer(forKey: essentialsKey("peerIdStyle"))
            return (value >= 0 && value <= 2) ? Int32(value) : 0
        }
        return 0
    }

    public static func setEssentialsBool(_ name: String, keyPath: WritableKeyPath<AyuRuntimeSnapshot, Bool>, value: Bool) {
        UserDefaults.standard.set(value, forKey: essentialsKey(name))
        _ = state.modify { current in
            var current = current
            current[keyPath: keyPath] = value
            return current
        }
    }

    public static func setEssentialsPeerIdStyle(_ value: Int32) {
        let normalized = (value >= 0 && value <= 2) ? value : 0
        UserDefaults.standard.set(Int(normalized), forKey: essentialsKey("peerIdStyle"))
        _ = state.modify { current in
            var current = current
            current.peerIdStyle = normalized
            return current
        }
    }

    private static let ayuZalgoRanges: [(UInt32, UInt32)] = [
        (0x0300, 0x036F), (0x0483, 0x0489), (0x0591, 0x05BD), (0x05BF, 0x05BF),
        (0x05C1, 0x05C2), (0x05C4, 0x05C5), (0x05C7, 0x05C7), (0x0610, 0x061A),
        (0x064B, 0x065F), (0x0670, 0x0670), (0x06D6, 0x06DC), (0x06DF, 0x06E4),
        (0x06E7, 0x06E8), (0x06EA, 0x06ED), (0x0711, 0x0711), (0x0730, 0x074A),
        (0x07A6, 0x07B0), (0x07EB, 0x07F3), (0x0816, 0x0819), (0x081B, 0x0823),
        (0x0825, 0x0827), (0x0829, 0x082D), (0x0859, 0x085B), (0x08E3, 0x0902),
        (0x093A, 0x093A), (0x093C, 0x093C), (0x0941, 0x0948), (0x094D, 0x094D),
        (0x0951, 0x0957), (0x0962, 0x0963), (0x1AB0, 0x1AFF), (0x1DC0, 0x1DFF),
        (0x20D0, 0x20F0), (0xFE00, 0xFE0F), (0xFE20, 0xFE2F)
    ]

    private static func ayuIsZalgoScalar(_ value: UInt32) -> Bool {
        for range in ayuZalgoRanges where value >= range.0 && value <= range.1 {
            return true
        }
        return false
    }

    public static func ayuStripZalgo(_ source: String) -> String {
        return ayuStripZalgoWithEntities(source, entities: nil).text
    }

    /// Removes Zalgo combining marks while keeping text-entity ranges valid by
    /// remapping every boundary to the nearest surviving position.
    public static func ayuStripZalgoWithEntities(_ source: String, entities: [MessageTextEntity]?) -> (text: String, entities: [MessageTextEntity]?) {
        guard !source.isEmpty else {
            return (source, entities)
        }
        var output = String()
        output.reserveCapacity(source.utf16.count)
        // For every original UTF-16 offset: the new offset, or nil when removed.
        var map: [Int32] = []
        map.reserveCapacity(source.utf16.count + 1)
        var removedRun: Int32 = -1
        for scalar in source.unicodeScalars {
            let utf16Length = Int32(String(scalar).utf16.count)
            if ayuIsZalgoScalar(scalar.value) {
                for _ in 0..<utf16Length {
                    map.append(removedRun)
                    removedRun -= 1
                }
            } else {
                let base = Int32(output.utf16.count)
                for i in 0..<utf16Length {
                    map.append(base + i)
                }
                output.unicodeScalars.append(scalar)
            }
        }
        map.append(Int32(output.utf16.count))

        func ayuMappedIndex(_ index: Int) -> Int32 {
            if index < map.count, map[index] >= 0 {
                return map[index]
            }
            var j = min(index, map.count - 1) - 1
            while j >= 0 {
                if map[j] >= 0 {
                    return map[j]
                }
                j -= 1
            }
            return 0
        }

        guard var inputEntities = entities, !inputEntities.isEmpty else {
            return (output, entities == nil ? nil : [])
        }
        var mapped: [MessageTextEntity] = []
        mapped.reserveCapacity(inputEntities.count)
        for entity in inputEntities {
            let newLower = Int(ayuMappedIndex(entity.range.lowerBound))
            let newUpper = Int(ayuMappedIndex(entity.range.upperBound))
            if newUpper > newLower {
                mapped.append(MessageTextEntity(range: newLower..<newUpper, type: entity.type))
            }
        }
        inputEntities = mapped
        return (output, inputEntities)
    }

    public static var suppressReadMessages: Bool {
"""
    text = replace_once(text, api_anchor, api_block, "essentials runtime api")

    path.write_text(text, encoding="utf-8")
    print(f"[ayu-essentials] runtime settings extended: {path}")


def patch_numeric_format(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print(f"[ayu-essentials] already patched: {path}")
        return

    anchor = """public func compactNumericCountString(_ count: Int, decimalSeparator: String = ".", showDecimalPart: Bool = true) -> String {
    if count >= 1000 * 1000 {
"""
    new = """public func compactNumericCountString(_ count: Int, decimalSeparator: String = ".", showDecimalPart: Bool = true) -> String {
    // AYU_ESSENTIALS_v1: exact numbers instead of the abbreviated form.
    if AyuRuntimeSettings.snapshot.disableNumberRounding {
        return "\\(count)"
    }
    if count >= 1000 * 1000 {
"""
    text = replace_once(text, anchor, new, "number rounding")
    path.write_text(text, encoding="utf-8")
    print(f"[ayu-essentials] exact numbers installed: {path}")


def patch_presence_strings(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print(f"[ayu-essentials] already patched: {path}")
        return

    # Seconds precision for today/yesterday presence strings.
    present_old = """                    return (stringForUserPresence(strings: strings, day: day, dateTimeFormat: dateTimeFormat, hours: timeinfo.tm_hour, minutes: timeinfo.tm_min), false)
"""
    present_new = """                    // AYU_ESSENTIALS_v1: optional seconds precision.
                    return (ayuPresenceDayTimeString(strings: strings, day: day, dateTimeFormat: dateTimeFormat, timestamp: statusTimestamp), false)
"""
    text = replace_once(text, present_old, present_new, "presence seconds")

    recently_old = """    case .recently:
        let activeUntil = presence.lastActivity + 30
        if activeUntil >= timestamp {
            return (strings.Presence_online, true)
        } else {
            return (strings.LastSeen_Lately, false)
        }
"""
    recently_new = """    case .recently:
        let activeUntil = presence.lastActivity + 30
        if activeUntil >= timestamp {
            return (strings.Presence_online, true)
        } else if AyuRuntimeSettings.snapshot.relativeOnlineTime, presence.lastActivity > 0 {
            // AYU_ESSENTIALS_v1: keep the last precise online moment visible
            // instead of the vague "last seen recently".
            var t: time_t = time_t(presence.lastActivity)
            var timeinfo = tm()
            localtime_r(&t, &timeinfo)
            var nowT: time_t = time_t(timestamp)
            var nowInfo = tm()
            localtime_r(&nowT, &nowInfo)
            let seconds: Int32? = AyuRuntimeSettings.snapshot.timeWithSeconds ? Int32(timeinfo.tm_sec) : nil
            let timeString = stringForShortTimestamp(hours: Int32(timeinfo.tm_hour), minutes: Int32(timeinfo.tm_min), seconds: seconds, dateTimeFormat: dateTimeFormat)
            if timeinfo.tm_year == nowInfo.tm_year && timeinfo.tm_yday == nowInfo.tm_yday {
                return (strings.LastSeen_TodayAt(timeString).string, false)
            } else if timeinfo.tm_yday == nowInfo.tm_yday - 1 {
                return (strings.LastSeen_YesterdayAt(timeString).string, false)
            } else {
                return (strings.LastSeen_AtDate(stringForTimestamp(day: timeinfo.tm_mday, month: timeinfo.tm_mon + 1, year: timeinfo.tm_year, dateTimeFormat: dateTimeFormat)).string, false)
            }
        } else {
            return (strings.LastSeen_Lately, false)
        }
"""
    text = replace_once(text, recently_old, recently_new, "relative online")

    helper_anchor = "public func stringAndActivityForUserPresence(strings: PresentationStrings, dateTimeFormat: PresentationDateTimeFormat, presence: EnginePeer.Presence, relativeTo timestamp: Int32, expanded: Bool = false) -> (String, Bool) {\n"
    helper = """// AYU_ESSENTIALS_v1
private func ayuPresenceDayTimeString(strings: PresentationStrings, day: RelativeTimestampFormatDay, dateTimeFormat: PresentationDateTimeFormat, timestamp: Int32) -> String {
    var t: time_t = time_t(timestamp)
    var timeinfo = tm()
    localtime_r(&t, &timeinfo)
    let seconds: Int32? = AyuRuntimeSettings.snapshot.timeWithSeconds ? Int32(timeinfo.tm_sec) : nil
    let timeString = stringForShortTimestamp(hours: Int32(timeinfo.tm_hour), minutes: Int32(timeinfo.tm_min), seconds: seconds, dateTimeFormat: dateTimeFormat)
    switch day {
    case .today:
        return strings.LastSeen_TodayAt(timeString).string
    case .yesterday:
        return strings.LastSeen_YesterdayAt(timeString).string
    case .tomorrow:
        return strings.LastSeen_TodayAt(timeString).string
    }
}

"""
    text = replace_once(text, helper_anchor, helper + helper_anchor, "presence helper")

    path.write_text(text, encoding="utf-8")
    print(f"[ayu-essentials] presence formatting extended: {path}")


def patch_message_timestamp(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text or "withSeconds: AyuRuntimeSettings.snapshot.timeWithSeconds" in text:
        print(f"[ayu-essentials] already patched: {path}")
        return

    old_regular = "stringForMessageTimestamp(timestamp: timestamp, dateTimeFormat: dateTimeFormat)"
    new_regular = "stringForMessageTimestamp(timestamp: timestamp, dateTimeFormat: dateTimeFormat, withSeconds: AyuRuntimeSettings.snapshot.timeWithSeconds)"
    text = replace_count(text, old_regular, new_regular, "message timestamps", 4)

    old_forward = "stringForMessageTimestamp(timestamp: forwardInfo.date, dateTimeFormat: dateTimeFormat)"
    new_forward = "stringForMessageTimestamp(timestamp: forwardInfo.date, dateTimeFormat: dateTimeFormat, withSeconds: AyuRuntimeSettings.snapshot.timeWithSeconds)"
    text = replace_count(text, old_forward, new_forward, "forwarded timestamps", 1)

    path.write_text(text, encoding="utf-8")
    print(f"[ayu-essentials] message timestamps with seconds: {path}")


def patch_peer_title(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print(f"[ayu-essentials] already patched: {path}")
        return

    anchor = """    func displayTitle(strings: PresentationStrings, displayOrder: PresentationPersonNameOrder) -> String {
"""
    wrapper = """    // AYU_ESSENTIALS_v1: strip Zalgo combining marks from displayed names.
    func displayTitle(strings: PresentationStrings, displayOrder: PresentationPersonNameOrder) -> String {
        let rawTitle = displayTitleUnfiltered(strings: strings, displayOrder: displayOrder)
        if AyuRuntimeSettings.snapshot.zalgoFilter {
            return AyuRuntimeSettings.ayuStripZalgo(rawTitle)
        }
        return rawTitle
    }

    func displayTitleUnfiltered(strings: PresentationStrings, displayOrder: PresentationPersonNameOrder) -> String {
"""
    text = replace_once(text, anchor, wrapper, "peer title filter")
    path.write_text(text, encoding="utf-8")
    print(f"[ayu-essentials] peer name filter installed: {path}")


def patch_message_text(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print(f"[ayu-essentials] already patched: {path}")
        return

    anchor = """                    if let updatingMedia = item.attributes.updatingMedia {
                        messageEntities = updatingMedia.entities?.entities ?? []
                    }
                    
"""
    new = anchor + """                    // AYU_ESSENTIALS_v1: remove Zalgo marks from message texts,
                    // keeping entity ranges aligned with the filtered string.
                    if AyuRuntimeSettings.snapshot.zalgoFilter {
                        let ayuFiltered = AyuRuntimeSettings.ayuStripZalgoWithEntities(rawText, entities: messageEntities)
                        rawText = ayuFiltered.text
                        messageEntities = ayuFiltered.entities
                    }
                    
"""
    text = replace_once(text, anchor, new, "message text filter")
    path.write_text(text, encoding="utf-8")
    print(f"[ayu-essentials] message text filter installed: {path}")


def patch_header_node(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print(f"[ayu-essentials] already patched: {path}")
        return

    anchor = """                var subtitle = formatPhoneNumber(context: self.context, number: user.phone ?? "")
                
                if let mainUsername = user.addressName, !mainUsername.isEmpty {
                    subtitle = "\\(subtitle) • @\\(mainUsername)"
                }
"""
    new = """                var subtitle = formatPhoneNumber(context: self.context, number: user.phone ?? "")
                
                if let mainUsername = user.addressName, !mainUsername.isEmpty {
                    if AyuRuntimeSettings.snapshot.hidePhoneNumber {
                        // AYU_ESSENTIALS_v1: username takes the phone place, no dot left over.
                        subtitle = "@\\(mainUsername)"
                    } else {
                        subtitle = "\\(subtitle) • @\\(mainUsername)"
                    }
                } else if AyuRuntimeSettings.snapshot.hidePhoneNumber {
                    subtitle = ""
                }
"""
    text = replace_once(text, anchor, new, "settings header phone")
    path.write_text(text, encoding="utf-8")
    print(f"[ayu-essentials] phone hidden in settings header: {path}")


def patch_profile_items(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print(f"[ayu-essentials] already patched: {path}")
        return

    phone_anchor = """            let formattedPhone = formatPhoneNumber(context: context, number: phone)
"""
    phone_new = """            // AYU_ESSENTIALS_v1: own profile hides the real number.
            let formattedPhone = AyuRuntimeSettings.snapshot.hidePhoneNumber ? "Неизвестен" : formatPhoneNumber(context: context, number: phone)
"""
    text = replace_once(text, phone_anchor, phone_new, "my profile phone")

    result_anchor = """                items[.community]!.append(PeerInfoScreenCommentItem(id: ItemAddToCommunityInfo, text: presentationData.strings.PeerInfo_Community_GroupInfo))
            }
        }
    }
    
    var result: [(AnyHashable, [PeerInfoScreenItem])] = []
"""
    id_block = """    // AYU_PEER_ID_INFO_v1: technical info block at the bottom of the profile.
    if AyuRuntimeSettings.snapshot.peerIdStyle != 0 {
        let ayuInternalId = data.peer.id.id._internalGetInt64Value()
        let ayuIdText: String
        if AyuRuntimeSettings.snapshot.peerIdStyle == 2 {
            switch data.peer.id.namespace {
            case Namespaces.Peer.CloudChannel:
                ayuIdText = "-100\\(ayuInternalId)"
            case Namespaces.Peer.CloudGroup:
                ayuIdText = "-\\(ayuInternalId)"
            default:
                ayuIdText = "\\(ayuInternalId)"
            }
        } else {
            ayuIdText = "\\(ayuInternalId)"
        }

        var ayuDcLine = ""
        var ayuRepresentations: [TelegramMediaImageRepresentation] = []
        if let ayuEnginePeer = data.peer.peers[data.peer.peerId] {
            switch ayuEnginePeer {
            case let .user(ayuUserPeer):
                ayuRepresentations = ayuUserPeer.photo
            case let .legacyGroup(ayuGroupPeer):
                ayuRepresentations = ayuGroupPeer.photo
            case let .channel(ayuChannelPeer):
                ayuRepresentations = ayuChannelPeer.photo
            case let .community(ayuCommunityPeer):
                ayuRepresentations = ayuCommunityPeer.photo
            case .secretChat:
                break
            }
        }
        if let ayuResource = ayuRepresentations.first?.resource as? CloudPeerPhotoSizeMediaResource {
            let dc = ayuResource.datacenterId
            let city: String
            switch dc {
            case 1, 3: city = "Miami, US"
            case 2, 4: city = "Amsterdam, NL"
            case 5: city = "Singapore, SG"
            default: city = ""
            }
            ayuDcLine = city.isEmpty ? "DC\\(dc)" : "DC\\(dc), \\(city)"
        }

        var ayuFooterText = "ID: \\(ayuIdText)"
        if !ayuDcLine.isEmpty {
            ayuFooterText += "\\n\\(ayuDcLine)"
        }
        items[currentPeerInfoSection]!.append(PeerInfoScreenCommentItem(id: 0xA0091101, text: ayuFooterText))
    }

"""
    text = replace_once(text, result_anchor, result_anchor.replace("    var result:", id_block + "    var result:"), "profile id footer")

    path.write_text(text, encoding="utf-8")
    print(f"[ayu-essentials] profile phone/id blocks installed: {path}")


ESSENTIALS_CONTROLLER = '''
// AYU_ESSENTIALS_v1
private final class AyuEssentialsArguments {
    let updateBool: (WritableKeyPath<AyuRuntimeSnapshot, Bool>, String, Bool) -> Void
    let selectPeerIdStyle: () -> Void

    init(updateBool: @escaping (WritableKeyPath<AyuRuntimeSnapshot, Bool>, String, Bool) -> Void, selectPeerIdStyle: @escaping () -> Void) {
        self.updateBool = updateBool
        self.selectPeerIdStyle = selectPeerIdStyle
    }
}

private enum AyuEssentialsSection: Int32 {
    case essentials
    case profile
}

private enum AyuEssentialsEntry: ItemListNodeEntry {
    case essentialsHeader
    case numberRounding(Bool)
    case timeWithSeconds(Bool)
    case zalgoFilter(Bool)
    case zalgoDescription
    case profileHeader
    case relativeOnline(Bool, String)
    case hidePhone(Bool)
    case peerIdStyle(String)
    case peerIdDescription

    var section: ItemListSectionId {
        switch self {
        case .essentialsHeader, .numberRounding, .timeWithSeconds, .zalgoFilter, .zalgoDescription:
            return AyuEssentialsSection.essentials.rawValue
        case .profileHeader, .relativeOnline, .hidePhone, .peerIdStyle, .peerIdDescription:
            return AyuEssentialsSection.profile.rawValue
        }
    }

    var stableId: Int32 {
        switch self {
        case .essentialsHeader: return 0
        case .numberRounding: return 1
        case .timeWithSeconds: return 2
        case .zalgoFilter: return 3
        case .zalgoDescription: return 4
        case .profileHeader: return 10
        case .relativeOnline: return 11
        case .hidePhone: return 12
        case .peerIdStyle: return 13
        case .peerIdDescription: return 14
        }
    }

    static func <(lhs: AyuEssentialsEntry, rhs: AyuEssentialsEntry) -> Bool { lhs.stableId < rhs.stableId }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let arguments = arguments as! AyuEssentialsArguments
        switch self {
        case .essentialsHeader:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "ОСНОВНЫЕ".uppercased(), sectionId: self.section)
        case let .numberRounding(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Отключить округление чисел", text: "1.23K -> 1,234", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(\\\\.disableNumberRounding, "numberRounding", $0) })
        case let .timeWithSeconds(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Форматировать время с секундами", text: "12:34 -> 12:34:56", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(\\\\.timeWithSeconds, "timeWithSeconds", $0) })
        case let .zalgoFilter(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Фильтр \\"Zaglo\\"", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(\\\\.zalgoFilter, "zalgoFilter", $0) })
        case .zalgoDescription:
            return ItemListTextItem(presentationData: presentationData, text: .plain("Убирает искажающие текст символы \\"Zaglo\\" в именах и сообщениях. Если выключено — текст отображается в стиле Zaglo, если включено — отображается просто \\"Zaglo\\"."), sectionId: self.section)
        case .profileHeader:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "ПРОФИЛЬ".uppercased(), sectionId: self.section)
        case let .relativeOnline(value, description):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Относительное время онлайна", text: description, value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(\\\\.relativeOnlineTime, "relativeOnlineTime", $0) })
        case let .hidePhone(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Скрыть номер телефона", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(\\\\.hidePhoneNumber, "hidePhoneNumber", $0) })
        case let .peerIdStyle(label):
            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: "ID профиля", label: label, sectionId: self.section, style: .blocks, action: { arguments.selectPeerIdStyle() })
        case .peerIdDescription:
            return ItemListTextItem(presentationData: presentationData, text: .plain("Добавляет вниз профиля ID и информацию о датацентре. Telegram API показывает ID как есть, Bot API добавляет минус для групп и -100 для супергрупп и каналов."), sectionId: self.section)
        }
    }
}

func ayuEssentialsSettingsController(context: AccountContext) -> ViewController {
    let revision = ValuePromise<Int32>(0, ignoreRepeated: false)
    var revisionValue: Int32 = 0
    let bump: () -> Void = {
        revisionValue &+= 1
        revision.set(revisionValue)
    }
    let controllerBox = AyuWeakControllerBox()

    let presentPeerIdPicker: () -> Void = {
        guard let host = controllerBox.value else {
            return
        }
        let presentationData = context.sharedContext.currentPresentationData.with { $0 }
        let actionSheet = ActionSheetController(presentationData: presentationData)
        let dismiss: () -> Void = { [weak actionSheet] in
            actionSheet?.dismissAnimated()
        }
        let current = AyuRuntimeSettings.snapshot.peerIdStyle
        let options: [(Int32, String)] = [
            (0, "Скрыть"),
            (1, "Telegram API"),
            (2, "Bot API")
        ]
        let items: [ActionSheetItem] = options.map { style, title in
            let displayTitle = style == current ? "✓ \\(title)" : title
            return ActionSheetButtonItem(title: displayTitle, action: {
                dismiss()
                AyuRuntimeSettings.setEssentialsPeerIdStyle(style)
                bump()
            })
        }
        actionSheet.setItemGroups([
            ActionSheetItemGroup(items: items),
            ActionSheetItemGroup(items: [
                ActionSheetButtonItem(title: presentationData.strings.Common_Cancel, color: .accent, font: .bold, action: { dismiss() })
            ])
        ])
        host.present(actionSheet, in: .window(.root))
    }

    let arguments = AyuEssentialsArguments(updateBool: { keyPath, name, value in
        AyuRuntimeSettings.setEssentialsBool(name, keyPath: keyPath, value: value)
        bump()
    }, selectPeerIdStyle: presentPeerIdPicker)

    let signal = combineLatest(context.sharedContext.presentationData, revision.get())
    |> deliverOnMainQueue
    |> map { presentationData, _ -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let snapshot = AyuRuntimeSettings.snapshot
        let onlineExample: String
        if snapshot.timeWithSeconds {
            onlineExample = "был(а) в 01:40:54"
        } else {
            onlineExample = "был(а) в 01:40"
        }
        let peerIdLabel: String
        switch snapshot.peerIdStyle {
        case 1: peerIdLabel = "Telegram API"
        case 2: peerIdLabel = "Bot API"
        default: peerIdLabel = "Скрыть"
        }
        let entries: [AyuEssentialsEntry] = [
            .essentialsHeader,
            .numberRounding(snapshot.disableNumberRounding),
            .timeWithSeconds(snapshot.timeWithSeconds),
            .zalgoFilter(snapshot.zalgoFilter),
            .zalgoDescription,
            .profileHeader,
            .relativeOnline(snapshot.relativeOnlineTime, onlineExample),
            .hidePhone(snapshot.hidePhoneNumber),
            .peerIdStyle(peerIdLabel),
            .peerIdDescription
        ]
        let controllerState = ItemListControllerState(
            presentationData: ItemListPresentationData(presentationData),
            title: .text("Основные"),
            leftNavigationButton: nil,
            rightNavigationButton: nil,
            backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back)
        )
        return (controllerState, (ItemListNodeState(presentationData: ItemListPresentationData(presentationData), entries: entries, style: .blocks, animateChanges: true), arguments))
    }

    let controller = ItemListController(context: context, state: signal)
    controllerBox.value = controller
    return controller
}
'''


def patch_settings_controller(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print(f"[ayu-essentials] already patched: {path}")
        return

    args_old = """private final class AyuExteraArguments {
    let openAppearance: () -> Void
    let openChats: () -> Void
    init(openAppearance: @escaping () -> Void, openChats: @escaping () -> Void) {
        self.openAppearance = openAppearance
        self.openChats = openChats
    }
}
"""
    args_new = """private final class AyuExteraArguments {
    let openEssentials: () -> Void
    let openAppearance: () -> Void
    let openChats: () -> Void
    init(openEssentials: @escaping () -> Void, openAppearance: @escaping () -> Void, openChats: @escaping () -> Void) {
        self.openEssentials = openEssentials
        self.openAppearance = openAppearance
        self.openChats = openChats
    }
}
"""
    text = replace_once(text, args_old, args_new, "extera arguments")

    enum_old = """private enum AyuExteraEntry: ItemListNodeEntry {
    case header
    case appearance
    case chats

    var section: ItemListSectionId { AyuExteraSection.categories.rawValue }
    var stableId: Int32 {
        switch self {
        case .header: return 0
        case .appearance: return 1
        case .chats: return 2
        }
    }
    static func <(lhs: AyuExteraEntry, rhs: AyuExteraEntry) -> Bool { lhs.stableId < rhs.stableId }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let arguments = arguments as! AyuExteraArguments
        switch self {
        case .header:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "КАТЕГОРИИ", sectionId: self.section)
        case .appearance:
            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: "Оформление", label: "", sectionId: self.section, style: .blocks, action: arguments.openAppearance)
        case .chats:
            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: "Чаты", label: "", sectionId: self.section, style: .blocks, action: arguments.openChats)
        }
    }
}
"""
    enum_new = """private enum AyuExteraEntry: ItemListNodeEntry {
    case header
    case essentials
    case appearance
    case chats

    var section: ItemListSectionId { AyuExteraSection.categories.rawValue }
    var stableId: Int32 {
        switch self {
        case .header: return 0
        case .essentials: return 1
        case .appearance: return 2
        case .chats: return 3
        }
    }
    static func <(lhs: AyuExteraEntry, rhs: AyuExteraEntry) -> Bool { lhs.stableId < rhs.stableId }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let arguments = arguments as! AyuExteraArguments
        switch self {
        case .header:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "КАТЕГОРИИ", sectionId: self.section)
        case .essentials:
            // AYU_ESSENTIALS_v1
            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: "Основные", label: "", sectionId: self.section, style: .blocks, action: arguments.openEssentials)
        case .appearance:
            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: "Оформление", label: "", sectionId: self.section, style: .blocks, action: arguments.openAppearance)
        case .chats:
            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: "Чаты", label: "", sectionId: self.section, style: .blocks, action: arguments.openChats)
        }
    }
}
"""
    text = replace_once(text, enum_old, enum_new, "extera entries enum")

    init_old = """    let arguments = AyuExteraArguments(openAppearance: {
        controllerBox.value?.push(ayuExteraAppearanceSettingsController(context: context))
    }, openChats: {
        controllerBox.value?.push(ayuExteraChatsSettingsController(context: context))
    })
"""
    init_new = """    let arguments = AyuExteraArguments(openEssentials: {
        // AYU_ESSENTIALS_v1
        controllerBox.value?.push(ayuEssentialsSettingsController(context: context))
    }, openAppearance: {
        controllerBox.value?.push(ayuExteraAppearanceSettingsController(context: context))
    }, openChats: {
        controllerBox.value?.push(ayuExteraChatsSettingsController(context: context))
    })
"""
    text = replace_once(text, init_old, init_new, "extera arguments init")

    entries_old = """        let entries: [AyuExteraEntry] = [.header, .appearance, .chats]
"""
    entries_new = """        // AYU_ESSENTIALS_v1
        let entries: [AyuExteraEntry] = [.header, .essentials, .appearance, .chats]
"""
    text = replace_once(text, entries_old, entries_new, "extera entries list")

    text = text.rstrip("\n") + "\n" + ESSENTIALS_CONTROLLER.replace("\\\\", "\\")
    path.write_text(text, encoding="utf-8")
    print(f"[ayu-essentials] essentials screen installed: {path}")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_extera_essentials.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()

    patch_runtime(root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift")
    patch_numeric_format(root / "submodules/TelegramPresentationData/Sources/NumericFormat.swift")
    patch_presence_strings(root / "submodules/TelegramStringFormatting/Sources/PresenceStrings.swift")
    patch_message_timestamp(root / "submodules/TelegramUI/Components/Chat/ChatMessageDateAndStatusNode/Sources/StringForMessageTimestampStatus.swift")
    patch_peer_title(root / "submodules/LocalizedPeerData/Sources/PeerTitle.swift")
    patch_message_text(root / "submodules/TelegramUI/Components/Chat/ChatMessageTextBubbleContentNode/Sources/ChatMessageTextBubbleContentNode.swift")
    patch_header_node(root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoHeaderNode.swift")
    patch_profile_items(root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoProfileItems.swift")
    patch_settings_controller(root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift")

    print("[ayu-essentials] DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
