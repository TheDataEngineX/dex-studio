"""Shared formatting helpers used by routers and Jinja2 templates."""

from __future__ import annotations

from datetime import datetime


def fmt_ts(ts: object) -> str:
    """Format an ISO timestamp string to 'May 21 14:30', or '—' if absent."""
    s = str(ts or "")
    if not s or s in ("-", "None", ""):
        return "—"
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.strftime("%b %d %H:%M")
    except (ValueError, AttributeError):
        return s


def fmt_cron(expr: str) -> str:
    """Return a short human-readable label for common cron expressions."""
    e = (expr or "").strip()
    if not e or e == "—":
        return "—"
    shortcuts = {
        "@hourly": "Hourly",
        "@daily": "Daily",
        "@weekly": "Weekly",
        "@monthly": "Monthly",
        "@yearly": "Yearly",
        "@reboot": "On reboot",
    }
    if e in shortcuts:
        return shortcuts[e]
    parts = e.split()
    if len(parts) != 5:
        return e
    minute, hour, dom, month, dow = parts
    if minute.startswith("*/") and hour == dom == month == dow == "*":
        n = minute[2:]
        return f"Every {n} min" if n.isdigit() else e
    if minute == "0" and hour.startswith("*/") and dom == month == dow == "*":
        n = hour[2:]
        return f"Every {n} hours" if n.isdigit() else e
    if minute == "0" and hour == "0" and dom == month == dow == "*":
        return "Daily at midnight"
    if minute == "0" and hour == "0" and dom == "*" and month == "*" and dow == "0":
        return "Weekly (Sun)"
    return e


def fmt_bytes(n: int | None) -> str:
    """Format byte count to human-readable string."""
    if n is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n //= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"


def status_color(status: str) -> str:
    """Map a status string to a Radix color name."""
    s = (status or "").lower()
    if s in ("ok", "healthy", "active", "success", "available", "production", "passed"):
        return "green"
    if s in ("warning", "warn", "staging", "running"):
        return "orange"
    if s in ("error", "failed", "failure", "offline", "critical"):
        return "red"
    return "gray"
