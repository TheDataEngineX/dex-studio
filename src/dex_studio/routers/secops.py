"""SecOps domain routes — PrivacyGuard status and audit log."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dex_studio.routers._deps import base_ctx, get_eng, render, require_auth, require_engine

router = APIRouter()


def _guard(request: Request) -> RedirectResponse | None:
    return require_auth(request) or require_engine(request)


def _privacy_guard(eng: Any) -> Any:
    """Return eng.privacy_guard or None — safe against older dataenginex installs."""
    return getattr(eng, "privacy_guard", None)


def _secops_audit(eng: Any) -> Any:
    """Return eng.secops_audit or None — safe against older dataenginex installs."""
    return getattr(eng, "secops_audit", None)


# ── Overview ──────────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def secops_overview(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
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
    }
    return render(request, "secops/overview.html", ctx)


# ── Audit log ─────────────────────────────────────────────────────────────────


@router.get("/audit", response_class=HTMLResponse)
async def secops_audit(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
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
