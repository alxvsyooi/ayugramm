#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

MARK = "AYU_VIEW_ONCE_DURABLE_v0_3"


def die(message: str) -> None:
    print(f"[ayu-view-once-durable] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Persist and restore preserved incoming view-once media outside normal MediaBox cleanup")
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.repo).expanduser().resolve()
    path = root / "submodules/TelegramCore/Sources/TelegramEngine/Messages/MarkMessageContentAsConsumedInteractively.swift"
    if not path.exists():
        die(f"missing file: {path}")

    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print(f"[ayu-view-once-durable] already patched: {path}")
        return

    function_anchor = "func _internal_markMessageContentAsConsumedInteractively(postbox: Postbox, messageId: MessageId) -> Signal<Void, NoError> {\n"
    helpers = r'''// AYU_VIEW_ONCE_DURABLE_v0_3
// Keep a durable copy outside MediaBox's cache/size-cleanup root. This is only
// touched when an incoming view-once item is actually opened or explicitly
// burned; there is no polling and no render-path work.
private func ayuViewOnceResource(_ message: Message) -> MediaResource? {
    for media in message.media {
        if let image = media as? TelegramMediaImage {
            return largestImageRepresentation(image.representations)?.resource
        } else if let file = media as? TelegramMediaFile, file.isVoice || file.isInstantVideo {
            return file.resource
        }
    }
    return nil
}

private func ayuViewOnceDurablePath(postbox: Postbox, resource: MediaResource) -> String {
    let mediaParent = (postbox.mediaBox.basePath as NSString).deletingLastPathComponent
    let directory = mediaParent + "/ayu-view-once"
    let _ = try? FileManager.default.createDirectory(atPath: directory, withIntermediateDirectories: true)
    let safeId = resource.id.stringRepresentation
        .replacingOccurrences(of: "/", with: "_")
        .replacingOccurrences(of: ":", with: "_")
    return directory + "/" + safeId
}

private func ayuRestoreDurableViewOnceMedia(postbox: Postbox, message: Message) {
    guard let resource = ayuViewOnceResource(message) else {
        return
    }
    let durable = ayuViewOnceDurablePath(postbox: postbox, resource: resource)
    guard FileManager.default.fileExists(atPath: durable) else {
        return
    }

    let mediaPaths = postbox.mediaBox.storePathsForId(resource.id)
    if FileManager.default.fileExists(atPath: mediaPaths.complete) {
        return
    }

    let parent = (mediaPaths.complete as NSString).deletingLastPathComponent
    let _ = try? FileManager.default.createDirectory(atPath: parent, withIntermediateDirectories: true)
    let temp = mediaPaths.complete + ".ayu-restore-" + UUID().uuidString
    do {
        try FileManager.default.copyItem(atPath: durable, toPath: temp)
        if FileManager.default.fileExists(atPath: mediaPaths.complete) {
            try? FileManager.default.removeItem(atPath: temp)
        } else {
            try FileManager.default.moveItem(atPath: temp, toPath: mediaPaths.complete)
        }
    } catch {
        try? FileManager.default.removeItem(atPath: temp)
    }
}

private func ayuPersistViewOnceMedia(postbox: Postbox, message: Message) {
    guard let resource = ayuViewOnceResource(message) else {
        return
    }
    let destination = ayuViewOnceDurablePath(postbox: postbox, resource: resource)
    if FileManager.default.fileExists(atPath: destination) {
        return
    }

    let _ = (postbox.mediaBox.resourceData(resource)
    |> filter { $0.complete }
    |> take(1)
    |> deliverOn(Queue.concurrentDefaultQueue())).startStandalone(next: { data in
        guard !FileManager.default.fileExists(atPath: destination) else {
            return
        }
        let temp = destination + ".tmp-" + UUID().uuidString
        do {
            try FileManager.default.copyItem(atPath: data.path, toPath: temp)
            if FileManager.default.fileExists(atPath: destination) {
                try? FileManager.default.removeItem(atPath: temp)
            } else {
                try FileManager.default.moveItem(atPath: temp, toPath: destination)
            }
        } catch {
            try? FileManager.default.removeItem(atPath: temp)
        }
    })
}

private func ayuRemoveDurableViewOnceMedia(postbox: Postbox, message: Message) {
    guard let resource = ayuViewOnceResource(message) else {
        return
    }
    let path = ayuViewOnceDurablePath(postbox: postbox, resource: resource)
    if FileManager.default.fileExists(atPath: path) {
        try? FileManager.default.removeItem(atPath: path)
    }
}

'''

    if function_anchor not in text:
        die("consume function anchor not found")
    text = text.replace(function_anchor, helpers + function_anchor, 1)

    old = """            if AyuRuntimeSettings.shouldPreserveViewOnce(message: message) {\n                return\n            }\n            AyuRuntimeSettings.consumeViewOnceBurnAllowance(message.id)\n"""
    new = """            if AyuRuntimeSettings.shouldPreserveViewOnce(message: message) {\n                // Restore first if Telegram's normal MediaBox cache was cleaned,\n                // then refresh the durable copy once the stock resource is complete.\n                ayuRestoreDurableViewOnceMedia(postbox: postbox, message: message)\n                ayuPersistViewOnceMedia(postbox: postbox, message: message)\n                return\n            }\n            // Reaching this branch for a preserved view-once item means the explicit\n            // manual Burn allowance was armed. Remove Ayu's durable copy and let\n            // Telegram's stock consume/destruction path continue unchanged.\n            ayuRemoveDurableViewOnceMedia(postbox: postbox, message: message)\n            AyuRuntimeSettings.consumeViewOnceBurnAllowance(message.id)\n"""

    count = text.count(old)
    if count != 1:
        die(f"view-once preserve anchor expected exactly once, found {count}")
    text = text.replace(old, new, 1)

    path.write_text(text, encoding="utf-8")
    print(f"[ayu-view-once-durable] patched: {path}")


if __name__ == "__main__":
    main()
