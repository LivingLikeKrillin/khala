"""A2A audit trail (Phase 2 §5.2; durable sink Phase 3 §5.6/§19).

Emits exactly one PII-safe, structured audit record per A2A task — granted or denied. The
always-on path is ``structlog`` (no external dependency, air-gap intact). ``record_audit`` adds
a **best-effort durable mirror** into the ``a2a_audit`` table — but only when a DB pool already
exists, and never raising, so audit persistence can neither add a connection attempt to the
unit-test path nor break the request path if the DB is down.

The raw query is never recorded anywhere. It used to leave a fingerprint —
``query_sha256`` — and that was not the PII-safe choice it was documented as: this record
carries ``principal``, and ``search_query_text`` stores the question in plaintext, so
recomputing ``sha256(plaintext)`` walked straight to a person. A salt would not have fixed it;
the tenant is a column in this same table (SPEC-nexus-audit-query-hash §1.4, approved
2026-08-14). What remains is ``query_len``, which is also a deterministic function of the
query — the criterion is entropy, not determinism, and a length alone recovers nothing.
"""

from __future__ import annotations

import structlog

from nexus import db

log = structlog.get_logger("nexus.a2a.audit")

# Stable event name for every cross-agent A2A task record.
AUDIT_EVENT = "a2a.audit"


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
    """Emit one ``a2a.audit`` record. Callers pass the query raw; only its **length** is kept."""
    log.info(
        AUDIT_EVENT,
        skill=skill,
        principal=principal,
        tenant=tenant,
        clearance=clearance,
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
    break the request path). Neither sink receives the query or any value derived from it
    beyond its length.
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
                skill, principal, tenant, clearance, query_len,
                route, evidence_count, task_state, denied, reason, latency_ms
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            skill, principal, tenant, clearance, len(query),
            route, evidence_count, task_state, denied, reason, latency_ms,
        )
    except Exception as exc:  # noqa: BLE001 - audit persistence must never break the request
        log.warning("a2a.audit.persist_failed", error=str(exc))
