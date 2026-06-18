"""A2A audit trail (Phase 2, SPEC §5.2).

Emits exactly one PII-safe, structured audit record per A2A task — granted or denied — via
the existing ``structlog`` pipeline (no external dependency, air-gap intact). The raw query
is never recorded: only ``query_sha256`` + ``query_len``, so the audit log cannot become a
quarantine bypass (Nexus principle #3).
"""

from __future__ import annotations

import hashlib

import structlog

log = structlog.get_logger("nexus.a2a.audit")

# Stable event name for every cross-agent A2A task record.
AUDIT_EVENT = "a2a.audit"


def query_sha256(query: str) -> str:
    """sha256 hex of the raw query — the only form that may enter an audit record."""
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def emit_audit(
    *,
    skill: str,
    query: str,
    principal: str | None = None,
    tenant: str | None = None,
    clearance: str | None = None,
    route: str | None = None,
    evidence_count: int = 0,
    task_state: str | None = None,
    denied: bool = False,
    reason: str | None = None,
    latency_ms: int = 0,
) -> None:
    """Emit one ``a2a.audit`` record. The query is hashed here; callers pass it raw."""
    log.info(
        AUDIT_EVENT,
        skill=skill,
        principal=principal,
        tenant=tenant,
        clearance=clearance,
        query_sha256=query_sha256(query),
        query_len=len(query),
        route=route,
        evidence_count=evidence_count,
        task_state=task_state,
        denied=denied,
        reason=reason,
        latency_ms=latency_ms,
    )
