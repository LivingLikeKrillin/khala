"""A2A audit trail (Phase 2 §5.2; durable sink Phase 3 §5.6/§19).

Emits exactly one PII-safe, structured audit record per A2A task — granted or denied. The
always-on path is ``structlog`` (no external dependency, air-gap intact). ``record_audit`` adds
a **best-effort durable mirror** into the ``a2a_audit`` table — but only when a DB pool already
exists, and never raising, so audit persistence can neither add a connection attempt to the
unit-test path nor break the request path if the DB is down.

The raw query is never recorded anywhere: only ``query_sha256`` + ``query_len``, so the audit
trail cannot become a quarantine bypass (Nexus principle #3).
"""

from __future__ import annotations

import hashlib

import structlog

from nexus import db

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


async def record_audit(
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
    """Emit the structlog record (always) and best-effort persist it to ``a2a_audit``.

    The DB insert runs only when a pool already exists (``db.has_pool()``) — so unit tests with
    no DB never trigger a connection — and any failure is swallowed (the audit trail must never
    break the request path). The raw ``query`` is hashed before it touches either sink.
    """
    emit_audit(
        skill=skill, query=query, principal=principal, tenant=tenant, clearance=clearance,
        route=route, evidence_count=evidence_count, task_state=task_state, denied=denied,
        reason=reason, latency_ms=latency_ms,
    )
    if not db.has_pool():
        return
    try:
        await db.execute(
            """
            INSERT INTO a2a_audit (
                skill, principal, tenant, clearance, query_sha256, query_len,
                route, evidence_count, task_state, denied, reason, latency_ms
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            """,
            skill, principal, tenant, clearance, query_sha256(query), len(query),
            route, evidence_count, task_state, denied, reason, latency_ms,
        )
    except Exception as exc:  # noqa: BLE001 - audit persistence must never break the request
        log.warning("a2a.audit.persist_failed", error=str(exc))
