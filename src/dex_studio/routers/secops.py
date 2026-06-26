"""SecOps domain routes — PrivacyGuard status and audit log."""

from __future__ import annotations

import contextlib
import datetime as _dt
from typing import Any

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from dex_studio.routers._deps import ReadDep, base_ctx, render
from dex_studio.utils import fmt_ts

router = APIRouter()
log = structlog.get_logger().bind(src="router.secops")


def _privacy_guard(eng: Any) -> Any:
    """Return eng.privacy_guard or None — safe against older dataenginex installs."""
    return getattr(eng, "privacy_guard", None)


def _secops_audit(eng: Any) -> Any:
    """Return eng.secops_audit or None — safe against older dataenginex installs."""
    return getattr(eng, "secops_audit", None)


def _audit_chart_json(audit: Any, days: int = 42) -> str:
    """Return a JSON array of daily event counts for the last *days* days."""
    cells: list[int] = [0] * days
    with contextlib.suppress(Exception):
        now = _dt.datetime.now(_dt.UTC)
        origin = now - _dt.timedelta(days=days - 1)
        for e in audit.events:
            ts = e.occurred_at
            if not ts:
                continue
            if isinstance(ts, str):
                ts = _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if not ts.tzinfo:
                ts = ts.replace(tzinfo=_dt.UTC)
            delta = (ts - origin).days
            if 0 <= delta < days:
                cells[delta] += 1
    return "[" + ",".join(str(x) for x in cells) + "]"


def _mode_for_strategy(strategy_value: str) -> str:
    """Map strategy/action value to a display mode: mask | block | allow."""
    v = strategy_value.lower()
    if any(k in v for k in ("mask", "hash", "redact", "pseudonymize")):
        return "mask"
    if any(k in v for k in ("block", "deny", "reject")):
        return "block"
    return "allow"


_GuardConfig = tuple[bool, bool, bool, bool, list[str], list[dict[str, str]]]


def _load_guard_config(guard: Any) -> _GuardConfig:
    """Extract PrivacyGuard configuration.

    Returns (enabled, block_on_detect, allow_local, log_all, targets, strategies).
    """
    if guard is None:
        return False, False, True, True, [], []
    cfg = guard.config
    enabled: bool = cfg.enabled
    block_on_detect: bool = cfg.block_on_detect
    allow_local: bool = cfg.allow_local
    log_all_outbound: bool = cfg.log_all_outbound
    local_targets: list[str] = sorted(cfg.local_targets)
    strategies: list[dict[str, str]] = [
        {"pii_type": k.value, "strategy": v.value}
        for k, v in sorted(cfg.strategies.items(), key=lambda kv: kv[0].value)
    ]
    if enabled:
        log.info(
            "privacy guard active",
            block_on_detect=block_on_detect,
            strategy_count=len(strategies),
        )
    else:
        log.warning("privacy guard is disabled")
    return enabled, block_on_detect, allow_local, log_all_outbound, local_targets, strategies


def _load_audit_data(
    audit: Any,
) -> tuple[int, int, list[dict[str, Any]], list[dict[str, Any]]]:
    """Load audit events and compute overview stats.

    Returns (count, today_count, recent_events, top_fields).
    """
    if audit is None:
        return 0, 0, [], []

    raw_events = audit.events
    audit_count = len(raw_events)
    today_str = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d")
    audit_today = 0
    with contextlib.suppress(Exception):
        for e in raw_events:
            ts = str(getattr(e, "occurred_at", "") or "")
            if ts.startswith(today_str):
                audit_today += 1

    recent_events: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        recent_events = [
            {
                "operation": e.operation.value,
                "dataset": e.dataset_name,
                "pii_fields": e.pii_fields,
                "record_count": e.record_count,
                "occurred_at": str(e.occurred_at)[:19].replace("T", " "),
                "actor": getattr(e, "actor", "system"),
            }
            for e in reversed(raw_events[-10:])
        ]

    top_masked_fields = _top_masked_fields(raw_events)
    return audit_count, audit_today, recent_events, top_masked_fields


def _top_masked_fields(raw_events: Any) -> list[dict[str, Any]]:
    """Compute top 5 fields by mask count."""
    field_counts: dict[str, int] = {}
    field_strategy: dict[str, str] = {}
    with contextlib.suppress(Exception):
        for e in raw_events:
            for f in e.pii_fields or []:
                field_counts[f] = field_counts.get(f, 0) + 1
                if f not in field_strategy:
                    field_strategy[f] = f.split(".")[0] if "." in f else "pii"
    return [
        {"field": f, "count": c, "strategy": field_strategy.get(f, "pii")}
        for f, c in sorted(field_counts.items(), key=lambda x: -x[1])[:5]
    ]


def _build_strategy_display(
    strategies: list[dict[str, str]], pii_action: str
) -> list[dict[str, Any]]:
    """Build enriched strategy list for display; falls back to defaults."""
    display: list[dict[str, Any]] = [
        {
            "name": s["pii_type"],
            "strategy": s["strategy"],
            "mode": _mode_for_strategy(s["strategy"]),
            "field_count": 1,
        }
        for s in strategies
    ]
    if not display:
        _defaults = [
            ("email", pii_action),
            ("ssn", "block"),
            ("phone", pii_action),
            ("credit_card", "block"),
        ]
        for pt, act in _defaults:
            display.append(
                {"name": pt, "strategy": act, "mode": _mode_for_strategy(act), "field_count": 1}
            )
    return display


def _security_score(
    guard_active: bool, block_on_detect: bool, active_rules: int
) -> tuple[int, str]:
    """Compute security score and posture label."""
    score = 50
    if guard_active:
        score = 75
        if block_on_detect:
            score = 90
        if active_rules >= 3:
            score = min(99, score + 5)
    if score >= 80:
        label = "Security Nominal"
    elif score >= 50:
        label = "Security Warning"
    else:
        label = "At Risk"
    return score, label


def _build_activity_feed(recent_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build activity feed entries from recent audit events."""
    feed: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        for e in recent_events[:10]:
            op = e.get("operation", "")
            ds = e.get("dataset", "—")
            if op == "blocked":
                icon, badge, sub = "shield-x", "blocked", f"policy blocked · {ds}"
            elif e.get("pii_fields"):
                count = len(e.get("pii_fields") or [])
                icon, badge, sub = "shield-check", "masked", f"{count} fields masked · {ds}"
            else:
                icon, badge, sub = "eye", "read", f"data access · {ds}"
            feed.append(
                {
                    "icon": icon,
                    "desc": op or "data.access",
                    "sub": sub,
                    "badge": badge,
                    "time_ago": (e.get("occurred_at") or "—")[-5:],
                    "domain": "secops",
                    "href": "/secops/audit",
                }
            )
    return feed


def _parse_audit_events(
    raw: list[Any], today_str: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse raw audit events into serialisable dicts and compute counts."""
    all_events: list[dict[str, Any]] = []
    tables_seen: set[str] = set()
    today_count = 0
    violations = 0

    with contextlib.suppress(Exception):
        for e in raw:
            occurred = str(getattr(e, "occurred_at", "") or "")
            op = getattr(e, "operation", None)
            op_val: str = op.value if op is not None else "data.access"
            ds: str = getattr(e, "dataset_name", "") or "—"
            pii_raw = getattr(e, "pii_fields", None)
            pii_str = ", ".join(pii_raw) if pii_raw else "—"
            actor: str = getattr(e, "actor", "system") or "system"
            meta: dict[str, Any] = getattr(e, "metadata", {}) or {}

            all_events.append(
                {
                    "operation": op_val,
                    "dataset": ds,
                    "pii_fields": pii_str,
                    "record_count": getattr(e, "record_count", None),
                    "actor": actor,
                    "occurred_at": occurred[:19].replace("T", " "),
                    "date": occurred[:10],
                    "metadata": meta,
                }
            )

            if occurred.startswith(today_str):
                today_count += 1
            if ds and ds != "—":
                tables_seen.add(ds)
            if op_val == "blocked":
                violations += 1

    counts: dict[str, Any] = {
        "total": len(all_events),
        "today": today_count,
        "unique_tables": len(tables_seen),
        "violations": violations,
    }
    return all_events, counts


# ── Overview ──────────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def secops_overview(request: Request, eng: ReadDep) -> HTMLResponse:  # noqa: C901
    log.debug("secops overview viewed")
    guard = _privacy_guard(eng)

    guard_enabled, block_on_detect, allow_local, log_all_outbound, local_targets, strategies = (
        _load_guard_config(guard)
    )

    audit = _secops_audit(eng)
    audit_count, audit_today, recent_events, top_masked_fields = _load_audit_data(audit)

    pii_action = "warn"
    with contextlib.suppress(Exception):
        sec = getattr(eng.config, "secops", None)
        pii_cfg = getattr(sec, "pii", None) if sec else None
        if pii_cfg:
            pii_action = str(getattr(pii_cfg, "action", "warn"))

    strategy_display = _build_strategy_display(strategies, pii_action)
    guard_active = guard_enabled
    strategy_count = len(strategy_display)
    active_rules = sum(1 for s in strategy_display if s["mode"] != "allow")

    security_score, posture_label = _security_score(guard_active, block_on_detect, active_rules)
    activity_feed = _build_activity_feed(recent_events)

    chart_json = _audit_chart_json(audit) if audit is not None else "[" + ",".join(["0"] * 42) + "]"

    ctx = base_ctx(request) | {
        "guard_enabled": guard_enabled,
        "guard_active": guard_active,
        "block_on_detect": block_on_detect,
        "allow_local": allow_local,
        "log_all_outbound": log_all_outbound,
        "local_targets": local_targets,
        "strategies": strategies,
        "strategy_display": strategy_display,
        "strategy_count": strategy_count,
        "active_rules": active_rules,
        "security_score": security_score,
        "posture_label": posture_label,
        "audit_enabled": audit is not None,
        "audit_count": audit_count,
        "audit_today": audit_today,
        "recent_events": recent_events,
        "top_masked_fields": top_masked_fields,
        "activity_feed": activity_feed,
        "pii_action": pii_action,
        "outbound_calls_today": audit_today,
        "pii_masked_today": sum(len(e.get("pii_fields") or []) for e in recent_events),
        "calls_blocked_today": sum(1 for e in recent_events if e.get("operation") == "blocked"),
        "external_spend_today": "0.00",
        "chart_zeros": chart_json,
        # ponytail: nested getattr chain, refactor if secops config grows
        "pii_masking": getattr(
            getattr(getattr(eng.config, "secops", None), "pii", None),
            "masking",
            None,
        ),
    }
    return render(request, "secops/overview.html", ctx)


# ── Privacy ──────────────────────────────────────────────────────────────────


@router.get("/privacy", response_class=HTMLResponse)
def secops_privacy(request: Request, eng: ReadDep) -> HTMLResponse:
    guard = _privacy_guard(eng)
    guard_enabled, block_on_detect, allow_local, log_all_outbound, local_targets, strategies = (
        _load_guard_config(guard)
    )

    pii_action = "warn"
    with contextlib.suppress(Exception):
        sec = getattr(eng.config, "secops", None)
        pii_cfg = getattr(sec, "pii", None) if sec else None
        if pii_cfg:
            pii_action = str(getattr(pii_cfg, "action", "warn"))

    strategy_display = _build_strategy_display(strategies, pii_action)
    active_rules = sum(1 for s in strategy_display if s["mode"] != "allow")

    audit = _secops_audit(eng)
    audit_count, audit_today, recent_events, top_masked_fields = _load_audit_data(audit)

    pii_cfg = None
    with contextlib.suppress(Exception):
        sec = getattr(eng.config, "secops", None)
        pii_cfg = getattr(sec, "pii", None) if sec else None

    ctx = base_ctx(request) | {
        "guard_enabled": guard_enabled,
        "block_on_detect": block_on_detect,
        "allow_local": allow_local,
        "log_all_outbound": log_all_outbound,
        "local_targets": local_targets,
        "guard_local_targets": local_targets,
        "guard_strategies": {s["name"]: s["mode"] for s in strategy_display},
        "strategy_display": strategy_display,
        "active_rules": active_rules,
        "pii_action": pii_action,
        "pii_scan": getattr(pii_cfg, "scan", False) if pii_cfg else False,
        "pii_patterns": getattr(pii_cfg, "patterns", []) if pii_cfg else [],
        "pii_masking": getattr(pii_cfg, "masking", None) if pii_cfg else None,
        "audit_count": audit_count,
        "audit_today": audit_today,
        "top_masked_fields": top_masked_fields,
    }
    return render(request, "secops/privacy.html", ctx)


# ── Policies ──────────────────────────────────────────────────────────────────


@router.get("/policies", response_class=HTMLResponse)
def secops_policies(request: Request, eng: ReadDep) -> HTMLResponse:
    guard = _privacy_guard(eng)
    guard_enabled, block_on_detect, allow_local, log_all_outbound, local_targets, strategies = (
        _load_guard_config(guard)
    )

    pii_action = "warn"
    with contextlib.suppress(Exception):
        sec = getattr(eng.config, "secops", None)
        pii_cfg = getattr(sec, "pii", None) if sec else None
        if pii_cfg:
            pii_action = str(getattr(pii_cfg, "action", "warn"))

    strategy_display = _build_strategy_display(strategies, pii_action)

    # Build policy list from strategies + default data governance rules
    policies: list[dict[str, str]] = [
        {
            "name": s["name"].replace("_", " ").title(),
            "rule": f"PII type: {s['name']}",
            "action": s["strategy"],
            "mode": s["mode"],
        }
        for s in strategy_display
    ]

    config_policies: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        sec_pol = getattr(getattr(eng.config, "secops", None), "policies", None)
        if sec_pol:
            config_policies = [
                {
                    "name": p.name,
                    "description": p.description,
                    "rule": p.rule,
                    "severity": p.severity,
                    "tables": p.tables,
                }
                for p in sec_pol
            ]

    ctx = base_ctx(request) | {
        "guard_enabled": guard_enabled,
        "block_on_detect": block_on_detect,
        "allow_local": allow_local,
        "log_all_outbound": log_all_outbound,
        "local_targets": local_targets,
        "policies": policies,
        "pii_action": pii_action,
        "config_policies": config_policies,
    }
    return render(request, "secops/policies.html", ctx)


# ── Audit log ─────────────────────────────────────────────────────────────────


@router.get("/audit", response_class=HTMLResponse)
def secops_audit(
    request: Request,
    eng: ReadDep,
    action: str = "",
    date_from: str = "",
    date_to: str = "",
    table: str = "",
) -> HTMLResponse:
    audit = _secops_audit(eng)

    all_events: list[dict[str, Any]] = []
    event_counts: dict[str, Any] = {"total": 0, "today": 0, "unique_tables": 0, "violations": 0}

    if audit is not None:
        raw = list(reversed(audit.events))
        today_str = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d")
        all_events, event_counts = _parse_audit_events(raw, today_str)

        if action:
            all_events = [e for e in all_events if e["operation"] == action]
        if date_from:
            all_events = [e for e in all_events if e["date"] >= date_from]
        if date_to:
            all_events = [e for e in all_events if e["date"] <= date_to]
        if table:
            tl = table.lower()
            all_events = [e for e in all_events if tl in e["dataset"].lower()]

    ctx = base_ctx(request) | {
        "audit_enabled": audit is not None,
        "events": all_events,
        "event_counts": event_counts,
        "filter_action": action,
        "filter_date_from": date_from,
        "filter_date_to": date_to,
        "filter_table": table,
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
                        "message": f"Feature drift detected on {feat}: PSI exceeds {threshold}",
                        "source": "ml.drift monitor",
                        "threshold": str(threshold),
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
                        "message": f"Pipeline '{name}' last run did not succeed.",
                        "source": f"data.pipelines.{name}",
                        "threshold": "0 failures",
                    }
                )

    firing_count = sum(1 for r in alert_rules if r["state"] == "firing")
    armed_count = sum(1 for r in alert_rules if r["state"] == "armed")
    critical_count = sum(
        1 for r in alert_rules if r.get("severity") == "high" and r["state"] == "firing"
    )
    info_count = sum(1 for r in alert_rules if r.get("severity") not in ("high", "med"))

    config_alerts: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        sec_alerts = getattr(getattr(eng.config, "secops", None), "alerts", None)
        if sec_alerts:
            config_alerts = [
                {
                    "name": a.name,
                    "condition": a.condition,
                    "severity": a.severity,
                    "channels": a.channels,
                }
                for a in sec_alerts
            ]

    ctx = base_ctx(request) | {
        "alert_rules": alert_rules,
        "firing_count": firing_count,
        "armed_count": armed_count,
        "critical_count": critical_count,
        "info_count": info_count,
        "active_tab": "secops",
        "config_alerts": config_alerts,
    }
    return render(request, "secops/alerts.html", ctx)
