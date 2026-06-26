"""Shared formatting helpers used by routers and Jinja2 templates."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _to_local_dt(ts: object) -> datetime | None:
    """Parse a UTC ISO string and return a local-timezone datetime, or None."""
    s = str(ts or "").strip()
    if not s or s in ("-", "None"):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()
    except (ValueError, AttributeError):
        return None


def fmt_ts(ts: object) -> str:
    """Format an ISO timestamp string to 'May 21 14:30' in local time, or '—'."""
    dt = _to_local_dt(ts)
    return dt.strftime("%b %d %H:%M") if dt else "—"


def fmt_ts_iso(ts: object) -> str:
    """Format an ISO timestamp string to 'YYYY-MM-DD HH:MM' in local time, or '—'."""
    dt = _to_local_dt(ts)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "—"


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


def fmt_run_row(r: Any, **extra: Any) -> dict[str, Any]:
    """Serialize a pipeline run record to a display dict.

    Pass extra keyword arguments to merge additional fields (e.g. trigger, io).
    """
    dur_ms = getattr(r, "duration_ms", None)
    if dur_ms is None:
        dur_str = "—"
    elif dur_ms >= 1000:
        dur_str = f"{dur_ms / 1000:.1f}s"
    else:
        dur_str = f"{int(dur_ms)}ms"
    return {
        "type": "pipeline",
        "name": r.pipeline_name,
        "status": "success" if r.success else "error",
        "started": fmt_ts_iso(r.timestamp),
        "duration": dur_str,
        **extra,
    }


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
