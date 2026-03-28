"""DEX Studio theme — dark/light palettes with CSS custom properties."""

from __future__ import annotations

__all__ = ["COLORS", "LIGHT_COLORS", "get_colors", "apply_global_styles"]

# Dark palette (default)
COLORS: dict[str, str] = {
    "bg_primary": "#0f1117",
    "bg_secondary": "#1a1d27",
    "bg_sidebar": "#13151f",
    "bg_hover": "#1e2235",
    "bg_card": "#1e2130",
    "accent": "#6366f1",
    "accent_light": "#a5b4fc",
    "accent_muted": "#4f46e5",
    "text_primary": "#f1f5f9",
    "text_muted": "#94a3b8",
    "text_dim": "#64748b",
    "text_faint": "#475569",
    "border": "#2d3348",
    "divider": "#1e2235",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "error": "#ef4444",
}

# Light palette
LIGHT_COLORS: dict[str, str] = {
    "bg_primary": "#f8fafc",
    "bg_secondary": "#ffffff",
    "bg_sidebar": "#f1f5f9",
    "bg_hover": "#e2e8f0",
    "bg_card": "#ffffff",
    "accent": "#6366f1",
    "accent_light": "#4f46e5",
    "accent_muted": "#818cf8",
    "text_primary": "#0f172a",
    "text_muted": "#475569",
    "text_dim": "#94a3b8",
    "text_faint": "#cbd5e1",
    "border": "#e2e8f0",
    "divider": "#f1f5f9",
    "success": "#16a34a",
    "warning": "#d97706",
    "error": "#dc2626",
}


def get_colors(theme: str = "dark") -> dict[str, str]:
    """Return the color palette for the given theme name."""
    return LIGHT_COLORS if theme == "light" else COLORS


def apply_global_styles(theme: str = "dark") -> None:
    """Inject global CSS custom properties for the given theme."""
    from nicegui import ui

    palette = get_colors(theme)
    css_vars = "\n".join(f"  --{k.replace('_', '-')}: {v};" for k, v in palette.items())
    ui.add_css(f"""
        :root {{
            {css_vars}
        }}
        body {{
            background: var(--bg-primary);
            color: var(--text-primary);
            font-family: system-ui, -apple-system, sans-serif;
        }}
        .nicegui-content {{
            padding: 0;
        }}
        .dex-card {{
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
        }}
        .dex-card:hover {{
            border-color: var(--accent);
        }}
        .section-title {{
            font-size: 10px;
            text-transform: uppercase;
            color: var(--text-faint);
            letter-spacing: 0.05em;
        }}
    """)
