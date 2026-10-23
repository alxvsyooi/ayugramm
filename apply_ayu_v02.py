#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

PATCH_VERSION = "0.2.5"
MARK = "AYU_IOS_PATCH_v0_2"


def die(message: str) -> None:
    print(f"[ayu-v02] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def backup(path: Path) -> None:
    dst = path.with_suffix(path.suffix + ".ayu-v02.bak")
    if not dst.exists():
        shutil.copy2(path, dst)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        die(f"anchor '{label}' expected exactly once, found {count}")
    return text.replace(old, new, 1)


def patch_file(path: Path, transform) -> None:
    if not path.exists():
        die(f"missing file: {path}")
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print(f"[ayu-v02] already patched: {path}")
        return
    new_text = transform(text)
    if new_text == text:
        die(f"patch produced no changes: {path}")
    backup(path)
    path.write_text(new_text, encoding="utf-8")
    print(f"[ayu-v02] patched: {path}")


def patch_presence(text: str) -> str:
    old = """    private func updatePresence(_ isOnline: Bool) {\n        let request: Signal<Api.Bool, MTRpcError>\n        if isOnline {\n"""
    new = """    private func updatePresence(_ isOnline: Bool) {\n        // AYU_IOS_PATCH_v0_2: Ghost presence without an extra polling/timer loop.\n        // When Ghost is active, Telegram's own 30-second online refresh timer is never created.\n        if isOnline && AyuRuntimeSettings.suppressOnlineStatus {\n            self.onlineTimer?.invalidate()\n            self.onlineTimer = nil\n\n            if !AyuRuntimeSettings.shouldSendAutomaticOffline {\n                self.currentRequestDisposable.set(nil)\n                self.isPerformingUpdate.set(false)\n                return\n            }\n\n            self.isPerformingUpdate.set(true)\n            let request = self.network.request(Api.functions.account.updateStatus(offline: .boolTrue))\n            self.currentRequestDisposable.set((request\n            |> `catch` { _ -> Signal<Api.Bool, NoError> in\n                return .single(.boolFalse)\n            }\n            |> deliverOn(self.queue)).start(completed: { [weak self] in\n                self?.isPerformingUpdate.set(false)\n            }))\n            return\n        }\n\n        let request: Signal<Api.Bool, MTRpcError>\n        if isOnline {\n"""
    return replace_once(text, old, new, "presence")


def patch_typing(text: str) -> str:
    old = """private func requestActivity(postbox: Postbox, network: Network, accountPeerId: PeerId, peerId: PeerId, threadId: Int64?, activity: PeerInputActivity?) -> Signal<Void, NoError> {\n    return postbox.transaction { transaction -> Signal<Void, NoError> in\n"""
    # Preserve nil cancel actions. Also preserve group-call speech and emoji interaction semantics.
    new = """private func requestActivity(postbox: Postbox, network: Network, accountPeerId: PeerId, peerId: PeerId, threadId: Int64?, activity: PeerInputActivity?) -> Signal<Void, NoError> {\n    // AYU_IOS_PATCH_v0_2: a single in-memory flag check before Postbox/network work.\n    if AyuRuntimeSettings.suppressTypingActivities, let activity {\n        switch activity {\n        case .speakingInGroupCall, .interactingWithEmoji, .seeingEmojiInteraction:\n            break\n        default:\n            return .complete()\n        }\n    }\n\n    return postbox.transaction { transaction -> Signal<Void, NoError> in\n"""
    return replace_once(text, old, new, "typing")


def patch_read_state(text: str) -> str:
    # Critical difference from v0.1: do NOT bypass Telegram's operation-log/state machine.
    # We only replace the low-level network push with .single(readState). The existing outer
    # verification still confirms the local synchronized operation normally.
    old_low = """private func pushPeerReadState(network: Network, postbox: Postbox, stateManager: AccountStateManager, peerId: PeerId, readState: PeerReadState) -> Signal<PeerReadState, PeerReadStateValidationError> {\n    if peerId.namespace == Namespaces.Peer.SecretChat {\n"""
    new_low = """private func pushPeerReadState(network: Network, postbox: Postbox, stateManager: AccountStateManager, peerId: PeerId, readState: PeerReadState) -> Signal<PeerReadState, PeerReadStateValidationError> {\n    // AYU_IOS_PATCH_v0_2: preserve Telegram's read-state synchronization state machine,\n    // but don't emit readHistory/readEncryptedHistory while Ghost is active.\n    if AyuRuntimeSettings.suppressReadMessages {\n        return .single(readState)\n    }\n\n    if peerId.namespace == Namespaces.Peer.SecretChat {\n"""
    text = replace_once(text, old_low, new_low, "read-low-level")

    old_validate = """    if validate {\n        signal = signal\n        |> then(validatePeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n"""
    new_validate = """    if validate && !AyuRuntimeSettings.suppressReadMessages {\n        // AYU_IOS_PATCH_v0_2: validation queries server read-state and can undo the local\n        // ghost read. Skip only validation while suppression is active.\n        signal = signal\n        |> then(validatePeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n"""
    text = replace_once(text, old_validate, new_validate, "read-validation")
    return text


def patch_stories(text: str) -> str:
    old = """private func pushStoriesAreSeen(postbox: Postbox, network: Network, stateManager: AccountStateManager, peer: Peer, operation: SynchronizeViewStoriesOperation) -> Signal<Void, NoError> {\n    guard let inputPeer = apiInputPeer(peer) else {\n"""
    new = """private func pushStoriesAreSeen(postbox: Postbox, network: Network, stateManager: AccountStateManager, peer: Peer, operation: SynchronizeViewStoriesOperation) -> Signal<Void, NoError> {\n    // AYU_IOS_PATCH_v0_2: caller already consumes the operation after completion, so this\n    // suppresses only stories.readStories and leaves the operation log consistent.\n    if AyuRuntimeSettings.suppressStoryViews {\n        return .complete()\n    }\n\n    guard let inputPeer = apiInputPeer(peer) else {\n"""
    return replace_once(text, old, new, "story-views")


def patch_debug_ui(text: str) -> str:
    # Add a small, isolated control surface to Telegram's existing Debug screen.
    # This intentionally avoids modifying SettingsUI's enormous privacy enum/switch graph,
    # which was the fragile part of v0.1.
    anchor = "private enum DebugControllerSection: Int32 {"
    if anchor not in text:
        die("debug helper anchor missing")

    helper = r'''
// AYU_IOS_PATCH_v0_2: isolated settings UI. No SettingsUI enum surgery.
private func presentAyuGhostSettings(arguments: DebugControllerArguments) {
    guard let rootController = arguments.getRootController() else {
        return
    }

    func mark(_ value: Bool) -> String {
        return value ? "✓" : "○"
    }

    let current = AyuRuntimeSettings.snapshot
    let message = current.master ? "Ghost Mode включён" : "Ghost Mode выключен"
    let alert = UIAlertController(title: "AyuGram · Режим призрака", message: message, preferredStyle: .alert)

    func addToggle(_ title: String, option: AyuRuntimeOption) {
        let value = AyuRuntimeSettings.value(option)
        alert.addAction(UIAlertAction(title: "\(mark(value)) \(title)", style: .default, handler: { _ in
            AyuRuntimeSettings.set(option, value: !value)
            DispatchQueue.main.async {
                presentAyuGhostSettings(arguments: arguments)
            }
        }))
    }

    addToggle("Режим призрака", option: .master)
    addToggle("Не читать сообщения", option: .hideReadMessages)
    addToggle("Не читать истории", option: .hideReadStories)
    addToggle("Не отправлять «онлайн»", option: .hideOnline)
    addToggle("Не отправлять «печатает»", option: .hideTyping)
    addToggle("Автоматический «офлайн»", option: .automaticOffline)

    alert.addAction(UIAlertAction(title: "Закрыть", style: .cancel))
    rootController.present(alert, animated: true)
}

private func presentAyuSettings(arguments: DebugControllerArguments) {
    guard let rootController = arguments.getRootController() else {
        return
    }

    let alert = UIAlertController(
        title: "AyuGram iOS v0.2.5",
        message: "Стабильная база. Ghost работает. Шпион и метки удалённых сообщений подключаются следующим слоем после проверки стабильности.",
        preferredStyle: .alert
    )
    alert.addAction(UIAlertAction(title: "Режим призрака", style: .default, handler: { _ in
        DispatchQueue.main.async {
            presentAyuGhostSettings(arguments: arguments)
        }
    }))

    let spy = UIAlertAction(title: "Шпион · backend v0.3", style: .default, handler: nil)
    spy.isEnabled = false
    alert.addAction(spy)

    let deleted = UIAlertAction(title: "Метки удалёнок · backend v0.3", style: .default, handler: nil)
    deleted.isEnabled = false
    alert.addAction(deleted)

    alert.addAction(UIAlertAction(title: "Закрыть", style: .cancel))
    rootController.present(alert, animated: true)
}

'''
    text = text.replace(anchor, helper + anchor, 1)

    # Replace ONLY the .accounts branch inside item(...).
    #
    # Telegram currently declares the enum case as accounts(PresentationTheme), so
    # inside `switch self` the branch can be formatted as either:
    #   case .accounts:
    #   case let .accounts(theme):
    #   case .accounts(_):
    #
    # Do not depend on the exact associated-value spelling or on the next case name.
    item_anchor = "    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {"
    item_start = text.find(item_anchor)
    if item_start == -1:
        die("debug item() anchor missing")

    prefix = text[:item_start]
    item_text = text[item_start:]

    # Only match a switch case at DebugControllerEntry's normal 8-space indentation.
    # The lookahead stops at the next sibling case, not at nested closure contents.
    pattern = re.compile(
        r"(?ms)^        case(?:\s+let)?\s+\.accounts(?:\([^\n:]*\))?\s*:"
        r".*?(?=^        case\s)"
    )
    matches = list(pattern.finditer(item_text))
    if len(matches) != 1:
        samples = re.findall(
            r"(?m)^        case[^\n]*accounts[^\n]*$",
            item_text
        )
        die(
            "debug accounts item expected once inside item(), "
            f"found {len(matches)}; candidates={samples[:5]}"
        )

    replacement = (
        '        case .accounts:\n'
        '            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: "AyuGram Settings", label: "", sectionId: self.section, style: .blocks, action: {\n'
        '                presentAyuSettings(arguments: arguments)\n'
        '            })\n'
    )

    m = matches[0]
    item_text = item_text[:m.start()] + replacement + item_text[m.end():]
    text = prefix + item_text

    # Fail fast if the earlier enum switches were touched.
    section_ok = "        case .accounts:\n            return DebugControllerSection.logs.rawValue"
    stable_ok = "        case .accounts:\n            return 9"
    if section_ok not in prefix:
        die("debug section switch missing/corrupted before item()")
    if stable_ok not in prefix:
        die("debug stableId switch missing/corrupted before item()")

    # The injected Ayu row must exist exactly once and only after item(...).
    if text.count('title: "AyuGram Settings"') != 1:
        die("AyuGram Settings row expected exactly once")
    if text.index('title: "AyuGram Settings"') < item_start:
        die("AyuGram Settings row injected before item()")

    return text


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply stable AyuGram Ghost v0.2 to Telegram-iOS")
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--no-ui", action="store_true")
    args = parser.parse_args()

    root = Path(args.repo).expanduser().resolve()
    if not (root / "submodules" / "TelegramCore").exists():
        die(f"'{root}' is not TelegramMessenger/Telegram-iOS")

    here = Path(__file__).resolve().parent
    payload = here / "payload" / "AyuRuntimeSettings.swift"
    target = root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.read_text(encoding="utf-8") != payload.read_text(encoding="utf-8"):
        if target.exists():
            backup(target)
        shutil.copy2(payload, target)
        print(f"[ayu-v02] installed runtime settings: {target}")

    state = root / "submodules/TelegramCore/Sources/State"
    patch_file(state / "ManagedAccountPresence.swift", patch_presence)
    patch_file(state / "ManagedLocalInputActivities.swift", patch_typing)
    patch_file(state / "SynchronizePeerReadState.swift", patch_read_state)
    patch_file(state / "ManagedSynchronizeViewStoriesOperations.swift", patch_stories)

    if not args.no_ui:
        patch_file(root / "submodules/DebugSettingsUI/Sources/DebugController.swift", patch_debug_ui)

    print("[ayu-v02] DONE")
    print("[ayu-v02] Ghost defaults OFF. Open Telegram Debug -> AyuGram Settings to enable it.")


if __name__ == "__main__":
    main()
