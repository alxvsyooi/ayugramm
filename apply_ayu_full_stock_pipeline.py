#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PATCHERS = (
    "apply_ayu_v03_ui_v2.py",
    "apply_ayu_profile_cache.py",
    "apply_ayu_view_once.py",
    "apply_ayu_view_once_durable.py",
    "apply_ayu_view_once_burn.py",
    "apply_ayu_stock_ui_guard.py",
    "apply_ayu_deleted_alpha.py",
    "apply_ayu_deleted_viewer_safety.py",
    "apply_ayu_deleted_background.py",
    "apply_ayu_deleted_marker.py",
    "apply_ayu_deleted_realtime.py",
    "apply_ayu_manual_read_fix.py",
    "apply_ayu_send_read.py",
    "apply_ayu_behavior_anchor_compat.py",
    "apply_ayu_behavior_hotfix.py",
    "apply_ayu_deleted_archive.py",
    "apply_ayu_files_visibility.py",
    "apply_ayu_presence_toggle_hotfix.py",
    "apply_ayu_settings_categories.py",
    "apply_ayu_spy_settings.py",
    "apply_ayu_chat_camera_ghost.py",
    "apply_ayu_avatar_rounding.py",
    "apply_ayu_chat_avatar_rounding.py",
    "apply_ayu_avatar_rounding_v3.py",
    "apply_ayu_chat_list_appearance.py",
    "apply_ayu_spy_edit_history.py",
    "apply_ayu_spy_read_dates.py",
    "apply_ayu_spy_details.py",
    "apply_ayu_spy_content_read_dates.py",
    "apply_ayu_branding_only.py",
    "apply_ayu_app_icon.py",
    "apply_ayu_ios27_color_compat.py",
    "apply_ayu_extera_essentials.py",
    "apply_ayu_peer_id_compile_fix.py",
)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_full_stock_pipeline.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    here = Path(__file__).resolve().parent
    for name in PATCHERS:
        subprocess.run([sys.executable, str(here / name), str(root)], check=True)

    # Theme selection, family routing and native glass stay byte-for-byte
    # upstream. Ayu must not touch theme routing at all: day/night switching,
    # custom themes and wallpapers behave exactly like stock Telegram.
    stock_paths = (
        "submodules/SettingsUI/Sources/Themes/ThemeSettingsController.swift",
        "submodules/TelegramUI/Components/LiquidLens/Sources/LiquidLensView.swift",
        "submodules/TelegramUI/Components/GlassBackgroundComponent/Sources/GlassBackgroundComponent.swift",
        "submodules/TelegramUI/Components/Chat/ChatMessageReplyInfoNode/Sources/ChatMessageReplyInfoNode.swift",
        "submodules/TelegramUI/Sources/ChatPinnedMessageTitlePanelNode.swift",
        "submodules/TelegramUI/Components/PeerInfo/PeerInfoVisualMediaPaneNode/Sources/PeerInfoGiftsPaneNode.swift",
        "submodules/TelegramPresentationData/Sources/PresentationData.swift",
        "submodules/TelegramUI/Sources/SharedAccountContext.swift",
    )
    for relative in stock_paths:
        subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", relative], cwd=root, check=True)

    print("[ayu-full-stock] Deleted/ViewOnce/Spy/Ghost restored; Telegram theme family, wallpaper and glass routing preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
