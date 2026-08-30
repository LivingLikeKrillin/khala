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

from nexus.a2a.audit import record_audit
from nexus.search import history as history_module
from nexus.a2a.card import build_agent_card
from nexus.a2a.config import A2AConfig
from nexus.a2a.external_ingest_skill import (
    EXTERNAL_LABEL,
    ExternalIngestOutcome,
    build_external_ingest_artifact,
    compute_source_hash,
    extract_external_spec,
    validate_external_spec,
)
from nexus.a2a.ingest_skill import IngestOutcome, build_ingest_artifact, extract_governed_doc
from nexus.a2a.mapping import build_grounded_artifact
from nexus.a2a.policy import effective_scope, resolve_a2a_principal
from nexus.a2a.ratelimit import RateLimiter
from nexus.auth.deps import extract_bearer
from nexus.llm.answer import AnswerResult

# AnswerFn: (query, tenant, clearance) -> AnswerResult (sync or async).
AnswerFn = Callable[[str, str, str], AnswerResult | Awaitable[AnswerResult]]
# IngestFn: (governed_doc, tenant) -> IngestOutcome (sync or async).
IngestFn = Callable[[dict, str], IngestOutcome | Awaitable[IngestOutcome]]
# ExternalIngestFn: (csf, tenant) -> ExternalIngestOutcome (sync or async).
ExternalIngestFn = Callable[[dict, str], "ExternalIngestOutcome | Awaitable[ExternalIngestOutcome]"]

_CARD_PATH = "/.well-known/agent-card.json"
_RPC_PATH = "/a2a"
_SKILL_METHOD = "message/send"
_SKILL_NAME = "retrieve_grounded"
_INGEST_SKILL = "ingest_governed_doc"
_INGEST_CAPABILITY = "ingest_governed"
_EXT_INGEST_SKILL = "ingest_external_spec"
_EXT_INGEST_CAPABILITY = "ingest_external"

# JSON-RPC error codes (subset).
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_UNAUTHORIZED = -32001
_FORBIDDEN = -32003
_RATE_LIMITED = -32005


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


def _requested_history(params: dict):
    """이력은 `message.metadata.history` 로 온다 — tenant/clearance/skill_id 와 같은 자리다.

    **`message.parts` 에 얹지 않는다.** 지금 `_extract_query` 는 text part 를 전부 이어 붙여
    질의로 쓰므로, 앞턴을 part 로 보내면 그것이 조용히 질의에 섞인다 — U2 의 약속("동작 변화
    0")을 깨는 것이 바로 그 모양이다. metadata 는 덧붙임이라 기존 호출자에게 아무 일도 없다.

    상한과 거절 규칙은 HTTP 와 **같은 정본**에서 온다(`nexus.search.history`). 두 벌로 적으면
    갈라지고, 이 리포는 그걸 이미 여러 번 겪었다.
    """
    meta = ((params or {}).get("message") or {}).get("metadata") or {}
    return history_module.parse(meta.get("history"))


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
    external_ingest_fn: ExternalIngestFn | None = None,
) -> None:
    """Conditionally mount the A2A surface. No-op (no routes) when ``cfg.enabled`` is false."""
    if not cfg.enabled:
        return

    resolved_answer_fn = answer_fn or _default_answer_fn
    resolved_ingest_fn = ingest_fn or _default_ingest_fn
    resolved_external_ingest_fn = external_ingest_fn or _default_external_ingest_fn
    limiter = RateLimiter(cfg.rate_limit_per_min)  # per-principal; 0 ⇒ disabled

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
            await record_audit(skill=str(method), query=query, denied=True,
                       reason="method_not_found", latency_ms=elapsed_ms())
            return _rpc_error(req_id, _METHOD_NOT_FOUND, f"method not found: {method}")

        skill = _requested_skill(params)

        # Token-gated: the card is public, skill execution is not (default-deny).
        principal = resolve_a2a_principal(extract_bearer(authorization), cfg)
        if principal is None:
            await record_audit(skill=skill, query=query, denied=True,
                       reason="unauthorized", latency_ms=elapsed_ms())
            return _rpc_error(req_id, _UNAUTHORIZED, "unauthorized", status=401)

        # Per-principal rate limit (SPEC §21): one token can't flood the surface (default-deny
        # extended to volume). Checked after auth so the budget is keyed to a known principal.
        if not limiter.allow(principal.name):
            await record_audit(skill=skill, query=query, principal=principal.name,
                       tenant=principal.tenant, clearance=principal.clearance,
                       denied=True, reason="rate_limited", latency_ms=elapsed_ms())
            return _rpc_error(req_id, _RATE_LIMITED, "rate limit exceeded", status=429)

        # 이력 상한 — HTTP 와 **같은 정본**(nexus.search.history). 인증·레이트리밋 뒤에 두는
        # 이유는 거절 사유의 순서가 곧 방어의 순서이기 때문이다: 신원 없는 요청에 상한 이야기를
        # 해 줄 필요가 없다. U2 에서 여기 통과한 값은 **쓰이지 않고 버려진다**.
        try:
            _requested_history(params)
        except (history_module.HistoryTooLarge, history_module.MalformedHistory) as e:
            await record_audit(skill=skill, query=query, principal=principal.name,
                       tenant=principal.tenant, clearance=principal.clearance,
                       denied=True, reason="history_rejected", latency_ms=elapsed_ms())
            return _rpc_error(req_id, _INVALID_PARAMS, f"invalid history: {e}")

        # ── Write skill (Phase 3): ingest a governed doc — capability-gated. ──
        if skill == _INGEST_SKILL:
            if not principal.has(_INGEST_CAPABILITY):
                await record_audit(skill=_INGEST_SKILL, query="", principal=principal.name,
                           tenant=principal.tenant, clearance=principal.clearance,
                           denied=True, reason="forbidden_no_capability",
                           latency_ms=elapsed_ms())
                return _rpc_error(req_id, _FORBIDDEN,
                                  "forbidden: ingest_governed capability required", status=403)

            doc = extract_governed_doc(params)
            if doc is None:
                await record_audit(skill=_INGEST_SKILL, query="", principal=principal.name,
                           tenant=principal.tenant, clearance=principal.clearance,
                           denied=True, reason="invalid_doc", latency_ms=elapsed_ms())
                return _rpc_error(req_id, _INVALID_PARAMS, "invalid governed-doc payload")

            tenant, _clearance = effective_scope(principal)  # ingest is tenant-bound
            outcome = resolved_ingest_fn(doc, tenant)
            if isinstance(outcome, Awaitable):
                outcome = await outcome

            artifact_json, state, reason = build_ingest_artifact(outcome, doc, tenant)
            task = _wrap_task(artifact_json, state, reason)
            await record_audit(
                skill=_INGEST_SKILL, query=str(doc.get("id", "")), principal=principal.name,
                tenant=tenant, clearance=principal.clearance,
                evidence_count=outcome.chunks_indexed, task_state=state,
                denied=False, reason=reason, latency_ms=elapsed_ms(),
            )
            return {"jsonrpc": "2.0", "id": req_id, "result": task}

        # ── 외부 spec 메모 경로 (서브프로젝트 A): ungoverned, 별도 capability. ──
        if skill == _EXT_INGEST_SKILL:
            if not principal.has(_EXT_INGEST_CAPABILITY):
                await record_audit(skill=_EXT_INGEST_SKILL, query="", principal=principal.name,
                           tenant=principal.tenant, clearance=principal.clearance,
                           denied=True, reason="forbidden_no_capability",
                           latency_ms=elapsed_ms())
                return _rpc_error(req_id, _FORBIDDEN,
                                  "forbidden: ingest_external capability required", status=403)

            doc = extract_external_spec(params)
            if doc is None:
                await record_audit(skill=_EXT_INGEST_SKILL, query="", principal=principal.name,
                           tenant=principal.tenant, clearance=principal.clearance,
                           denied=True, reason="invalid_doc", latency_ms=elapsed_ms())
                return _rpc_error(req_id, _INVALID_PARAMS, "invalid external-spec payload")

            verr = validate_external_spec(doc)
            if verr is not None:
                await record_audit(skill=_EXT_INGEST_SKILL, query=str(doc.get("id", "")),
                           principal=principal.name, tenant=principal.tenant,
                           clearance=principal.clearance, denied=True,
                           reason="invalid_csf", latency_ms=elapsed_ms())
                return _rpc_error(req_id, _INVALID_PARAMS, f"invalid CSF: {verr}")

            tenant, _clearance = effective_scope(principal)  # ingest is tenant-bound
            outcome = resolved_external_ingest_fn(doc, tenant)
            if isinstance(outcome, Awaitable):
                outcome = await outcome

            artifact_json, state, reason = build_external_ingest_artifact(outcome, doc, tenant)
            task = _wrap_task(artifact_json, state, reason)
            await record_audit(
                skill=_EXT_INGEST_SKILL, query=str(doc.get("id", "")), principal=principal.name,
                tenant=tenant, clearance=principal.clearance,
                evidence_count=outcome.chunks_indexed, task_state=state,
                denied=False, reason=reason, latency_ms=elapsed_ms(),
            )
            return {"jsonrpc": "2.0", "id": req_id, "result": task}

        if not query:
            await record_audit(skill=_SKILL_NAME, query=query, principal=principal.name,
                       tenant=principal.tenant, clearance=principal.clearance,
                       denied=True, reason="empty_query", latency_ms=elapsed_ms())
            return _rpc_error(req_id, _INVALID_PARAMS, "empty query")

        req_tenant, req_clearance = _requested_scope(params)
        tenant, clearance = effective_scope(principal, req_tenant, req_clearance)

        result = resolved_answer_fn(query, tenant, clearance)
        if isinstance(result, Awaitable):
            result = await result

        task = _build_task(result, tenant, clearance)
        await record_audit(
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
    import time
    from nexus import db
    from nexus.index.graph_extractor import (
        _build_entity_patterns,
        _load_gazetteer,
        find_entities_in_text,
    )
    from nexus.llm.answer import generate_answer
    from nexus.providers.embedding import embedding_service_from_config
    from nexus.providers.llm import LLMService
    from nexus.repositories.graph import PostgresGraphRepository
    from nexus.rid import entity_rid
    from nexus.search.reconcile import packet_for_answer
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

    _t0 = time.time()
    config = _load_config()
    embedding_svc = embedding_service_from_config(config)
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
    packet = await packet_for_answer(search_result, tenant, clearance,
                                     config=config, search=hybrid_search,
                                     embedding_svc=embedding_svc,
                                     question=query, pool=await db.get_pool())
    answer_result = await generate_answer(
        query=query, packet=packet, llm_svc=llm_svc,
        route_used=route, timing_ms=search_result.timing_ms,
        confidence=search_result.confidence,
    )
    from nexus.search.signals import JudgeInput, extract_signals, record_search
    sig = extract_signals(
        search_result, answer_result, path="a2a",
        tenant=tenant, clearance=clearance, query=query,
        n_entities=len(entity_rids),
        latency_ms=int((time.time() - _t0) * 1000),
    )
    from nexus.search.evidence_packet import format_for_llm
    await record_search(sig, judge_input=JudgeInput(   # a2a_audit(인가)와 별개로 품질 기록
        query=query, evidence=format_for_llm(packet), config=config, llm_svc=llm_svc),
        # principal 을 넘기지 않는다 — `AnswerFn` 은 주입되는 계약 `(query, tenant, clearance)`
        # 이고 여기엔 신원이 오지 않는다. 허용목록에 오를 수 없으므로 A2A 질문은 보존되지
        # 않는다. **에이전트 질문이 필요 없다는 판단이 아니라, 이 표면이 아직 자기를 식별하지
        # 못한다는 한계다** — 필요해지면 계약을 넓히는 것이 먼저다.
        query_text=query)
    return answer_result


async def _default_ingest_fn(doc: dict, tenant: str) -> IngestOutcome:
    """Production ingest path: bridge the inline body to the existing file-based pipeline.

    ``run_ingest`` is path-based (globs ``**/*.md``), so the governed-doc body is written to a
    transient file and ingested (SPEC §5.2 bridge). The temp file name is **deterministic** from
    the governed doc's source basename, so the collector's canonical URI (``{tenant}:{name}``) —
    and thus the document ``rid`` — is **stable across re-publishes** regardless of temp dir.

    Idempotency (SPEC §5.4): ingest with ``force=False`` so the collector's built-in change
    detection — keyed on ``(tenant, source_uri, content_hash)`` — makes an unchanged re-publish a
    **no-op** (``idempotent_hit=True``, nothing re-indexed); a changed body supersedes (re-index).
    Imported lazily so the disabled surface stays import-light.
    """
    import tempfile
    from pathlib import Path

    from nexus import db
    from nexus.ingest.pipeline import run_ingest
    from nexus.rid import doc_rid

    body = str(doc.get("body", ""))
    source = str(doc.get("source") or f"{doc.get('id', 'doc')}.md")
    fname = Path(source).name or f"{doc.get('id', 'doc')}.md"
    if not fname.endswith(".md"):
        fname += ".md"

    approved_hash = str(doc.get("content_hash", ""))
    rid = doc_rid(f"{tenant}:{fname}")  # matches the collector's canonical_uri (stable)

    with tempfile.TemporaryDirectory() as td:
        (Path(td) / fname).write_text(body, encoding="utf-8")
        # force=False ⇒ the collector dedups by (tenant, source_uri, content_hash); persist the
        # governance stamp so retrieval surfaces it as approved_hash (SPEC §5.4).
        result = await run_ingest(td, force=False, tenant=tenant, approved_hash=approved_hash)

    # No files collected ⇒ the body is byte-identical to what's already indexed: idempotent no-op.
    idempotent = result.total_files == 0

    # Report the server-decided classification / quarantine from the stored row (never the caller).
    row = await db.fetch_one(
        "SELECT classification, is_quarantined FROM documents WHERE rid = $1 AND tenant = $2",
        rid, tenant,
    )
    classification = row["classification"] if row else "INTERNAL"
    quarantined = bool(row["is_quarantined"]) if row else (result.quarantined > 0)

    return IngestOutcome(
        resource_rid=rid,
        classification=classification,
        chunks_indexed=0 if idempotent else result.bm25_indexed,
        quarantined=quarantined,
        approved_hash=approved_hash,
        idempotent_hit=idempotent,
    )


def _csf_to_markdown_file(doc: dict) -> str:
    """CSF → 임시 파일에 쓸 마크다운. **제목을 frontmatter 로 실어 보낸다.**

    예전엔 body 만 썼다. 그래서 `run_ingest` 가 파일의 첫 헤딩에서 제목을 다시 만들었고,
    Notion 페이지 `Index` 가 코퍼스에 `Access 방식` 으로 들어갔다 — CSF 는 진짜 이름을
    싣고 있었는데 sink 가 버린 것이다. `derive_title` 은 이미 frontmatter 를 우선한다.

    제목이 없으면 frontmatter 를 쓰지 않는다. 첫 헤딩 폴백이 그대로 살아 있어야 한다.
    """
    import yaml

    body = str(doc.get("body", ""))
    title = str(doc.get("title", "") or "").strip()
    meta: dict = {}
    if title:
        meta["title"] = title
    # 비전 마커 신뢰는 **본문과 함께** 흘러야 한다. 이 임시 파일이 CSF 와 파이프라인 사이의
    # 유일한 통로라, 여기서 빠지면 청커가 마커를 못 믿고 벗겨 버리고 추출 텍스트가 저자
    # 텍스트로 세탁된다 — ADR-0010 §4 가 "추출 안 하느니만 못하다" 고 한 상태다.
    if doc.get("vision_extracted"):
        meta["vision_extracted"] = True
    # 그림 수도 같은 통로로 간다. 파이프라인이 `documents.n_images` 를 여기서 읽는다.
    if doc.get("image_count"):
        meta["image_count"] = int(doc["image_count"])
    if not meta:
        return body
    # yaml.safe_dump 로 인용한다 — `선두 컬럼: 제약 #1` 처럼 콜론·해시가 든 제목이 흔하다.
    fm = yaml.safe_dump(meta, allow_unicode=True, default_flow_style=False)
    return f"---\n{fm}---\n\n{body}"


async def _default_external_ingest_fn(doc: dict, tenant: str, *, force: bool = False) -> ExternalIngestOutcome:
    """Production 외부-ingest 경로: inline CSF body를 기존 파일 기반 파이프라인으로 브리지.

    governed 경로(_default_ingest_fn)와 동일하게 transient-file로 ingest 하되, approved_hash
    provenance는 없다. 결정적 id → 안정적 canonical URI 매핑으로 idempotency 가 성립한다
    (run_ingest force=False 의 (tenant, source_uri, content_hash) dedup). ingest 후 documents
    row 에 external_spec label 을 단다(classification 레벨이 아니라 CRM label).

    ``force=True`` 면 그 dedup 을 건너뛴다. 본문이 그대로여도 파생 메타데이터(제목 등)를
    다시 만들어야 할 때가 있다 — 콘솔의 "강제" 가 여기까지 닿지 않으면 그건 강제가 아니다.
    """
    import tempfile
    from pathlib import Path

    from nexus import db
    from nexus.ingest.pipeline import run_ingest
    from nexus.rid import doc_rid

    body = str(doc.get("body", ""))
    source_hash = compute_source_hash(body)   # 해시는 **본문**만 — frontmatter 는 파생물이다
    # id 는 신뢰 불가 외부 호출자가 보낸다 — 디렉터리 성분을 제거해 temp dir 탈출(path traversal)을
    # 막는다(governed _default_ingest_fn 의 Path(source).name 방어와 동일).
    safe_id = Path(str(doc.get("id", "ext-doc"))).name or "ext-doc"
    fname = f"{safe_id}.md"
    rid = doc_rid(f"{tenant}:{fname}")  # collector canonical_uri 와 일치(안정적)

    with tempfile.TemporaryDirectory() as td:
        (Path(td) / fname).write_text(_csf_to_markdown_file(doc), encoding="utf-8")
        result = await run_ingest(td, force=force, tenant=tenant)

    idempotent = result.total_files == 0
    # 서버 판정 quarantine 을 저장된 row 에서 읽어온다(governed _default_ingest_fn 와 동일).
    row = await db.fetch_one(
        "SELECT is_quarantined FROM documents WHERE rid = $1 AND tenant = $2",
        rid, tenant,
    )
    quarantined = bool(row["is_quarantined"]) if row else (result.quarantined > 0)
    # label(external_spec) · 축-A doc_type · prov_inputs(source_roots) 기록.
    # 규칙은 nexus.ingest.external_metadata 가 갖는다(테스트 가능하도록 sink 밖으로 뺐다):
    # quarantined 엔 아무것도 쓰지 않고, prov_inputs 는 멱등 히트에도 쓴다(재조정 백필).
    from nexus.ingest.external_metadata import apply_external_metadata

    await apply_external_metadata(
        rid, tenant, doc, idempotent=idempotent, quarantined=quarantined
    )

    return ExternalIngestOutcome(
        resource_rid=rid,
        labels=[EXTERNAL_LABEL],
        chunks_indexed=0 if idempotent else result.bm25_indexed,
        idempotent_hit=idempotent,
        source_hash=source_hash,
        quarantined=quarantined,
    )
