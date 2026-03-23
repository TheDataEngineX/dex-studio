# tests/unit/test_theme.py
from __future__ import annotations

from dex_studio.theme import COLORS


class TestTheme:
    def test_colors_has_required_keys(self) -> None:
        required = [
            "bg_primary",
            "bg_secondary",
            "bg_sidebar",
            "bg_hover",
            "accent",
            "accent_light",
            "text_primary",
            "text_muted",
            "text_dim",
            "text_faint",
            "border",
            "success",
            "warning",
            "error",
        ]
        for key in required:
            assert key in COLORS, f"Missing color: {key}"

    def test_colors_are_hex(self) -> None:
        for key, val in COLORS.items():
            assert val.startswith("#"), f"{key} is not hex: {val}"
            assert len(val) == 7, f"{key} is not 6-digit hex: {val}"
