"""Theme colors for DEX Studio (snake_case keys for test compatibility)."""

from __future__ import annotations

from dex_studio.design_tokens import COLORS_DARK

# Map kebab-case keys from design_tokens to snake_case keys expected by tests
COLORS: dict[str, str] = {
    "bg_primary": COLORS_DARK["bg-primary"],
    "bg_secondary": COLORS_DARK["bg-elevated"],
    "bg_sidebar": COLORS_DARK["bg-overlay"],
    "bg_hover": COLORS_DARK["bg-hover"],
    "accent": COLORS_DARK["accent"],
    "accent_light": COLORS_DARK["accent-hover"],
    "text_primary": COLORS_DARK["text-primary"],
    "text_muted": COLORS_DARK["text-secondary"],
    "text_dim": COLORS_DARK["text-tertiary"],
    "text_faint": COLORS_DARK["text-faint"],
    "border": COLORS_DARK["border-subtle"],
    "success": COLORS_DARK["success"],
    "warning": COLORS_DARK["warning"],
    "error": COLORS_DARK["error"],
}
