#!/usr/bin/env python3
from __future__ import annotations

import apply_ayu_v03_fixed as fixed

base = fixed.base


def patch_read_state(text: str) -> str:
    """Suppress read receipts by consuming the Postbox sync operation, not by
    returning an immediate .single(readState).

    The old v0.2/v0.3 low-level shortcut completed synchronously while the
    PeerReadStateSynchronizationOperation was still visible. Telegram's
    ManagedSynchronizePeerReadStates completion handler immediately calls
    update() again, which could recurse until the thread hit its stack guard.
    """
    old = """func synchronizePeerReadState(network: Network, postbox: Postbox, stateManager: AccountStateManager, peerId: PeerId, push: Bool, validate: Bool) -> Signal<Never, PeerReadStateValidationError> {\n    var signal: Signal<Never, PeerReadStateValidationError> = .complete()\n    if push {\n        signal = signal\n        |> then(pushPeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n    if validate {\n        signal = signal\n        |> then(validatePeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n    return signal\n}"""

    new = """func synchronizePeerReadState(network: Network, postbox: Postbox, stateManager: AccountStateManager, peerId: PeerId, push: Bool, validate: Bool) -> Signal<Never, PeerReadStateValidationError> {\n    // AYU_IOS_PATCH_v0_3: Ghost read suppression must remove the Postbox\n    // synchronization operation before completing. Returning .single(readState)\n    // here/inside pushPeerReadState completes synchronously while the operation is\n    // still visible, and ManagedSynchronizePeerReadStates immediately calls update()\n    // again -> unbounded SwiftSignalKit recursion / stack overflow.\n    if AyuRuntimeSettings.suppressReadMessages {\n        return postbox.transaction { transaction -> Void in\n            transaction.confirmSynchronizedIncomingReadState(peerId)\n        }\n        |> castError(PeerReadStateValidationError.self)\n        |> ignoreValues\n    }\n\n    var signal: Signal<Never, PeerReadStateValidationError> = .complete()\n    if push {\n        signal = signal\n        |> then(pushPeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n    if validate {\n        signal = signal\n        |> then(validatePeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n    return signal\n}"""

    return base.replace_once(text, old, new, "read-crashfix-transaction")


# Keep the corrected deleted-message patch from apply_ayu_v03_fixed.py, but
# replace the old synchronous Ghost read shortcut with the transaction-safe one.
base.patch_read_state = patch_read_state


if __name__ == "__main__":
    base.main()
