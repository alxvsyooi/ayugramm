#!/usr/bin/env python3
from pathlib import Path
import sys

MARK = "AYU_SETTINGS_CATEGORIES_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {n}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_settings_categories.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()

    runtime = root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift"
    text = runtime.read_text(encoding="utf-8")
    if MARK not in text:
        text = one(
            text,
            "    case showDeletedMarker = 8\n}",
            "    case showDeletedMarker = 8\n    // AYU_SETTINGS_CATEGORIES_v0_3\n    case readOnActions = 9\n    case useScheduled = 10\n}",
            "runtime options",
        )
        text = one(
            text,
            "    public var showDeletedMarker: Bool\n    public var deletedMarkerStyle: Int32\n",
            "    public var showDeletedMarker: Bool\n    public var readOnActions: Bool\n    public var useScheduled: Bool\n    public var deletedMarkerStyle: Int32\n",
            "snapshot fields",
        )
        text = one(
            text,
            "        case .showDeletedMarker:\n            return keyPrefix + \"showDeletedMarker\"\n        }",
            "        case .showDeletedMarker:\n            return keyPrefix + \"showDeletedMarker\"\n        case .readOnActions:\n            return keyPrefix + \"readOnActions\"\n        case .useScheduled:\n            return keyPrefix + \"useScheduled\"\n        }",
            "option keys",
        )
        text = one(
            text,
            "        case .hideReadMessages, .hideReadStories, .hideOnline, .hideTyping, .automaticOffline, .onlinePulseOnSend, .keepDeletedMessages, .showDeletedMarker:\n            return true\n",
            "        case .hideReadMessages, .hideReadStories, .hideOnline, .hideTyping, .automaticOffline, .onlinePulseOnSend, .keepDeletedMessages, .showDeletedMarker, .readOnActions, .useScheduled:\n            return true\n",
            "defaults",
        )
        text = one(
            text,
            "        case .onlinePulseOnSend, .keepDeletedMessages, .showDeletedMarker:\n            break\n",
            "        case .onlinePulseOnSend, .keepDeletedMessages, .showDeletedMarker, .readOnActions, .useScheduled:\n            break\n",
            "legacy migration",
        )
        text = one(
            text,
            "            keepDeletedMessages: storedValue(.keepDeletedMessages, defaults: defaults),\n            showDeletedMarker: storedValue(.showDeletedMarker, defaults: defaults),\n            deletedMarkerStyle: style,",
            "            keepDeletedMessages: storedValue(.keepDeletedMessages, defaults: defaults),\n            showDeletedMarker: storedValue(.showDeletedMarker, defaults: defaults),\n            readOnActions: storedValue(.readOnActions, defaults: defaults),\n            useScheduled: storedValue(.useScheduled, defaults: defaults),\n            deletedMarkerStyle: style,",
            "load snapshot",
        )
        text = one(
            text,
            "        case .showDeletedMarker:\n            return current.showDeletedMarker\n        }\n    }",
            "        case .showDeletedMarker:\n            return current.showDeletedMarker\n        case .readOnActions:\n            return current.readOnActions\n        case .useScheduled:\n            return current.useScheduled\n        }\n    }",
            "runtime value",
        )
        text = one(
            text,
            "            case .showDeletedMarker:\n                current.showDeletedMarker = value\n            }\n",
            "            case .showDeletedMarker:\n                current.showDeletedMarker = value\n            case .readOnActions:\n                current.readOnActions = value\n            case .useScheduled:\n                current.useScheduled = value\n            }\n",
            "runtime set",
        )
    runtime.write_text(text, encoding="utf-8")

    # "Читать при действиях": when disabled under Ghost, sending must not advance
    # the peer read index and opening/listening to consumable media must not emit a
    # content-consumed receipt. Both checks are O(1) in-memory snapshot reads.
    enqueue = root / "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift"
    text = enqueue.read_text(encoding="utf-8")
    text = text.replace(
        "    guard AyuRuntimeSettings.snapshot.master else {\n        return\n    }\n\n    let _ = account.postbox.transaction",
        "    guard AyuRuntimeSettings.snapshot.master, AyuRuntimeSettings.snapshot.readOnActions else {\n        return\n    }\n\n    let _ = account.postbox.transaction",
        1,
    )
    enqueue.write_text(text, encoding="utf-8")

    consume = root / "submodules/TelegramCore/Sources/TelegramEngine/Messages/MarkMessageContentAsConsumedInteractively.swift"
    text = consume.read_text(encoding="utf-8")
    consume_anchor = "func _internal_markMessageContentAsConsumedInteractively(postbox: Postbox, messageId: MessageId) -> Signal<Void, NoError> {\n"
    consume_new = consume_anchor + "    if AyuRuntimeSettings.snapshot.master && !AyuRuntimeSettings.snapshot.readOnActions {\n        return .complete()\n    }\n"
    if "!AyuRuntimeSettings.snapshot.readOnActions" not in text:
        text = one(text, consume_anchor, consume_new, "content read-on-actions guard")
    consume.write_text(text, encoding="utf-8")

    settings = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift"
    settings.write_text(r'''import Foundation
import Display
import SwiftSignalKit
import TelegramCore
import TelegramPresentationData
import ItemListUI
import AccountContext

private final class AyuWeakControllerBox {
    weak var value: ViewController?
}

private enum AyuMainSection: Int32 {
    case categories
}

private final class AyuMainArguments {
    let openGhost: () -> Void
    let openCustomization: () -> Void

    init(openGhost: @escaping () -> Void, openCustomization: @escaping () -> Void) {
        self.openGhost = openGhost
        self.openCustomization = openCustomization
    }
}

private enum AyuMainEntry: ItemListNodeEntry {
    case header
    case ghost
    case customization

    var section: ItemListSectionId { return AyuMainSection.categories.rawValue }
    var stableId: Int32 {
        switch self {
        case .header: return 0
        case .ghost: return 1
        case .customization: return 2
        }
    }
    static func <(lhs: AyuMainEntry, rhs: AyuMainEntry) -> Bool { lhs.stableId < rhs.stableId }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let arguments = arguments as! AyuMainArguments
        switch self {
        case .header:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "КАТЕГОРИИ", sectionId: self.section)
        case .ghost:
            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: "Режим Призрака", label: "", sectionId: self.section, style: .blocks, action: { arguments.openGhost() })
        case .customization:
            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: "Кастомизация", label: "", sectionId: self.section, style: .blocks, action: { arguments.openCustomization() })
        }
    }
}

private final class AyuGhostArguments {
    let updateBool: (AyuRuntimeOption, Bool) -> Void
    init(updateBool: @escaping (AyuRuntimeOption, Bool) -> Void) {
        self.updateBool = updateBool
    }
}

private enum AyuGhostSection: Int32 {
    case ghost
    case actions
}

private enum AyuGhostEntry: ItemListNodeEntry {
    case header
    case master(String, Bool)
    case read(Bool)
    case stories(Bool)
    case online(Bool)
    case typing(Bool)
    case automaticOffline(Bool)
    case actionsHeader
    case readOnActions(Bool)
    case useScheduled(Bool)
    case useScheduledInfo

    var section: ItemListSectionId {
        switch self {
        case .header, .master, .read, .stories, .online, .typing, .automaticOffline:
            return AyuGhostSection.ghost.rawValue
        case .actionsHeader, .readOnActions, .useScheduled, .useScheduledInfo:
            return AyuGhostSection.actions.rawValue
        }
    }
    var stableId: Int32 {
        switch self {
        case .header: return 0
        case .master: return 1
        case .read: return 2
        case .stories: return 3
        case .online: return 4
        case .typing: return 5
        case .automaticOffline: return 6
        case .actionsHeader: return 10
        case .readOnActions: return 11
        case .useScheduled: return 12
        case .useScheduledInfo: return 13
        }
    }
    static func <(lhs: AyuGhostEntry, rhs: AyuGhostEntry) -> Bool { lhs.stableId < rhs.stableId }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let arguments = arguments as! AyuGhostArguments
        switch self {
        case .header:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "РЕЖИМ ПРИЗРАКА", sectionId: self.section)
        case let .master(title, value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: title, value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.master, $0) })
        case let .read(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Не читать сообщения", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.hideReadMessages, $0) })
        case let .stories(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Не отмечать просмотр историй", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.hideReadStories, $0) })
        case let .online(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Скрывать онлайн", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.hideOnline, $0) })
        case let .typing(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Скрывать «печатает…»", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.hideTyping, $0) })
        case let .automaticOffline(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Автоматически офлайн", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.automaticOffline, $0) })
        case .actionsHeader:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "ДЕЙСТВИЯ", sectionId: self.section)
        case let .readOnActions(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Читать при действиях", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.readOnActions, $0) })
        case let .useScheduled(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Использовать отложку", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.useScheduled, $0) })
        case .useScheduledInfo:
            return ItemListTextItem(presentationData: presentationData, text: .markdown("Использует отложенную отправку, когда это требуется режиму призрака."), sectionId: self.section)
        }
    }
}

private func ayuGhostEntries(_ snapshot: AyuRuntimeSnapshot) -> [AyuGhostEntry] {
    let enabledCount = [snapshot.hideReadMessages, snapshot.hideReadStories, snapshot.hideOnline, snapshot.hideTyping, snapshot.automaticOffline].filter { $0 }.count
    return [
        .header,
        .master("Режим призрака \(enabledCount)/5", snapshot.master),
        .read(snapshot.hideReadMessages),
        .stories(snapshot.hideReadStories),
        .online(snapshot.hideOnline),
        .typing(snapshot.hideTyping),
        .automaticOffline(snapshot.automaticOffline),
        .actionsHeader,
        .readOnActions(snapshot.readOnActions),
        .useScheduled(snapshot.useScheduled),
        .useScheduledInfo
    ]
}

private final class AyuCustomizationArguments {
    let updateBool: (AyuRuntimeOption, Bool) -> Void
    let selectDeletedStyle: () -> Void
    let selectDeletedColor: () -> Void
    let clearDeleted: () -> Void

    init(updateBool: @escaping (AyuRuntimeOption, Bool) -> Void, selectDeletedStyle: @escaping () -> Void, selectDeletedColor: @escaping () -> Void, clearDeleted: @escaping () -> Void) {
        self.updateBool = updateBool
        self.selectDeletedStyle = selectDeletedStyle
        self.selectDeletedColor = selectDeletedColor
        self.clearDeleted = clearDeleted
    }
}

private enum AyuCustomizationSection: Int32 { case deleted }
private enum AyuCustomizationEntry: ItemListNodeEntry {
    case header
    case keepDeleted(Bool)
    case showMarker(Bool)
    case markerStyle(String)
    case markerColor(String)
    case clearDeleted

    var section: ItemListSectionId { AyuCustomizationSection.deleted.rawValue }
    var stableId: Int32 {
        switch self {
        case .header: return 0
        case .keepDeleted: return 1
        case .showMarker: return 2
        case .markerStyle: return 3
        case .markerColor: return 4
        case .clearDeleted: return 5
        }
    }
    static func <(lhs: AyuCustomizationEntry, rhs: AyuCustomizationEntry) -> Bool { lhs.stableId < rhs.stableId }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let arguments = arguments as! AyuCustomizationArguments
        switch self {
        case .header:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "УДАЛЁННЫЕ СООБЩЕНИЯ", sectionId: self.section)
        case let .keepDeleted(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Сохранять удалённые сообщения", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.keepDeletedMessages, $0) })
        case let .showMarker(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Показывать метку удаления", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.showDeletedMarker, $0) })
        case let .markerStyle(value):
            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: "Метка удаления", label: value, sectionId: self.section, style: .blocks, action: { arguments.selectDeletedStyle() })
        case let .markerColor(value):
            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: "Цвет фона удалённых", label: value, sectionId: self.section, style: .blocks, action: { arguments.selectDeletedColor() })
        case .clearDeleted:
            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: "Очистить метки удалённых", label: "", sectionId: self.section, style: .blocks, action: { arguments.clearDeleted() })
        }
    }
}

private func ayuCustomizationController(context: AccountContext) -> ViewController {
    let revision = ValuePromise<Int32>(0, ignoreRepeated: false)
    var revisionValue: Int32 = 0
    let bump: () -> Void = { revisionValue &+= 1; revision.set(revisionValue) }
    let controllerBox = AyuWeakControllerBox()

    let presentStylePicker: () -> Void = {
        guard let host = controllerBox.value else { return }
        let presentationData = context.sharedContext.currentPresentationData.with { $0 }
        let actionSheet = ActionSheetController(presentationData: presentationData)
        let dismiss: () -> Void = { [weak actionSheet] in actionSheet?.dismissAnimated() }
        let current = AyuDeletedMarkerStyle(rawValue: AyuRuntimeSettings.snapshot.deletedMarkerStyle) ?? .trash
        let options: [(AyuDeletedMarkerStyle, String)] = [(.text, "Убрать значок"), (.trash, "👀"), (.cross, "❌"), (.compact, "👀")]
        let items: [ActionSheetItem] = options.map { style, title in
            ActionSheetButtonItem(title: style == current ? "✓ \(title)" : title, action: { dismiss(); AyuRuntimeSettings.setDeletedMarkerStyle(style.rawValue); bump() })
        }
        actionSheet.setItemGroups([ActionSheetItemGroup(items: items), ActionSheetItemGroup(items: [ActionSheetButtonItem(title: presentationData.strings.Common_Cancel, color: .accent, font: .bold, action: { dismiss() })])])
        host.present(actionSheet, in: .window(.root))
    }

    let presentColorPicker: () -> Void = {
        guard let host = controllerBox.value else { return }
        let presentationData = context.sharedContext.currentPresentationData.with { $0 }
        let actionSheet = ActionSheetController(presentationData: presentationData)
        let dismiss: () -> Void = { [weak actionSheet] in actionSheet?.dismissAnimated() }
        let current = AyuDeletedMarkerColor(rawValue: AyuRuntimeSettings.snapshot.deletedMarkerColor) ?? .telegram
        let options: [(AyuDeletedMarkerColor, String)] = [(.telegram, "Тема Telegram"), (.gray, "⚪️ Серый"), (.red, "🔴 Красный"), (.orange, "🟠 Оранжевый"), (.pink, "🩷 Розовый"), (.magenta, "🩷 Малиновый"), (.purple, "🟣 Фиолетовый"), (.indigo, "🔵 Индиго"), (.blue, "🔵 Синий")]
        let items: [ActionSheetItem] = options.map { color, title in
            ActionSheetButtonItem(title: color == current ? "✓ \(title)" : title, action: { dismiss(); AyuRuntimeSettings.setDeletedMarkerColor(color.rawValue); bump() })
        }
        actionSheet.setItemGroups([ActionSheetItemGroup(items: items), ActionSheetItemGroup(items: [ActionSheetButtonItem(title: presentationData.strings.Common_Cancel, color: .accent, font: .bold, action: { dismiss() })])])
        host.present(actionSheet, in: .window(.root))
    }

    let arguments = AyuCustomizationArguments(updateBool: { option, value in AyuRuntimeSettings.set(option, value: value); bump() }, selectDeletedStyle: presentStylePicker, selectDeletedColor: presentColorPicker, clearDeleted: { AyuRuntimeSettings.clearDeletedMarkers(); bump() })
    let signal = combineLatest(context.sharedContext.presentationData, revision.get()) |> deliverOnMainQueue |> map { presentationData, _ -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let snapshot = AyuRuntimeSettings.snapshot
        let entries: [AyuCustomizationEntry] = [.header, .keepDeleted(snapshot.keepDeletedMessages), .showMarker(snapshot.showDeletedMarker), .markerStyle(AyuRuntimeSettings.deletedMarkerStyleTitle), .markerColor(AyuRuntimeSettings.deletedMarkerColorTitle), .clearDeleted]
        let controllerState = ItemListControllerState(presentationData: ItemListPresentationData(presentationData), title: .text("Кастомизация"), leftNavigationButton: nil, rightNavigationButton: nil, backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back))
        return (controllerState, (ItemListNodeState(presentationData: ItemListPresentationData(presentationData), entries: entries, style: .blocks, animateChanges: true), arguments))
    }
    let controller = ItemListController(context: context, state: signal)
    controllerBox.value = controller
    return controller
}

private func ayuGhostSettingsController(context: AccountContext) -> ViewController {
    let revision = ValuePromise<Int32>(0, ignoreRepeated: false)
    var revisionValue: Int32 = 0
    let bump: () -> Void = { revisionValue &+= 1; revision.set(revisionValue) }
    let arguments = AyuGhostArguments(updateBool: { option, value in
        AyuRuntimeSettings.set(option, value: value)
        switch option {
        case .master, .hideOnline:
            ayuApplyGhostPresence(account: context.account)
        default:
            break
        }
        bump()
    })
    let signal = combineLatest(context.sharedContext.presentationData, revision.get()) |> deliverOnMainQueue |> map { presentationData, _ -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let controllerState = ItemListControllerState(presentationData: ItemListPresentationData(presentationData), title: .text("Режим Призрака"), leftNavigationButton: nil, rightNavigationButton: nil, backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back))
        return (controllerState, (ItemListNodeState(presentationData: ItemListPresentationData(presentationData), entries: ayuGhostEntries(AyuRuntimeSettings.snapshot), style: .blocks, animateChanges: true), arguments))
    }
    return ItemListController(context: context, state: signal)
}

func ayuSettingsController(context: AccountContext) -> ViewController {
    let controllerBox = AyuWeakControllerBox()
    let arguments = AyuMainArguments(openGhost: { [weak controllerBox] in
        controllerBox?.value?.push(ayuGhostSettingsController(context: context))
    }, openCustomization: { [weak controllerBox] in
        controllerBox?.value?.push(ayuCustomizationController(context: context))
    })
    let signal = context.sharedContext.presentationData |> deliverOnMainQueue |> map { presentationData -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let controllerState = ItemListControllerState(presentationData: ItemListPresentationData(presentationData), title: .text("Настройки AyuGram"), leftNavigationButton: nil, rightNavigationButton: nil, backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back))
        let entries: [AyuMainEntry] = [.header, .ghost, .customization]
        return (controllerState, (ItemListNodeState(presentationData: ItemListPresentationData(presentationData), entries: entries, style: .blocks, animateChanges: false), arguments))
    }
    let controller = ItemListController(context: context, state: signal)
    controllerBox.value = controller
    return controller
}
''', encoding="utf-8")

    print("[ayu-settings-categories] categories + Ghost 5/5 + read-on-actions + scheduled toggle installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
