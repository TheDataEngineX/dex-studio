"""Outbound push notification for pipeline alerts (dead-letter, quality, drift, reconciliation).

Alerts are always recorded in the studio DB (pull-based, via /system/incidents).
This module additionally pushes them to a webhook so failures don't rely on
someone opening the UI. Configured via DEX_STUDIO_ALERT_WEBHOOK_URL; a no-op
when unset.
"""

from __future__ import annotations

import os

import httpx
import structlog

log = structlog.get_logger().bind(src="notify")

_TIMEOUT_S = 5.0


def send_alert_webhook(event_type: str, pipeline: str, message: str) -> bool:
    """POST an alert to the configured webhook. Returns True on 2xx delivery.

    Best-effort: network/config errors are logged, never raised, so alerting
    can never take down a pipeline run.
    """
    url = os.environ.get("DEX_STUDIO_ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return False
    payload = {"event_type": event_type, "pipeline": pipeline, "message": message}
    try:
        resp = httpx.post(url, json=payload, timeout=_TIMEOUT_S)
        resp.raise_for_status()
    except Exception:
        log.warning(
            "alert webhook delivery failed", event_type=event_type, pipeline=pipeline, url=url
        )
        return False
    return True
