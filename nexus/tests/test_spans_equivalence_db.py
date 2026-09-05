"""단계 span — 동치성 · 파괴 경로 · 비용 관측 (SPEC-nexus-stage-spans Unit 1, chunk 6).

세 가지를 한 파일에 묶는다. 셋 다 같은 재료(작은 픽스처 코퍼스 + 값싼 LLM 더블)를 쓴다:

1. **동치성** — `spans.enabled` 를 켜고 끄고 같은 질의를 돌려, 히트와 `search_log` 값이
   (생성 의존 칸을 빼고) **바이트 단위로 같은지** 본다. `test_spans_gate_db.py` 가 "캡처가
   맞는 것을 담는가" 를 본다면 이 시험은 "캡처가 **아무것도 안 건드리는가**" 를 본다 — 둘 다
   있어야 "관측 전용" 이라는 주장이 성립한다.
2. **파괴 경로** — span 저장을 실제 제약 위반으로 실패시켜, "배치가 유실됐다" 는 사실이
   `spans_expected IS NOT NULL AND search_span 행 0개` 라는 조합으로 **기록되는가**를 본다.
3. **비용 관측** — 요청당 후보·span 행 수를 세어 찍는다. 문턱도 단언도 없다.

**LLM 은 실제로 부르지만 값을 지어내지 않는다.** 이 리포의 기존 `_FakeLLM` 더블들(예:
`test_citation_validation.py`)은 전부 `Usage(None, None, None, "fake")` 를 돌려준다 —
무비용이라는 계약은 지키지만 토큰이 늘 `None` 이라 `prompt_tokens` 비교가 `None == None`
으로 항상 통과하는 공허한 검사가 된다. 여기 `_TokenCountingLLM` 은 같은 무비용 관례
(실 백엔드 호출 없음, `cost_usd=0.0` 고정)를 지키면서 토큰만 **프롬프트 길이의 결정적
함수**로 만든다 — 그래야 `prompt_tokens` 가 "캡처가 조립된 패킷을 건드리지 않았다" 는
실제 계약을 시험한다. 답변 문장 자체는 항상 같은 고정 문자열이다 — 생성은 재현 가능하지
않다는 사실을 시험이 우회하지 않는다(그래서 `completion_tokens`/`cost_usd`/인용 지표는
아래에서 여전히 비교 대상에서 뺀다: 이 더블이 우연히 결정적이라고 해서 일반 계약처럼
단언하지 않는다).
"""
from __future__ import annotations

import os

import pytest

from nexus import db
from nexus.index.bm25 import index_chunk_bm25
from nexus.llm.answer import generate_answer
from nexus.providers.llm import LLMResult, Usage
from nexus.rid import chunk_rid, doc_rid
from nexus.search.evidence_packet import assemble_packet
from nexus.search.hybrid import hybrid_search
from nexus.search.signals import extract_signals, record_search

pytestmark = pytest.mark.asyncio

_DB = os.getenv("NEXUS_TEST_DB_URL")
_TENANT = "spans_equiv_ut1"
_QUERY = "gizmo diagnostics report"
_DIM = 768

_DOCS = {
    "doc_a": "gizmo diagnostics report shows steady status across the fleet",
    "doc_b": "gizmo diagnostics summary and report notes for the week",
}
#: (dim0, dim1) — 순위 자체는 이 파일의 관심사가 아니다(`test_spans_gate_db.py` 가 이미
#: 본다). 둘이 갈리기만 하면 되고, 그래야 벡터 다리가 실제로 도는지가 보인다.
_QUERY_VEC = (1.0, 0.0)
_VECTORS = {"doc_a": (1.0, 0.1), "doc_b": (1.0, 0.4)}


def _vec(a: float, b: float) -> str:
    return "[" + ",".join(str(v) for v in [a, b] + [0.0] * (_DIM - 2)) + "]"


class _StubEmbedder:
    """벡터는 모델 호출이 아니라 고정 픽스처다 — 모델/차원이 바뀌어도 이 시험은 안 흔들린다."""

    async def embed_query(self, _text: str) -> list[float]:
        a, b = _QUERY_VEC
        return [a, b] + [0.0] * (_DIM - 2)


class _TokenCountingLLM:
    """무비용 더블이지만 토큰은 프롬프트 길이의 함수다 — 모듈 머리말 참조."""

    configured = True

    async def generate_full(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096):
        text = "근거를 확인했습니다."
        return LLMResult(
            text=text,
            usage=Usage(
                input_tokens=len(system_prompt) + len(user_prompt),
                output_tokens=len(text),
                cost_usd=0.0,
                model="fake-zero-cost",
            ),
        )


class _Chunk:
    def __init__(self, text: str):
        self.chunk_text, self.section_path, self.context_prefix = text, "root", None


@pytest.fixture(autouse=True)
async def _db_pool():
    """`test_spans_store_db.py` 와 같은 관례 — `nexus.db` 전역 풀을 직접 연다."""
    os.environ["DATABASE_URL"] = _DB or ""
    await db.get_pool()
    yield
    await db.close_pool()


async def _seed() -> dict[str, str]:
    rids: dict[str, str] = {}
    for key, text in _DOCS.items():
        uri = f"{_TENANT}:{key}.md"
        drid = doc_rid(uri)
        await db.execute(
            "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, title, status) "
            "VALUES ($1,$2,$3,'h','h',$4,'active')", drid, _TENANT, uri, key)
        crid = chunk_rid(drid, "root", 0)
        await db.execute(
            "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, chunk_text, section_path, "
            "chunk_index, status, hash) VALUES ($1,$2,$3,$4,$5,'root',0,'active','h')",
            crid, _TENANT, uri, drid, text)
        await index_chunk_bm25(crid, _Chunk(text))
        a, b = _VECTORS[key]
        await db.execute("UPDATE chunks SET embedding = $1::vector WHERE rid = $2", _vec(a, b), crid)
        rids[key] = crid
    return rids


async def _run_once(query_text: str, path: str, spans_enabled: bool, llm) -> tuple[object, object, dict]:
    """검색 → 패킷 조립 → 답변 → 신호 적재, 네 표면이 공유하는 것과 같은 순서(reconcile.py 참조)."""
    cfg = {"search": {}, "spans": {"enabled": spans_enabled, "max_candidates_per_span": 100}}
    result = await hybrid_search(
        query_text, tenant=_TENANT, clearance="INTERNAL", top_k=10,
        embedding_svc=_StubEmbedder(), route="hybrid_only", config=cfg)
    packet = await assemble_packet(
        result.hits, graph=result.graph, tenant=_TENANT, fill=result.fill,
        clearance="INTERNAL", spans=result.spans)
    answer = await generate_answer(
        query_text, packet, llm, route_used=result.route_used, timing_ms=result.timing_ms,
        confidence=result.confidence, spans=result.spans)
    sig = extract_signals(
        result, answer, path=path, tenant=_TENANT, clearance="INTERNAL",
        query=query_text, latency_ms=1)
    await record_search(sig, await_persist=True, spans=result.spans)
    row = await db.fetch_one(
        "SELECT * FROM search_log WHERE path = $1 ORDER BY id DESC LIMIT 1", path)
    return result, answer, dict(row)


# ── 1. 동치성 ────────────────────────────────────────────────────────────────

_PATH_ON = "test_spans_equiv_on"
_PATH_OFF = "test_spans_equiv_off"

#: 답변에서 유도되는 칸 — 생성은 재현 가능하지 않으므로 뺀다(작업 지시문의 명시 목록).
_EXCLUDE_ANSWER_DERIVED = {
    "latency_ms", "spans_expected", "completion_tokens", "cost_usd",
    "n_citations", "unverified_citations",
}
#: 행 신원·벽시계 칸 — 캡처 여부와 무관하게 매 실행 다르다. 작업 지시문의 목록에는 없지만
#: 빼지 않으면 `id`/`ts`/`sufficiency_at` 하나만으로 모든 실행이 "달라졌다" 고 나온다.
_EXCLUDE_STRUCTURAL = {"id", "ts", "sufficiency_at", "path"}


@pytest.mark.integration
async def test_capture_does_not_change_hits_or_search_log(clean_db):
    await _seed()
    try:
        llm = _TokenCountingLLM()
        result_on, _answer_on, row_on = await _run_once(_QUERY, _PATH_ON, True, llm)
        result_off, _answer_off, row_off = await _run_once(_QUERY, _PATH_OFF, False, llm)

        assert result_on.hits, "빈 히트로는 동치성을 증명하지 못한다"
        # SearchHit 은 (frozen 아닌) dataclass 라 필드별 값 비교가 기본이다 — 순서까지 본다.
        assert [h.rid for h in result_on.hits] == [h.rid for h in result_off.hits]
        assert result_on.hits == result_off.hits

        # prompt_tokens 는 진짜 검사다: `_TokenCountingLLM` 이 프롬프트 **길이의 함수**로 값을
        # 내므로, 캡처가 조립된 패킷을 한 글자라도 건드렸으면 이 값이 갈린다.
        assert row_on["prompt_tokens"] is not None
        assert row_on["prompt_tokens"] == row_off["prompt_tokens"]

        # spans_expected 는 캡처 여부 자체를 담는 칸이라 **다른 것이 계약**이다.
        assert row_on["spans_expected"] is not None
        assert row_off["spans_expected"] is None

        skip = _EXCLUDE_ANSWER_DERIVED | _EXCLUDE_STRUCTURAL
        keys = sorted(set(row_on) - skip)
        mismatches = {k: (row_on[k], row_off[k]) for k in keys if row_on[k] != row_off[k]}
        assert not mismatches, f"spans 를 켜고 끈 것만으로 search_log 값이 갈렸다: {mismatches}"
    finally:
        await db.execute("DELETE FROM search_log WHERE path = ANY($1::text[])", [_PATH_ON, _PATH_OFF])
        await db.execute("DELETE FROM documents WHERE tenant = $1", _TENANT)


# ── 2. 파괴 경로 ──────────────────────────────────────────────────────────────

_PATH_BROKEN = "test_spans_equiv_broken_write"


@pytest.mark.integration
async def test_a_broken_span_write_still_returns_the_answer_and_records_the_loss(clean_db):
    """span 저장을 **진짜로** 실패시킨다. `search_span` 의 부분 유니크 인덱스
    (`stage <> 'leg'` 인 stage 는 요청당 최대 1개, migration 040)를 fusion span 을 하나 더
    넣어 어긴다 — `test_spans_store_db.py::test_a_failing_batch_does_not_take_the_parent_with_it`
    와 같은 결함 재현 방식이다. monkeypatch 로 예외를 흉내내지 않는다: `span_store.py` 가
    실제로 잡는 예외 경로(제약 위반 → 자기 트랜잭션만 롤백)를 그대로 태운다.
    """
    await _seed()
    try:
        llm = _TokenCountingLLM()
        cfg = {"search": {}, "spans": {"enabled": True, "max_candidates_per_span": 100}}
        result = await hybrid_search(
            _QUERY, tenant=_TENANT, clearance="INTERNAL", top_k=10,
            embedding_svc=_StubEmbedder(), route="hybrid_only", config=cfg)
        assert result.spans is not None
        # 둘째 fusion → idx_search_span_singleton 위반. persist 시 배치 전체가 롤백된다.
        result.spans.add_fusion(candidates=[], rrf_k=60, n_channels=1)

        packet = await assemble_packet(
            result.hits, graph=result.graph, tenant=_TENANT, fill=result.fill,
            clearance="INTERNAL", spans=result.spans)
        answer = await generate_answer(
            _QUERY, packet, llm, route_used=result.route_used, timing_ms=result.timing_ms,
            confidence=result.confidence, spans=result.spans)
        # 답변 경로는 span 저장보다 **먼저** 끝난다 — 아래에서 저장이 실패해도 이 값은 이미 있다.
        assert answer.answer, "답변 경로가 값을 못 냈다"
        expected_spans = len(result.spans.spans)

        sig = extract_signals(
            result, answer, path=_PATH_BROKEN, tenant=_TENANT, clearance="INTERNAL",
            query=_QUERY, latency_ms=1)
        await record_search(sig, await_persist=True, spans=result.spans)   # 절대 raise 하지 않는다

        row = await db.fetch_one(
            "SELECT id, spans_expected FROM search_log WHERE path = $1 ORDER BY id DESC LIMIT 1",
            _PATH_BROKEN)
        assert row is not None, "search_log 행 자체가 안 써졌다 — 유실이 부모까지 끌고 내려갔다"
        assert row["spans_expected"] == expected_spans, "기대치는 저장 성공 여부와 무관하게 남아야 한다"

        span_rows = await db.fetch_val(
            "SELECT count(*) FROM search_span WHERE search_log_id = $1", row["id"])
        assert span_rows == 0, "제약 위반이 배치를 통째로 굴렸어야 한다 — 일부만 남으면 그게 더 나쁘다"
    finally:
        await db.execute("DELETE FROM search_log WHERE path = $1", _PATH_BROKEN)
        await db.execute("DELETE FROM documents WHERE tenant = $1", _TENANT)


# ── 3. 비용 관측 ──────────────────────────────────────────────────────────────

_PATH_COST_PREFIX = "test_spans_equiv_cost"
#: 픽스처 질의 셋 — 코퍼스가 둘 뿐이라 다양한 질의보다는 "요청당 몇 행이 쌓이는가" 를
#: 재현 가능하게 보이는 것이 목적이다.
_COST_QUERIES = [_QUERY, "gizmo status", "diagnostics notes for gizmo"]


@pytest.mark.integration
async def test_fixture_cost_observation(clean_db):
    """비용 관측 — **단언도 문턱도 없다.**

    ⚠ 여기서 찍는 수는 이 파일의 두 문서·세 질의 픽스처에서 나온 값이다. `spans.enabled`
    기본값은 false 라 라이브 행이 아직 없고, 그래서 "프로덕션에서 요청당 몇 행이 쌓이는가"
    를 지금 잴 방법이 없다 — 이 수를 그 답으로 인용하지 않는다.
    """
    await _seed()
    try:
        llm = _TokenCountingLLM()
        cfg = {"search": {}, "spans": {"enabled": True, "max_candidates_per_span": 100}}
        # ASCII 로만 찍는다 - 이 파일을 여는 셸의 코드페이지에 따라 em-dash 등
        # 비-ASCII 문자가 UnicodeEncodeError 를 낼 수 있다(레거시 코드페이지 콘솔에서 실측).
        print("\n[fixture cost observation - NOT a production measurement; "
              "spans.enabled defaults to false, so no live rows exist yet]")
        for i, q in enumerate(_COST_QUERIES):
            path = f"{_PATH_COST_PREFIX}_{i}"
            result = await hybrid_search(
                q, tenant=_TENANT, clearance="INTERNAL", top_k=10,
                embedding_svc=_StubEmbedder(), route="hybrid_only", config=cfg)
            packet = await assemble_packet(
                result.hits, graph=result.graph, tenant=_TENANT, fill=result.fill,
                clearance="INTERNAL", spans=result.spans)
            answer = await generate_answer(
                q, packet, llm, route_used=result.route_used, timing_ms=result.timing_ms,
                confidence=result.confidence, spans=result.spans)
            sig = extract_signals(
                result, answer, path=path, tenant=_TENANT, clearance="INTERNAL",
                query=q, latency_ms=1)
            await record_search(sig, await_persist=True, spans=result.spans)

            row = await db.fetch_one(
                "SELECT id FROM search_log WHERE path = $1 ORDER BY id DESC LIMIT 1", path)
            n_spans = await db.fetch_val(
                "SELECT count(*) FROM search_span WHERE search_log_id = $1", row["id"])
            n_candidates = await db.fetch_val(
                "SELECT count(*) FROM search_span_candidate c "
                "JOIN search_span s ON s.id = c.span_id WHERE s.search_log_id = $1", row["id"])
            print(f"[fixture] query={q!r} span_rows={n_spans} candidate_rows={n_candidates}")
    finally:
        await db.execute("DELETE FROM search_log WHERE path LIKE $1", f"{_PATH_COST_PREFIX}_%")
        await db.execute("DELETE FROM documents WHERE tenant = $1", _TENANT)
