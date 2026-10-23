#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import apply_ayu_v03 as base


def patch_read_state(text: str) -> str:
    old = """func synchronizePeerReadState(network: Network, postbox: Postbox, stateManager: AccountStateManager, peerId: PeerId, push: Bool, validate: Bool) -> Signal<Never, PeerReadStateValidationError> {\n    var signal: Signal<Never, PeerReadStateValidationError> = .complete()\n    if push {\n        signal = signal\n        |> then(pushPeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n    if validate {\n        signal = signal\n        |> then(validatePeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n    return signal\n}"""
    new = """func synchronizePeerReadState(network: Network, postbox: Postbox, stateManager: AccountStateManager, peerId: PeerId, push: Bool, validate: Bool) -> Signal<Never, PeerReadStateValidationError> {\n    // AYU_IOS_PATCH_v0_3: Ghost-only read suppression. Confirm the local\n    // synchronization operation instead of sending a read receipt.\n    if AyuRuntimeSettings.shouldSuppressRead(peerId: peerId) {\n        return postbox.transaction { transaction -> Void in\n            transaction.confirmSynchronizedIncomingReadState(peerId)\n        }\n        |> castError(PeerReadStateValidationError.self)\n        |> ignoreValues\n    }\n\n    AyuRuntimeSettings.consumeManualReadAllowance(peerId: peerId)\n\n    var signal: Signal<Never, PeerReadStateValidationError> = .complete()\n    if push {\n        signal = signal\n        |> then(pushPeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n    if validate {\n        signal = signal\n        |> then(validatePeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n    return signal\n}"""
    return base.replace_once(text, old, new, "ghost-only-read")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply minimal AyuGram Ghost-only patch")
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.repo).expanduser().resolve()
    if not (root / "submodules" / "TelegramCore").exists():
        base.die(f"'{root}' is not TelegramMessenger/Telegram-iOS")

    here = Path(__file__).resolve().parent
    state = root / "submodules/TelegramCore/Sources/State"

    base.install_payload(here / "payload" / "AyuRuntimeSettingsGhostOnly.swift", state / "AyuRuntimeSettings.swift", "Ghost-only runtime settings")
    base.install_payload(here / "payload" / "AyuGhostLastSeen.swift", state / "AyuGhostLastSeen.swift", "Ghost last-seen state")
    base.install_payload(here / "payload" / "AyuSettingsControllerGhostOnly.swift", root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift", "Ghost-only Ayu settings")

    base.patch_file(state / "ManagedAccountPresence.swift", base.patch_presence)
    base.patch_file(state / "ManagedLocalInputActivities.swift", base.patch_typing)
    base.patch_file(state / "SynchronizePeerReadState.swift", patch_read_state)
    base.patch_file(state / "ManagedSynchronizeViewStoriesOperations.swift", base.patch_stories)
    base.patch_file(root / "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift", base.patch_online_pulse)
    base.patch_file(root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoSettingsItems.swift", base.patch_native_settings)
    base.patch_file(root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoData.swift", base.patch_own_profile_last_seen)

    print("[ayu-ghost-only] stock Telegram UI/theme; Ghost hooks only")


if __name__ == "__main__":
    main()
