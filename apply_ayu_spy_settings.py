#!/usr/bin/env python3
from pathlib import Path
import sys

MARK = "AYU_SPY_SETTINGS_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_spy_settings.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()

    runtime = root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift"
    text = runtime.read_text(encoding="utf-8")
    if MARK not in text:
        text = one(
            text,
            "    case useScheduled = 10\n}",
            "    case useScheduled = 10\n    // AYU_SPY_SETTINGS_v0_3\n    case saveEditHistory = 11\n    case saveReadDates = 12\n}",
            "spy runtime options",
        )
        text = one(
            text,
            "    public var useScheduled: Bool\n    public var deletedMarkerStyle: Int32\n",
            "    public var useScheduled: Bool\n    public var saveEditHistory: Bool\n    public var saveReadDates: Bool\n    public var deletedMarkerStyle: Int32\n",
            "spy snapshot fields",
        )
        text = one(
            text,
            "        case .useScheduled:\n            return keyPrefix + \"useScheduled\"\n        }",
            "        case .useScheduled:\n            return keyPrefix + \"useScheduled\"\n        case .saveEditHistory:\n            return keyPrefix + \"spy.saveEditHistory\"\n        case .saveReadDates:\n            return keyPrefix + \"spy.saveReadDates\"\n        }",
            "spy keys",
        )
        text = one(
            text,
            "        case .hideReadMessages, .hideReadStories, .hideOnline, .hideTyping, .automaticOffline, .onlinePulseOnSend, .keepDeletedMessages, .showDeletedMarker, .readOnActions, .useScheduled:\n            return true\n",
            "        case .hideReadMessages, .hideReadStories, .hideOnline, .hideTyping, .automaticOffline, .onlinePulseOnSend, .keepDeletedMessages, .showDeletedMarker, .readOnActions, .useScheduled, .saveEditHistory, .saveReadDates:\n            return true\n",
            "spy defaults",
        )
        text = one(
            text,
            "        case .onlinePulseOnSend, .keepDeletedMessages, .showDeletedMarker, .readOnActions, .useScheduled:\n            break\n",
            "        case .onlinePulseOnSend, .keepDeletedMessages, .showDeletedMarker, .readOnActions, .useScheduled, .saveEditHistory, .saveReadDates:\n            break\n",
            "spy migration",
        )
        text = one(
            text,
            "            readOnActions: storedValue(.readOnActions, defaults: defaults),\n            useScheduled: storedValue(.useScheduled, defaults: defaults),\n            deletedMarkerStyle: style,",
            "            readOnActions: storedValue(.readOnActions, defaults: defaults),\n            useScheduled: storedValue(.useScheduled, defaults: defaults),\n            saveEditHistory: storedValue(.saveEditHistory, defaults: defaults),\n            saveReadDates: storedValue(.saveReadDates, defaults: defaults),\n            deletedMarkerStyle: style,",
            "spy load snapshot",
        )
        text = one(
            text,
            "        case .useScheduled:\n            return current.useScheduled\n        }\n    }",
            "        case .useScheduled:\n            return current.useScheduled\n        case .saveEditHistory:\n            return current.saveEditHistory\n        case .saveReadDates:\n            return current.saveReadDates\n        }\n    }",
            "spy value",
        )
        text = one(
            text,
            "            case .useScheduled:\n                current.useScheduled = value\n            }\n",
            "            case .useScheduled:\n                current.useScheduled = value\n            case .saveEditHistory:\n                current.saveEditHistory = value\n            case .saveReadDates:\n                current.saveReadDates = value\n            }\n",
            "spy set",
        )
    runtime.write_text(text, encoding="utf-8")

    settings = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift"
    text = settings.read_text(encoding="utf-8")
    if MARK not in text:
        text = one(
            text,
            "private final class AyuMainArguments {\n    let openGhost: () -> Void\n    let openCustomization: () -> Void\n\n    init(openGhost: @escaping () -> Void, openCustomization: @escaping () -> Void) {\n        self.openGhost = openGhost\n        self.openCustomization = openCustomization\n    }\n}",
            "private final class AyuMainArguments {\n    let openGhost: () -> Void\n    let openCustomization: () -> Void\n    let openSpy: () -> Void\n\n    init(openGhost: @escaping () -> Void, openCustomization: @escaping () -> Void, openSpy: @escaping () -> Void) {\n        self.openGhost = openGhost\n        self.openCustomization = openCustomization\n        self.openSpy = openSpy\n    }\n}",
            "main arguments",
        )
        text = one(
            text,
            "private enum AyuMainEntry: ItemListNodeEntry {\n    case header\n    case ghost\n    case customization\n",
            "private enum AyuMainEntry: ItemListNodeEntry {\n    case header\n    case ghost\n    case customization\n    case spy\n",
            "main spy entry",
        )
        text = one(
            text,
            "        case .header: return 0\n        case .ghost: return 1\n        case .customization: return 2\n",
            "        case .header: return 0\n        case .ghost: return 1\n        case .customization: return 2\n        case .spy: return 3\n",
            "main spy id",
        )
        text = one(
            text,
            "        case .customization:\n            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: \"Кастомизация\", label: \"\", sectionId: self.section, style: .blocks, action: { arguments.openCustomization() })\n        }",
            "        case .customization:\n            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: \"Кастомизация\", label: \"\", sectionId: self.section, style: .blocks, action: { arguments.openCustomization() })\n        case .spy:\n            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: \"Шпион\", label: \"\", sectionId: self.section, style: .blocks, action: { arguments.openSpy() })\n        }",
            "main spy row",
        )

        spy_code = r'''
// AYU_SPY_SETTINGS_v0_3
private final class AyuSpyArguments {
    let updateBool: (AyuRuntimeOption, Bool) -> Void
    init(updateBool: @escaping (AyuRuntimeOption, Bool) -> Void) {
        self.updateBool = updateBool
    }
}

private enum AyuSpySection: Int32 { case spy }

private enum AyuSpyEntry: ItemListNodeEntry {
    case header
    case deleted(Bool)
    case edits(Bool)
    case readDates(Bool)
    case readDatesInfo

    var section: ItemListSectionId { AyuSpySection.spy.rawValue }
    var stableId: Int32 {
        switch self {
        case .header: return 0
        case .deleted: return 1
        case .edits: return 2
        case .readDates: return 3
        case .readDatesInfo: return 4
        }
    }
    static func <(lhs: AyuSpyEntry, rhs: AyuSpyEntry) -> Bool { lhs.stableId < rhs.stableId }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let arguments = arguments as! AyuSpyArguments
        switch self {
        case .header:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "РЕЖИМ ШПИОНА", sectionId: self.section)
        case let .deleted(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Сохранять удалённые сообщения", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.keepDeletedMessages, $0) })
        case let .edits(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Сохранять историю правок", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.saveEditHistory, $0) })
        case let .readDates(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Сохранять дату прочтения", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.saveReadDates, $0) })
        case .readDatesInfo:
            return ItemListTextItem(presentationData: presentationData, text: .markdown("Локально сохраняет данные о чтении сообщений. Будет использоваться, если Telegram не предоставит дату чтения"), sectionId: self.section)
        }
    }
}

private func ayuSpySettingsController(context: AccountContext) -> ViewController {
    let revision = ValuePromise<Int32>(0, ignoreRepeated: false)
    var revisionValue: Int32 = 0
    let bump: () -> Void = {
        revisionValue &+= 1
        revision.set(revisionValue)
    }
    let arguments = AyuSpyArguments(updateBool: { option, value in
        AyuRuntimeSettings.set(option, value: value)
        bump()
    })
    let signal = combineLatest(context.sharedContext.presentationData, revision.get())
    |> deliverOnMainQueue
    |> map { presentationData, _ -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let snapshot = AyuRuntimeSettings.snapshot
        let entries: [AyuSpyEntry] = [
            .header,
            .deleted(snapshot.keepDeletedMessages),
            .edits(snapshot.saveEditHistory),
            .readDates(snapshot.saveReadDates),
            .readDatesInfo
        ]
        let controllerState = ItemListControllerState(
            presentationData: ItemListPresentationData(presentationData),
            title: .text("Шпион"),
            leftNavigationButton: nil,
            rightNavigationButton: nil,
            backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back)
        )
        return (controllerState, (ItemListNodeState(presentationData: ItemListPresentationData(presentationData), entries: entries, style: .blocks, animateChanges: true), arguments))
    }
    return ItemListController(context: context, state: signal)
}

'''
        text = one(text, "func ayuSettingsController(context: AccountContext) -> ViewController {\n", spy_code + "func ayuSettingsController(context: AccountContext) -> ViewController {\n", "spy controller insertion")
        text = one(
            text,
            "    let arguments = AyuMainArguments(openGhost: { [weak controllerBox] in\n        controllerBox?.value?.push(ayuGhostSettingsController(context: context))\n    }, openCustomization: { [weak controllerBox] in\n        controllerBox?.value?.push(ayuCustomizationController(context: context))\n    })",
            "    // AYU_SETTINGS_NAVIGATION_FIX_v0_3: AyuWeakControllerBox already keeps\n    // the controller weakly, so the actions must retain the box itself.\n    let arguments = AyuMainArguments(openGhost: {\n        controllerBox.value?.push(ayuGhostSettingsController(context: context))\n    }, openCustomization: {\n        controllerBox.value?.push(ayuCustomizationController(context: context))\n    }, openSpy: {\n        controllerBox.value?.push(ayuSpySettingsController(context: context))\n    })",
            "main spy navigation",
        )
        text = one(
            text,
            "        let entries: [AyuMainEntry] = [.header, .ghost, .customization]",
            "        let entries: [AyuMainEntry] = [.header, .ghost, .customization, .spy]",
            "main spy list",
        )
    settings.write_text(text, encoding="utf-8")

    print("[ayu-spy-settings] Spy category + deleted/edit/read-date toggles + category navigation lifetime fixed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
