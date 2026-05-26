"""Career audit logger — optional DataEngineX integration for tracking career actions.

Uses DataEngineX AuditLog when available, otherwise falls back to simple in-memory logging.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

logger = structlog.get_logger()

try:
    from dataenginex.ai.observability.audit import AuditEntry as DexAuditEntry
    from dataenginex.ai.observability.audit import AuditLog as DexAuditLog

    _dex_audit: DexAuditLog | None = None

    def get_audit_log() -> DexAuditLog | None:
        global _dex_audit
        if _dex_audit is None:
            _dex_audit = DexAuditLog()
        return _dex_audit

    AUDIT_AVAILABLE = True
except ImportError:
    AUDIT_AVAILABLE = False
    DexAuditEntry = None
    DexAuditLog = None
    logger.warning("dataenginex audit not available")


class CareerAuditLogger:
    """Audit logger for career actions with DataEngineX integration."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []
        self._dex_log = get_audit_log() if AUDIT_AVAILABLE else None

    def log(
        self,
        action: str,
        company: str = "",
        role: str = "",
        details: str = "",
        status: str = "success",
    ) -> None:
        """Log a career action."""
        entry = {
            "timestamp": time.time(),
            "action": action,
            "company": company,
            "role": role,
            "details": details,
            "status": status,
        }
        self._entries.append(entry)
        logger.info("career_action", **entry)

        if self._dex_log and DexAuditEntry:
            self._dex_log.log(
                DexAuditEntry(
                    agent_name="careerdex",
                    action=action,
                    input=f"{company}: {role}",
                    output=details,
                    timestamp=time.time(),
                    reasoning=status,
                )
            )

    def get_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent audit entries."""
        return self._entries[-limit:]

    def log_application_added(self, company: str, role: str, url: str = "") -> None:
        self.log("application_added", company, role, url)

    def log_application_updated(self, company: str, role: str, status: str) -> None:
        self.log("application_updated", company, role, status)

    def log_resume_matched(self, score: str, details: str = "") -> None:
        self.log("resume_matched", details=details, status=score)

    def log_job_search(self, query: str, results_count: int = 0) -> None:
        self.log("job_search", details=f"query='{query}' results={results_count}")

    def log_batch_apply(self, count: int, success_count: int = 0) -> None:
        self.log(
            "batch_apply",
            details=f"total={count} success={success_count}",
            status="success" if success_count == count else "partial",
        )


_career_audit: CareerAuditLogger | None = None


def get_career_audit() -> CareerAuditLogger:
    global _career_audit
    if _career_audit is None:
        _career_audit = CareerAuditLogger()
    return _career_audit
