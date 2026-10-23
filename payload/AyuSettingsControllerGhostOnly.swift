import Foundation
import Display
import SwiftSignalKit
import TelegramCore
import TelegramPresentationData
import ItemListUI
import AccountContext

private final class AyuGhostSettingsArguments {
    let updateBool: (AyuRuntimeOption, Bool) -> Void
    init(updateBool: @escaping (AyuRuntimeOption, Bool) -> Void) { self.updateBool = updateBool }
}

private enum AyuGhostSettingsSection: Int32 { case ghost }

private enum AyuGhostSettingsEntry: ItemListNodeEntry {
    case header
    case master(Bool)
    case read(Bool)
    case stories(Bool)
    case online(Bool)
    case typing(Bool)

    var section: ItemListSectionId { AyuGhostSettingsSection.ghost.rawValue }
    var stableId: Int32 {
        switch self {
        case .header: return 0
        case .master: return 1
        case .read: return 2
        case .stories: return 3
        case .online: return 4
        case .typing: return 5
        }
    }
    static func <(lhs: AyuGhostSettingsEntry, rhs: AyuGhostSettingsEntry) -> Bool { lhs.stableId < rhs.stableId }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let arguments = arguments as! AyuGhostSettingsArguments
        switch self {
        case .header:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "РЕЖИМ ПРИЗРАКА", sectionId: self.section)
        case let .master(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Режим призрака", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.master, $0) })
        case let .read(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Не читать сообщения", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.hideReadMessages, $0) })
        case let .stories(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Не отмечать просмотр историй", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.hideReadStories, $0) })
        case let .online(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Скрывать онлайн", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.hideOnline, $0) })
        case let .typing(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Скрывать «печатает…»", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.hideTyping, $0) })
        }
    }
}

private func ayuGhostSettingsEntries(_ snapshot: AyuRuntimeSnapshot) -> [AyuGhostSettingsEntry] {
    [.header, .master(snapshot.master), .read(snapshot.hideReadMessages), .stories(snapshot.hideReadStories), .online(snapshot.hideOnline), .typing(snapshot.hideTyping)]
}

func ayuSettingsController(context: AccountContext) -> ViewController {
    let revision = ValuePromise<Int32>(0, ignoreRepeated: false)
    var revisionValue: Int32 = 0
    let bump: () -> Void = { revisionValue &+= 1; revision.set(revisionValue) }
    let arguments = AyuGhostSettingsArguments(updateBool: { option, value in
        AyuRuntimeSettings.set(option, value: value)
        if value && (option == .master || option == .hideOnline) && AyuRuntimeSettings.suppressOnlineStatus { AyuGhostLastSeen.recordNow() }
        bump()
    })
    let signal = combineLatest(context.sharedContext.presentationData, revision.get())
    |> deliverOnMainQueue
    |> map { presentationData, _ -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let pd = ItemListPresentationData(presentationData)
        return (
            ItemListControllerState(presentationData: pd, title: .text("AyuGram"), leftNavigationButton: nil, rightNavigationButton: nil, backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back)),
            (ItemListNodeState(presentationData: pd, entries: ayuGhostSettingsEntries(AyuRuntimeSettings.snapshot), style: .blocks, animateChanges: true), arguments)
        )
    }
    return ItemListController(context: context, state: signal)
}
