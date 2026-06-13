"""SecOps domain routes — PrivacyGuard status and audit log."""

from __future__ import annotations

import contextlib
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from dex_studio.routers._deps import ReadDep, base_ctx, render
from dex_studio.utils import fmt_ts

router = APIRouter()


def _privacy_guard(eng: Any) -> Any:
    """Return eng.privacy_guard or None — safe against older dataenginex installs."""
    return getattr(eng, "privacy_guard", None)


def _secops_audit(eng: Any) -> Any:
    """Return eng.secops_audit or None — safe against older dataenginex installs."""
    return getattr(eng, "secops_audit", None)


# ── Overview ──────────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def secops_overview(request: Request, eng: ReadDep) -> HTMLResponse:
    guard = _privacy_guard(eng)

    strategies: list[dict[str, str]] = []
    guard_enabled = False
    block_on_detect = False
    allow_local = True
    log_all_outbound = True
    local_targets: list[str] = []

    if guard is not None:
        cfg = guard.config
        guard_enabled = cfg.enabled
        block_on_detect = cfg.block_on_detect
        allow_local = cfg.allow_local
        log_all_outbound = cfg.log_all_outbound
        local_targets = sorted(cfg.local_targets)
        strategies = [
            {"pii_type": k.value, "strategy": v.value}
            for k, v in sorted(cfg.strategies.items(), key=lambda kv: kv[0].value)
        ]

    audit = _secops_audit(eng)
    audit_count = 0
    recent_events: list[dict[str, Any]] = []
    if audit is not None:
        events = audit.events
        audit_count = len(events)
        recent_events = [
            {
                "operation": e.operation.value,
                "dataset": e.dataset_name,
                "pii_fields": e.pii_fields,
                "record_count": e.record_count,
                "occurred_at": str(e.occurred_at)[:19].replace("T", " "),
            }
            for e in reversed(events[-10:])
        ]

    # PII config from dex.yaml secops.pii
    pii_action = "warn"
    with contextlib.suppress(Exception):
        sec = getattr(eng.config, "secops", None)
        pii_cfg = getattr(sec, "pii", None) if sec else None
        if pii_cfg:
            pii_action = str(getattr(pii_cfg, "action", "warn"))

    ctx = base_ctx(request) | {
        "guard_enabled": guard_enabled,
        "block_on_detect": block_on_detect,
        "allow_local": allow_local,
        "log_all_outbound": log_all_outbound,
        "local_targets": local_targets,
        "strategies": strategies,
        "audit_enabled": audit is not None,
        "audit_count": audit_count,
        "recent_events": recent_events,
        "pii_action": pii_action,
        # privacy dashboard stats (populated by audit when available)
        "outbound_calls_today": audit_count,
        "pii_masked_today": sum(len(e.get("pii_fields", [])) for e in recent_events),
        "calls_blocked_today": sum(1 for e in recent_events if e.get("operation") == "blocked"),
        "external_spend_today": "0.00",
        # Zeros until real LLM calls are recorded
        "chart_zeros": "[" + ",".join(["0"] * 42) + "]",
    }
    return render(request, "secops/overview.html", ctx)


# ── Audit log ─────────────────────────────────────────────────────────────────


@router.get("/audit", response_class=HTMLResponse)
def secops_audit(request: Request, eng: ReadDep) -> HTMLResponse:
    audit = _secops_audit(eng)

    if audit is None:
        ctx = base_ctx(request) | {"events": [], "audit_enabled": False}
    else:
        events = list(reversed(audit.events))
        ctx = base_ctx(request) | {
            "audit_enabled": True,
            "events": [
                {
                    "operation": e.operation.value,
                    "dataset": e.dataset_name,
                    "pii_fields": ", ".join(e.pii_fields) if e.pii_fields else "—",
                    "record_count": e.record_count,
                    "actor": e.actor,
                    "occurred_at": str(e.occurred_at)[:19].replace("T", " "),
                    "metadata": e.metadata,
                }
                for e in events
            ],
        }
    return render(request, "secops/audit.html", ctx)


# ── Alerts ────────────────────────────────────────────────────────────────────


@router.get("/alerts", response_class=HTMLResponse)
def secops_alerts(request: Request, eng: ReadDep) -> HTMLResponse:
    alert_rules: list[dict[str, Any]] = []

    # Drift monitoring → alert rules
    with contextlib.suppress(Exception):
        ml_cfg = getattr(eng.config, "ml", None)
        drift_cfg = getattr(ml_cfg, "drift", None) if ml_cfg else None
        if drift_cfg:
            threshold = float(getattr(drift_cfg, "threshold", 0.15))
            features = (
                getattr(drift_cfg, "monitor", None) or getattr(drift_cfg, "features", None) or []
            )
            for feat in features:
                alert_rules.append(
                    {
                        "name": f"drift.{feat}",
                        "condition": f"PSI({feat}) > {threshold}",
                        "severity": "med",
                        "state": "armed",
                        "channel": "audit log",
                        "firings": 0,
                        "last_fired": "never",
                        "snooze_until": "",
                    }
                )

    # Pipeline failure → firing alerts
    with contextlib.suppress(Exception):
        for name in eng.config.data.pipelines or {}:
            last = eng.pipeline_last_run(name)
            if last and not last.success:
                alert_rules.append(
                    {
                        "name": f"pipeline.failure.{name}",
                        "condition": f"pipeline '{name}' last run failed",
                        "severity": "high",
                        "state": "firing",
                        "channel": "audit log",
                        "firings": 1,
                        "last_fired": fmt_ts(getattr(last, "timestamp", None)),
                        "snooze_until": "",
                    }
                )

    firing_count = sum(1 for r in alert_rules if r["state"] == "firing")
    armed_count = sum(1 for r in alert_rules if r["state"] == "armed")
    ctx = base_ctx(request) | {
        "alert_rules": alert_rules,
        "firing_count": firing_count,
        "armed_count": armed_count,
        "active_tab": "secops",
    }
    return render(request, "secops/alerts.html", ctx)
