"""Design tokens — Apple-quality CSS variables for colors, typography, spacing, motion."""

from __future__ import annotations

__all__ = [
    "DESIGN_TOKENS",
    "LIGHT_TOKENS",
    "get_motion_css",
]

# Color tokens
COLORS_DARK = {
    "bg-primary": "#0f172a",
    "bg-elevated": "#1e293b",
    "bg-overlay": "#020617",
    "bg-hover": "#334155",
    "bg-card": "#1e293b",
    "accent": "#6366f1",
    "accent-hover": "#818cf8",
    "accent-active": "#4f46e5",
    "text-primary": "#f1f5f9",
    "text-secondary": "#94a3b8",
    "text-tertiary": "#64748b",
    "text-faint": "#475569",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "error": "#ef4444",
    "border-subtle": "#334155",
    "border-default": "#1e293b",
}

COLORS_LIGHT = {
    "bg-primary": "#f8fafc",
    "bg-elevated": "#f1f5f9",
    "bg-overlay": "#e2e8f0",
    "bg-hover": "#e2e8f0",
    "bg-card": "#ffffff",
    "accent": "#6366f1",
    "accent-hover": "#818cf8",
    "accent-active": "#4f46e5",
    "text-primary": "#0f172a",
    "text-secondary": "#475569",
    "text-tertiary": "#94a3b8",
    "text-faint": "#cbd5e1",
    "success": "#16a34a",
    "warning": "#d97706",
    "error": "#dc2626",
    "border-subtle": "#e2e8f0",
    "border-default": "#f1f5f9",
}

# Motion tokens
MOTION = {
    "ease-out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
    "ease-in-out": "cubic-bezier(0.4, 0, 0.2, 1)",
    "ease-spring": "cubic-bezier(0.175, 0.885, 0.32, 1.275)",
    "duration-instant": "0ms",
    "duration-fast": "150ms",
    "duration-normal": "250ms",
    "duration-slow": "350ms",
}

# Shadow tokens
SHADOWS = {
    "shadow-sm": "0 1px 2px rgba(0, 0, 0, 0.05)",
    "shadow-md": "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)",
    "shadow-lg": "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)",
    "shadow-xl": "0 25px 50px -12px rgba(0, 0, 0, 0.25)",
}

# Typography scale
TYPOGRAPHY = {
    "text-xs": "11px",
    "text-sm": "13px",
    "text-base": "15px",
    "text-lg": "17px",
    "text-xl": "22px",
    "text-2xl": "28px",
}

# Spacing
SPACING = {
    "space-1": "4px",
    "space-2": "8px",
    "space-3": "12px",
    "space-4": "16px",
    "space-5": "20px",
    "space-6": "24px",
    "space-8": "32px",
    "space-10": "40px",
    "space-12": "48px",
}

DESIGN_TOKENS = {
    **COLORS_DARK,
    **MOTION,
    **SHADOWS,
    **TYPOGRAPHY,
    **SPACING,
}

LIGHT_TOKENS = {
    **COLORS_LIGHT,
    **MOTION,
    **SHADOWS,
    **TYPOGRAPHY,
    **SPACING,
}


def get_motion_css() -> str:
    """Return CSS for motion/animation."""
    return f"""
        :root {{
            --ease-out-expo: {MOTION["ease-out-expo"]};
            --ease-in-out: {MOTION["ease-in-out"]};
            --ease-spring: {MOTION["ease-spring"]};
            --duration-instant: {MOTION["duration-instant"]};
            --duration-fast: {MOTION["duration-fast"]};
            --duration-normal: {MOTION["duration-normal"]};
            --duration-slow: {MOTION["duration-slow"]};

            --shadow-sm: {SHADOWS["shadow-sm"]};
            --shadow-md: {SHADOWS["shadow-md"]};
            --shadow-lg: {SHADOWS["shadow-lg"]};
            --shadow-xl: {SHADOWS["shadow-xl"]};

            --text-xs: {TYPOGRAPHY["text-xs"]};
            --text-sm: {TYPOGRAPHY["text-sm"]};
            --text-base: {TYPOGRAPHY["text-base"]};
            --text-lg: {TYPOGRAPHY["text-lg"]};
            --text-xl: {TYPOGRAPHY["text-xl"]};
            --text-2xl: {TYPOGRAPHY["text-2xl"]};

            --space-1: {SPACING["space-1"]};
            --space-2: {SPACING["space-2"]};
            --space-3: {SPACING["space-3"]};
            --space-4: {SPACING["space-4"]};
            --space-5: {SPACING["space-5"]};
            --space-6: {SPACING["space-6"]};
            --space-8: {SPACING["space-8"]};
            --space-10: {SPACING["space-10"]};
            --space-12: {SPACING["space-12"]};
        }}

        .animate-fade-in {{
            animation: fadeIn var(--duration-normal) var(--ease-out-expo);
        }}

        .animate-slide-up {{
            animation: slideUp var(--duration-normal) var(--ease-out-expo);
        }}

        .animate-scale-in {{
            animation: scaleIn var(--duration-fast) var(--ease-spring);
        }}

        .animate-slide-in-right {{
            animation: slideInRight var(--duration-normal) var(--ease-out-expo);
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
        }}

        @keyframes slideUp {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        @keyframes scaleIn {{
            from {{ opacity: 0; transform: scale(0.95); }}
            to {{ opacity: 1; transform: scale(1); }}
        }}

        @keyframes slideInRight {{
            from {{ opacity: 0; transform: translateX(100px); }}
            to {{ opacity: 1; transform: translateX(0); }}
        }}

        @keyframes shimmer {{
            0% {{ background-position: 200% 0; }}
            100% {{ background-position: -200% 0; }}
        }}

        .btn-press:active {{
            transform: scale(0.97);
            transition: transform 100ms var(--ease-out-expo);
        }}

        .focus-ring:focus {{
            outline: none;
            box-shadow: 0 0 0 2px var(--bg-primary), 0 0 0 4px var(--accent);
        }}

        .focus-ring:focus-visible {{
            outline: none;
            box-shadow: 0 0 0 2px var(--bg-primary), 0 0 0 4px #0A84FF;
        }}
    """
