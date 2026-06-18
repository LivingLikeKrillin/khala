"""A2A JSON-RPC 2.0 server surface (SPEC §5.1–§5.3, §5.6).

A thin, flag-gated adapter mounted onto the existing FastAPI app. It serves the Agent Card
at the spec well-known path (public) and a JSON-RPC ``message/send`` endpoint (token-gated)
that runs the ``retrieve_grounded`` skill by calling the *existing* grounded-answer path —
no new retrieval logic. Protocol churn is isolated here (adapter isolation, SPEC §4).

The grounded-answer service is injected (``answer_fn``) so the surface is unit-testable
without DB/LLM; production wires the default pipeline.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from a2a.compat.v0_3.types import (
    Artifact,
    Message,
    Role,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from nexus.a2a.audit import emit_audit
from nexus.a2a.card import build_agent_card
from nexus.a2a.config import A2AConfig
from nexus.a2a.ingest_skill import IngestOutcome, build_ingest_artifact, extract_governed_doc
from nexus.a2a.mapping import build_grounded_artifact
from nexus.a2a.policy import effective_scope, resolve_a2a_principal
from nexus.auth.deps import extract_bearer
from nexus.llm.answer import AnswerResult

# AnswerFn: (query, tenant, clearance) -> AnswerResult (sync or async).
AnswerFn = Callable[[str, str, str], AnswerResult | Awaitable[AnswerResult]]
# IngestFn: (governed_doc, tenant) -> IngestOutcome (sync or async).
IngestFn = Callable[[dict, str], IngestOutcome | Awaitable[IngestOutcome]]

_CARD_PATH = "/.well-known/agent-card.json"
_RPC_PATH = "/a2a"
_SKILL_METHOD = "message/send"
_SKILL_NAME = "retrieve_grounded"
_INGEST_SKILL = "ingest_governed_doc"
_INGEST_CAPABILITY = "ingest_governed"

# JSON-RPC error codes (subset).
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_UNAUTHORIZED = -32001
_FORBIDDEN = -32003


def _rpc_error(req_id, code: int, message: str, status: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}},
    )


def _extract_query(params: dict) -> str:
    """Pull the user query text out of the JSON-RPC ``message.parts`` (text parts)."""
    message = (params or {}).get("message") or {}
    texts = [p.get("text", "") for p in message.get("parts", []) if p.get("kind") == "text"]
    return "\n".join(t for t in texts if t).strip()


def _requested_scope(params: dict) -> tuple[str | None, str | None]:
    """Optional caller-supplied tenant/classification_max — requests, not grants."""
    meta = ((params or {}).get("message") or {}).get("metadata") or {}
    return meta.get("tenant"), meta.get("classification_max")


def _requested_skill(params: dict) -> str:
    """Which skill the message targets (metadata.skill_id); default retrieve_grounded."""
    meta = ((params or {}).get("message") or {}).get("metadata") or {}
    return str(meta.get("skill_id") or _SKILL_NAME)


def _wrap_task(artifact_json: dict, state: str, reason: str | None) -> dict:
    """Wrap a mapped artifact + state into a schema-valid A2A Task dict."""
    status_message = None
    if reason is not None:
        status_message = Message(
            role=Role.agent, message_id=uuid.uuid4().hex, parts=[TextPart(text=reason)],
        )
    task = Task(
        id=uuid.uuid4().hex,
        context_id=uuid.uuid4().hex,
        status=TaskStatus(state=TaskState(state), message=status_message),
        artifacts=[Artifact.model_validate(artifact_json)],
    )
    return task.model_dump(mode="json", by_alias=True, exclude_none=True)


def _build_task(result: AnswerResult, tenant: str, clearance: str) -> dict:
    """Map an AnswerResult to a schema-valid A2A Task (completed or failed)."""
    return _wrap_task(*build_grounded_artifact(result, tenant, clearance))


def mount_a2a(
    app: FastAPI,
    cfg: A2AConfig,
    answer_fn: AnswerFn | None = None,
    ingest_fn: IngestFn | None = None,
) -> None:
    """Conditionally mount the A2A surface. No-op (no routes) when ``cfg.enabled`` is false."""
    if not cfg.enabled:
        return

    resolved_answer_fn = answer_fn or _default_answer_fn
    resolved_ingest_fn = ingest_fn or _default_ingest_fn

    @app.get(_CARD_PATH)
    def agent_card() -> dict:  # public discovery
        return build_agent_card(cfg)

    @app.post(_RPC_PATH)
    async def jsonrpc(request: Request, authorization: str | None = Header(default=None)):
        start = time.perf_counter()

        def elapsed_ms() -> int:
            return int((time.perf_counter() - start) * 1000)

        body = await request.json()
        req_id = body.get("id")
        method = body.get("method")
        params = body.get("params") or {}
        query = _extract_query(params)

        # Every outcome — granted or denied — leaves exactly one a2a.audit record (SPEC §6.1).
        if method != _SKILL_METHOD:
            emit_audit(skill=str(method), query=query, denied=True,
                       reason="method_not_found", latency_ms=elapsed_ms())
            return _rpc_error(req_id, _METHOD_NOT_FOUND, f"method not found: {method}")

        skill = _requested_skill(params)

        # Token-gated: the card is public, skill execution is not (default-deny).
        principal = resolve_a2a_principal(extract_bearer(authorization), cfg)
        if principal is None:
            emit_audit(skill=skill, query=query, denied=True,
                       reason="unauthorized", latency_ms=elapsed_ms())
            return _rpc_error(req_id, _UNAUTHORIZED, "unauthorized", status=401)

        # ── Write skill (Phase 3): ingest a governed doc — capability-gated. ──
        if skill == _INGEST_SKILL:
            if not principal.has(_INGEST_CAPABILITY):
                emit_audit(skill=_INGEST_SKILL, query="", principal=principal.name,
                           tenant=principal.tenant, clearance=principal.clearance,
                           denied=True, reason="forbidden_no_capability",
                           latency_ms=elapsed_ms())
                return _rpc_error(req_id, _FORBIDDEN,
                                  "forbidden: ingest_governed capability required", status=403)

            doc = extract_governed_doc(params)
            if doc is None:
                emit_audit(skill=_INGEST_SKILL, query="", principal=principal.name,
                           tenant=principal.tenant, clearance=principal.clearance,
                           denied=True, reason="invalid_doc", latency_ms=elapsed_ms())
                return _rpc_error(req_id, _INVALID_PARAMS, "invalid governed-doc payload")

            tenant, _clearance = effective_scope(principal)  # ingest is tenant-bound
            outcome = resolved_ingest_fn(doc, tenant)
            if isinstance(outcome, Awaitable):
                outcome = await outcome

            artifact_json, state, reason = build_ingest_artifact(outcome, doc, tenant)
            task = _wrap_task(artifact_json, state, reason)
            emit_audit(
                skill=_INGEST_SKILL, query=str(doc.get("id", "")), principal=principal.name,
                tenant=tenant, clearance=principal.clearance,
                evidence_count=outcome.chunks_indexed, task_state=state,
                denied=False, reason=reason, latency_ms=elapsed_ms(),
            )
            return {"jsonrpc": "2.0", "id": req_id, "result": task}

        if not query:
            emit_audit(skill=_SKILL_NAME, query=query, principal=principal.name,
                       tenant=principal.tenant, clearance=principal.clearance,
                       denied=True, reason="empty_query", latency_ms=elapsed_ms())
            return _rpc_error(req_id, _INVALID_PARAMS, "empty query")

        req_tenant, req_clearance = _requested_scope(params)
        tenant, clearance = effective_scope(principal, req_tenant, req_clearance)

        result = resolved_answer_fn(query, tenant, clearance)
        if isinstance(result, Awaitable):
            result = await result

        task = _build_task(result, tenant, clearance)
        emit_audit(
            skill=_SKILL_NAME, query=query, principal=principal.name,
            tenant=tenant, clearance=clearance, route=result.route_used,
            evidence_count=len(result.evidence_snippets),
            task_state=task["status"]["state"], denied=False, latency_ms=elapsed_ms(),
        )
        return {"jsonrpc": "2.0", "id": req_id, "result": task}


async def _default_answer_fn(query: str, tenant: str, clearance: str) -> AnswerResult:
    """Production grounded-answer path — the same pipeline behind ``POST /search/answer``.

    Imported lazily so the disabled surface stays import-light.
    """
    from nexus import db
    from nexus.index.graph_extractor import (
        _build_entity_patterns,
        _load_gazetteer,
        find_entities_in_text,
    )
    from nexus.llm.answer import generate_answer
    from nexus.providers.embedding import EmbeddingService
    from nexus.providers.llm import LLMService
    from nexus.repositories.graph import PostgresGraphRepository
    from nexus.rid import entity_rid
    from nexus.search.evidence_packet import assemble_packet
    from nexus.search.hybrid import hybrid_search
    from nexus.search.router import determine_route

    def _load_config() -> dict:
        from pathlib import Path

        import yaml
        p = Path("config.yaml")
        if not p.exists():
            return {}
        with open(p, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    config = _load_config()
    embedding_svc = EmbeddingService()
    llm_svc = LLMService()
    pool = await db.get_pool()
    graph_repo = PostgresGraphRepository(pool)

    gazetteer = _load_gazetteer()
    patterns = _build_entity_patterns(gazetteer)
    detected = find_entities_in_text(query, patterns)
    entity_rids = [entity_rid(tenant, e.entity_type, e.name) for e in detected]
    route = determine_route(query, "auto", [e.name for e in detected])

    search_result = await hybrid_search(
        query=query, tenant=tenant, clearance=clearance, top_k=10,
        embedding_svc=embedding_svc, graph_repo=graph_repo, route=route,
        entity_rids=entity_rids, config=config,
    )
    packet = assemble_packet(search_result.hits, search_result.graph)
    return await generate_answer(
        query=query, packet=packet, llm_svc=llm_svc,
        route_used=route, timing_ms=search_result.timing_ms,
    )


async def _default_ingest_fn(doc: dict, tenant: str) -> IngestOutcome:
    """Production ingest path: bridge the inline body to the existing file-based pipeline.

    ``run_ingest`` is path-based (globs ``**/*.md``), so the governed-doc body is written to
    a transient file and ingested (SPEC §5.2 bridge). Imported lazily so the disabled surface
    stays import-light. Idempotency dedup by ``(tenant, id, content_hash)`` is deferred
    (SPEC §10) — this default reports ``idempotent_hit=False``.
    """
    import tempfile
    from pathlib import Path

    from nexus.ingest.pipeline import run_ingest
    from nexus.rid import doc_rid

    body = str(doc.get("body", ""))
    source = str(doc.get("source") or f"{doc.get('id', 'doc')}.md")
    fname = Path(source).name or f"{doc.get('id', 'doc')}.md"
    if not fname.endswith(".md"):
        fname += ".md"

    with tempfile.TemporaryDirectory() as td:
        (Path(td) / fname).write_text(body, encoding="utf-8")
        result = await run_ingest(td, force=True, tenant=tenant)

    return IngestOutcome(
        resource_rid=doc_rid(source),
        classification="INTERNAL",  # server classifier ran in-pipeline; not surfaced per-doc here
        chunks_indexed=result.bm25_indexed,
        quarantined=result.quarantined > 0,
        approved_hash=str(doc.get("content_hash", "")),
        idempotent_hit=False,
    )
