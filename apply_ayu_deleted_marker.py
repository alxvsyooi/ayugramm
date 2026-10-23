#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


MARK = "AYU_DELETED_TIMESTAMP_MARKER_v1"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_deleted_marker.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    status_root = root / "submodules/TelegramUI/Components/Chat/ChatMessageDateAndStatusNode/Sources"

    timestamp_path = status_root / "StringForMessageTimestampStatus.swift"
    timestamp = timestamp_path.read_text(encoding="utf-8")
    if MARK not in timestamp:
        old = """    return dateText
}
"""
        new = f"""    // {MARK}
    return AyuRuntimeSettings.decorateTimestamp(dateText, messageId: message.id)
}}
"""
        timestamp = one(timestamp, old, new, "deleted timestamp text")
        timestamp_path.write_text(timestamp, encoding="utf-8")

    node_path = status_root / "ChatMessageDateAndStatusNode.swift"
    node = node_path.read_text(encoding="utf-8")
    if MARK not in node:
        old = """            let dateFont = Font.regular(floor(arguments.presentationData.fontSize.baseDisplaySize * 11.0 / 17.0))
            let (date, dateApply) = dateLayout(TextNodeLayoutArguments(attributedString: NSAttributedString(string: updatedDateText, font: dateFont, textColor: dateColor), backgroundColor: nil, maximumNumberOfLines: 1, truncationType: .middle, constrainedSize: arguments.constrainedSize, alignment: .natural, cutout: nil, insets: UIEdgeInsets()))
"""
        new = f"""            let dateFont = Font.regular(floor(arguments.presentationData.fontSize.baseDisplaySize * 11.0 / 17.0))
            // {MARK}: preserve Telegram's dateColor and tint only the marker.
            let ayuDateText = NSMutableAttributedString(string: updatedDateText, font: dateFont, textColor: dateColor)
            if AyuRuntimeSettings.isDeletedTimestampText(updatedDateText) {{
                let markerPrefix = AyuRuntimeSettings.deletedMarkerPrefix + " "
                let markerLength = (markerPrefix as NSString).length
                if markerLength <= ayuDateText.length {{
                    let markerColor: UIColor
                    switch AyuDeletedMarkerColor(rawValue: AyuRuntimeSettings.snapshot.deletedMarkerColor) ?? .telegram {{
                    case .red: markerColor = UIColor.systemRed
                    case .orange: markerColor = UIColor.systemOrange
                    case .gray: markerColor = UIColor.systemGray
                    case .purple: markerColor = UIColor.systemPurple
                    case .pink: markerColor = UIColor.systemPink
                    case .magenta: markerColor = UIColor(red: 0.86, green: 0.12, blue: 0.46, alpha: 1.0)
                    case .indigo: markerColor = UIColor.systemIndigo
                    case .blue: markerColor = UIColor.systemBlue
                    case .telegram: markerColor = dateColor
                    }}
                    ayuDateText.addAttribute(.foregroundColor, value: markerColor, range: NSRange(location: 0, length: markerLength))
                }}
            }}
            let (date, dateApply) = dateLayout(TextNodeLayoutArguments(attributedString: ayuDateText, backgroundColor: nil, maximumNumberOfLines: 1, truncationType: .middle, constrainedSize: arguments.constrainedSize, alignment: .natural, cutout: nil, insets: UIEdgeInsets()))
"""
        node = one(node, old, new, "deleted marker-only color")
        node_path.write_text(node, encoding="utf-8")

    if MARK not in timestamp_path.read_text(encoding="utf-8") or MARK not in node_path.read_text(encoding="utf-8"):
        raise RuntimeError("deleted timestamp marker is incomplete")

    print("[ayu-deleted-marker] marker restored without changing Telegram date/theme colors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
