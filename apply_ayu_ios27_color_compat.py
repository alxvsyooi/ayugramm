#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


TRAIT_MARK = "AYU_IOS27_UNSPECIFIED_TRAIT_COMPAT_v1"
ALPHA_MARK = "AYU_RGB24_THEME_COLOR_COMPAT_v1"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def patch_trait(root: Path) -> None:
    path = root / "submodules/Display/Source/NativeWindowHostView.swift"
    text = path.read_text(encoding="utf-8")
    if TRAIT_MARK in text:
        return

    old = """    override func traitCollectionDidChange(_ previousTraitCollection: UITraitCollection?) {
        if #available(iOS 12.0, *) {
            self._systemUserInterfaceStyle.set(WindowUserInterfaceStyle(style: self.traitCollection.userInterfaceStyle))
        }
    }
"""
    new = f"""    override func traitCollectionDidChange(_ previousTraitCollection: UITraitCollection?) {{
        super.traitCollectionDidChange(previousTraitCollection)
        // {TRAIT_MARK}
        // iOS 27 can briefly report .unspecified while switching appearance.
        // It is not a light-theme selection, so do not publish it as one.
        let style = self.traitCollection.userInterfaceStyle
        if style == .light || style == .dark {{
            self._systemUserInterfaceStyle.set(WindowUserInterfaceStyle(style: style))
        }}
    }}
"""
    text = one(text, old, new, "trait update")

    old_init = """        if #available(iOS 13.0, *) {
            self._systemUserInterfaceStyle.set(WindowUserInterfaceStyle(style: self.traitCollection.userInterfaceStyle))
        } else {
            self._systemUserInterfaceStyle.set(.light)
        }
"""
    new_init = """        if #available(iOS 13.0, *) {
            let style = self.traitCollection.userInterfaceStyle
            if style == .light || style == .dark {
                self._systemUserInterfaceStyle.set(WindowUserInterfaceStyle(style: style))
            }
        } else {
            self._systemUserInterfaceStyle.set(.light)
        }
"""
    text = one(text, old_init, new_init, "trait initialization")
    path.write_text(text, encoding="utf-8")


def patch_alpha(root: Path) -> None:
    path = root / "submodules/TelegramPresentationData/Sources/MakePresentationTheme.swift"
    text = path.read_text(encoding="utf-8")
    if ALPHA_MARK in text:
        return

    anchor = "import TelegramCore\n\n"
    helper = f"""import TelegramCore

// {ALPHA_MARK}
// Cloud settings may contain RGB24 in an ARGB field. Only alpha-zero values are
// normalized to opaque; every valid ARGB color remains unchanged.
private func ayuOpaqueThemeColor(_ value: UInt32) -> UIColor {{
    if value & 0xff000000 == 0 {{
        return UIColor(rgb: value)
    }} else {{
        return UIColor(argb: value)
    }}
}}

"""
    text = one(text, anchor, helper, "color helper")

    accent_count = text.count("UIColor(argb: settings.accentColor)")
    outgoing_count = text.count("UIColor(argb: $0)")
    if accent_count != 4 or outgoing_count != 4:
        raise RuntimeError(f"theme color anchors: expected 4+4, found {accent_count}+{outgoing_count}")
    text = text.replace("UIColor(argb: settings.accentColor)", "ayuOpaqueThemeColor(settings.accentColor)")
    text = text.replace("UIColor(argb: $0)", "ayuOpaqueThemeColor($0)")
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_ios27_color_compat.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    patch_trait(root)
    patch_alpha(root)

    native = (root / "submodules/Display/Source/NativeWindowHostView.swift").read_text(encoding="utf-8")
    make = (root / "submodules/TelegramPresentationData/Sources/MakePresentationTheme.swift").read_text(encoding="utf-8")
    for required, value in (
        (TRAIT_MARK, native),
        ("if style == .light || style == .dark", native),
        (ALPHA_MARK, make),
        ("ayuOpaqueThemeColor(settings.accentColor)", make),
    ):
        if required not in value:
            raise RuntimeError(f"compatibility patch incomplete: {required}")

    forbidden = (
        "updatePresentationThemeSettingsInteractively",
        "automaticThemeSwitchSetting",
        "themePreferredBaseTheme",
        "overrideUserInterfaceStyle",
    )
    combined = native + make
    for value in forbidden:
        if value in combined:
            raise RuntimeError(f"theme selection interference is forbidden: {value}")

    print("[ayu-ios27-color-compat] ignores transient unspecified traits and normalizes only alpha-zero RGB24; no theme selection writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

