"""Alerting dispatcher for DEX Studio.

Reads alert_events from StudioDb and delivers undelivered ones via
configured channels (webhook / email stub). Alert rules are configured
in dex.yaml under the `alerting:` block.

Alert channels supported:
  - webhook: HTTP POST with JSON payload to a configurable URL
  - log: Structured log line (default fallback, always active)

Freshness signals are also computed here — comparing the latest pipeline
run timestamp against a configurable SLA threshold.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from pathlib import Path as _Path
from typing import Any

import structlog
import yaml

from dex_studio.studio_db import StudioDb

__all__ = ["AlertDispatcher", "FreshnessChecker", "read_alerting_config"]

log = structlog.get_logger().bind(src="alerting")


def read_alerting_config(eng: Any) -> dict[str, Any]:
    """Parse the `alerting:` block from dex.yaml."""
    path = getattr(eng, "config_path", None)
    if path is None:
        return {}
    try:
        raw: dict[str, Any] = yaml.safe_load(_Path(str(path)).read_text()) or {}
        return dict(raw.get("alerting") or {})
    except Exception:
        return {}


class AlertDispatcher:
    """Delivers undelivered alert_events via configured channels."""

    def __init__(self, db: StudioDb, config: dict[str, Any]) -> None:
        self._db = db
        self._cfg = config

    def _deliver_webhook(self, alert: dict[str, Any], url: str) -> bool:
        try:
            import json
            import urllib.request

            payload = json.dumps(alert).encode()
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
                return bool(resp.status < 300)
        except Exception as exc:
            log.warning("webhook delivery failed", url=url, error=str(exc))
            return False

    def dispatch_pending(self) -> int:
        """Deliver all undelivered alerts. Returns count delivered."""
        alerts = [a for a in self._db.get_alerts(limit=200) if not a["delivered"]]
        webhook_url: str = str(self._cfg.get("webhook_url") or "")
        delivered = 0
        for alert in alerts:
            log.info(
                "alert fired",
                event_type=alert["event_type"],
                pipeline=alert["pipeline"],
                message=alert["message"],
            )
            ok = True
            if webhook_url:
                ok = self._deliver_webhook(alert, webhook_url)
            if ok:
                self._db.mark_alert_delivered(alert["id"])
                delivered += 1
        return delivered

    def fire(self, event_type: str, pipeline: str, message: str) -> int:
        """Create and immediately attempt to deliver a new alert."""
        alert_id = self._db.record_alert(event_type, pipeline, message)
        with contextlib.suppress(Exception):
            self.dispatch_pending()
        return alert_id


class FreshnessChecker:
    """Checks pipeline SLAs against last-run timestamps stored in StudioDb."""

    def __init__(self, db: StudioDb, pipelines: dict[str, Any]) -> None:
        self._db = db
        self._pipes = pipelines

    def check_all(self) -> list[dict[str, Any]]:
        """Return freshness status for every pipeline that has a `schedule`."""
        results: list[dict[str, Any]] = []
        now = datetime.now(UTC)
        for name, cfg in self._pipes.items():
            schedule = str(getattr(cfg, "schedule", "") or "")
            if not schedule:
                continue
            last_run = self._db.get_last_run(name)
            sla_hours = float(getattr(cfg, "freshness_sla_hours", 0) or 0)
            status = "unknown"
            age_hours: float | None = None
            if last_run:
                age = now - last_run
                age_hours = age.total_seconds() / 3600
                if sla_hours > 0:
                    status = "ok" if age <= timedelta(hours=sla_hours) else "stale"
                else:
                    status = "ok"
            results.append(
                {
                    "pipeline": name,
                    "last_run": last_run.isoformat() if last_run else None,
                    "age_hours": round(age_hours, 2) if age_hours is not None else None,
                    "sla_hours": sla_hours or None,
                    "status": status,
                }
            )
        return results
