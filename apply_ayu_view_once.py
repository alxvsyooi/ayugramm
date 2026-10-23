#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: anchor not found")
    return text.replace(old, new, 1)


def patch_runtime(path: Path) -> None:
    text = path.read_text()

    text = replace_once(
        text,
        "    private static let manualReadPeers = Atomic<Set<Int64>>(value: Set())\n",
        "    private static let manualReadPeers = Atomic<Set<Int64>>(value: Set())\n\n"
        "    // View-once media preservation is always enabled and intentionally has no setting.\n"
        "    // A one-shot allowance is reserved for the explicit manual 'Сжечь' action.\n"
        "    private static let manualBurnMessages = Atomic<Set<String>>(value: Set())\n",
        "view-once-runtime-state",
    )

    anchor = "    public static var suppressReadMessages: Bool {\n"
    helpers = r'''    private static func burnMessageKey(_ id: MessageId) -> String {
        return "\(id.peerId.namespace):\(id.peerId.id._internalGetInt64Value()):\(id.namespace):\(id.id)"
    }

    public static func allowNextViewOnceBurn(_ id: MessageId) {
        let key = burnMessageKey(id)
        _ = manualBurnMessages.modify { current in
            var current = current
            current.insert(key)
            return current
        }
    }

    public static func consumeViewOnceBurnAllowance(_ id: MessageId) {
        let key = burnMessageKey(id)
        _ = manualBurnMessages.modify { current in
            var current = current
            current.remove(key)
            return current
        }
    }

    public static func shouldPreserveViewOnce(message: Message) -> Bool {
        let supportedMedia = message.media.contains { media in
            if media is TelegramMediaImage {
                return true
            }
            if let file = media as? TelegramMediaFile {
                return file.isVoice || file.isInstantVideo
            }
            return false
        }
        guard supportedMedia else {
            return false
        }

        let isViewOnce = message.attributes.contains { attribute in
            if let attribute = attribute as? AutoremoveTimeoutMessageAttribute {
                return attribute.timeout == viewOnceTimeout
            }
            if let attribute = attribute as? AutoclearTimeoutMessageAttribute {
                return attribute.timeout == viewOnceTimeout
            }
            return false
        }
        guard isViewOnce else {
            return false
        }

        let key = burnMessageKey(message.id)
        return manualBurnMessages.with { !$0.contains(key) }
    }

'''
    text = replace_once(text, anchor, helpers + anchor, "view-once-runtime-helpers")
    path.write_text(text)


def patch_consume(path: Path) -> None:
    text = path.read_text()
    old = """        if let message = transaction.getMessage(messageId), message.flags.contains(.Incoming) {\n            var updateMessage = false\n"""
    new = """        if let message = transaction.getMessage(messageId), message.flags.contains(.Incoming) {\n            // AYU_IOS_PATCH_v0_3: opening incoming view-once photo / voice / video-message\n            // must not consume it locally, start its destruction countdown, or send\n            // the consume operation to Telegram. The explicit 'Сжечь' action gets\n            // one allowance and then normal Telegram consumption runs unchanged.\n            if AyuRuntimeSettings.shouldPreserveViewOnce(message: message) {\n                return\n            }\n            AyuRuntimeSettings.consumeViewOnceBurnAllowance(message.id)\n\n            var updateMessage = false\n"""
    text = replace_once(text, old, new, "view-once-consume-guard")
    path.write_text(text)


def patch_open_view_once_ui(path: Path) -> None:
    text = path.read_text()
    text = replace_once(
        text,
        "        let isIncoming = message.effectivelyIncoming(self.context.account.peerId)\n        \n",
        "",
        "view-once-unused-incoming",
    )
    old = """                    closeActionTitle: isIncoming ? self.presentationData.strings.Chat_PlayOnceMesasgeCloseAndDelete : self.presentationData.strings.Chat_PlayOnceMesasgeClose,\n"""
    new = """                    // AYU_IOS_PATCH_v0_3: incoming view-once media is preserved,\n                    // so closing the viewer must not claim it will be deleted.\n                    closeActionTitle: self.presentationData.strings.Chat_PlayOnceMesasgeClose,\n"""
    text = replace_once(text, old, new, "view-once-close-title")
    path.write_text(text)


def patch_view_once_tooltip(path: Path) -> None:
    text = path.read_text()
    old_video = """                if isVideo {\n                    tooltipText = presentationData.strings.Chat_PlayOnceVideoMessageTooltip\n                } else {\n                    tooltipText = presentationData.strings.Chat_PlayOnceVoiceMessageTooltip\n                }\n"""
    new_video = """                if isVideo {\n                    // AYU_IOS_PATCH_v0_3: preserved incoming one-time media stays available.\n                    tooltipText = \"Сообщение не исчезнет после просмотра\"\n                } else {\n                    tooltipText = \"Сообщение не исчезнет после просмотра\"\n                }\n"""
    text = replace_once(text, old_video, new_video, "view-once-incoming-tooltip")
    path.write_text(text)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_view_once.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    patch_runtime(root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift")
    patch_consume(root / "submodules/TelegramCore/Sources/TelegramEngine/Messages/MarkMessageContentAsConsumedInteractively.swift")
    patch_open_view_once_ui(root / "submodules/TelegramUI/Sources/Chat/ChatControllerOpenViewOnceMediaMessage.swift")
    patch_view_once_tooltip(root / "submodules/TelegramUI/Sources/ChatMessageContextControllerContentSource.swift")
    print("Ayu view-once preserve patch applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
