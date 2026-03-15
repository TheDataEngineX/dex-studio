"""DEX Studio UI theme and shared styles.

Centralises colour palette, typography, and recurring CSS so that
all pages render consistently.
"""

from __future__ import annotations

from string import Template

__all__ = [
    "COLORS",
    "apply_global_styles",
]

# -- Colour palette (dark-first, inspired by DEX brand) -------------------

COLORS = {
    "bg_primary": "#0f1117",
    "bg_secondary": "#1a1d27",
    "bg_card": "#1e2130",
    "bg_hover": "#252838",
    "accent": "#6366f1",  # indigo-500
    "accent_light": "#818cf8",  # indigo-400
    "accent_muted": "#4f46e5",  # indigo-600
    "success": "#22c55e",
    "warning": "#f59e0b",
    "error": "#ef4444",
    "text_primary": "#f1f5f9",
    "text_secondary": "#94a3b8",
    "text_muted": "#64748b",
    "border": "#2e3347",
    "divider": "#313652",
}

# -- Global CSS injected once at app startup ------------------------------

_GLOBAL_CSS = Template("""
:root {
    --bg-primary: $bg_primary;
    --bg-secondary: $bg_secondary;
    --bg-card: $bg_card;
    --accent: $accent;
    --accent-light: $accent_light;
    --success: $success;
    --warning: $warning;
    --error: $error;
    --text-primary: $text_primary;
    --text-secondary: $text_secondary;
    --text-muted: $text_muted;
    --border: $border;
}

body {
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
}

.nicegui-content {
    background-color: var(--bg-primary) !important;
}

/* Card styling */
.dex-card {
    background-color: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.25rem;
    transition: border-color 0.2s ease;
}
.dex-card:hover {
    border-color: var(--accent);
}

/* Status indicators */
.status-healthy { color: var(--success); }
.status-degraded { color: var(--warning); }
.status-unhealthy { color: var(--error); }

/* Section headers */
.section-title {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    margin-bottom: 0.5rem;
}

/* Sidebar */
.sidebar-nav {
    background-color: var(--bg-secondary);
    border-right: 1px solid var(--border);
    height: 100vh;
    padding: 1rem 0;
}
.sidebar-link {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.6rem 1.25rem;
    color: var(--text-secondary);
    text-decoration: none;
    font-size: 0.875rem;
    transition: all 0.15s ease;
    border-left: 3px solid transparent;
}
.sidebar-link:hover {
    color: var(--text-primary);
    background-color: var(--bg-card);
}
.sidebar-link.active {
    color: var(--accent-light);
    background-color: var(--bg-card);
    border-left-color: var(--accent);
}

/* Metric cards */
.metric-value {
    font-size: 2rem;
    font-weight: 700;
    line-height: 1;
    color: var(--text-primary);
}
.metric-label {
    font-size: 0.8rem;
    color: var(--text-muted);
    margin-top: 0.25rem;
}
""").substitute(COLORS)


def apply_global_styles() -> None:
    """Inject global CSS into the current NiceGUI page."""
    from nicegui import ui

    ui.add_css(_GLOBAL_CSS)
