"""DEX Studio theme — dark-first palette with CSS custom properties."""

from __future__ import annotations

__all__ = ["COLORS", "apply_global_styles"]

COLORS: dict[str, str] = {
    # Backgrounds
    "bg_primary": "#0f1117",
    "bg_secondary": "#1a1d27",
    "bg_sidebar": "#13151f",
    "bg_hover": "#1e2235",
    "bg_card": "#1e2130",
    # Accent
    "accent": "#6366f1",
    "accent_light": "#a5b4fc",
    "accent_muted": "#4f46e5",
    # Text
    "text_primary": "#f1f5f9",
    "text_muted": "#94a3b8",
    "text_dim": "#64748b",
    "text_faint": "#475569",
    # Borders
    "border": "#2d3348",
    "divider": "#1e2235",
    # Status
    "success": "#22c55e",
    "warning": "#f59e0b",
    "error": "#ef4444",
}


def apply_global_styles() -> None:
    """Inject global CSS with theme custom properties."""
    from nicegui import ui

    css_vars = "\n".join(f"  --{k.replace('_', '-')}: {v};" for k, v in COLORS.items())
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
