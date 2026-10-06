"""`/search/answer` 가 **생성 없이 근거 묶음만** 돌려줄 수 있다 (`evidence_only`).

⛔ **왜 생겼나 (2026-10-01).** 융합 처치(F1)의 주 변수는 검색만으로 정해진다
(`docs/FUSION_DOCUMENT_AGREEMENT_PREREGISTRATION.md` §3). 그런데 소비자가 가진 길은 생성까지
부르는 `/search/answer` 하나라, 두 버전에 세 시간 남짓과 생성 74건이 들었다. `/search` 는 생성을
안 하지만 **같은 검색이 아니다** — 식별자 채널 · 제외 종류 필드가 없어 422 이고, 기본 `top_k` 가
10 이고, 필 넷을 안 붙인다.

⭐ 그래서 **같은 처리기**에 필드 하나를 둔다. 처리기가 같아야 「같은 검색 · 같은 묶음」이 코드로
보장된다 — 따로 만든 엔드포인트는 언젠가 갈라지고, 갈라진 것은 측정이 아니다.

이 파일이 지키는 것:

- 켜면 모델을 **한 번도** 안 만진다 (재작성은 이력이 있을 때만 돈다 — 같은 검색이어야 하므로)
- 근거 묶음은 생성하는 버전과 **같은 코드**가 만든다
- 안 켜면 오늘과 같다
- 생성이 내는 필드는 0 · False 가 아니라 **None** 이다 — 「인용 0건」·「실패 안 함」으로 읽히면 안 된다
- 기록에서 답변과 **갈라** 적고, 판정자(LLM)도 안 부른다
- 스트림에는 필드가 없다 — 생성을 건너뛰는 스트림은 뜻이 없고, 알 수 없는 필드는 422 다
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus import api  # noqa: E402
from nexus.llm.answer import AnswerResult, generate_answer  # noqa: E402
from nexus.search import evidence_packet  # noqa: E402
from nexus.search.confidence import Confidence  # noqa: E402
from nexus.search.evidence_packet import assemble_packet  # noqa: E402
from nexus.search.hybrid import SearchHit, SearchResult  # noqa: E402
from nexus.search.spans import SpanSet  # noqa: E402

_TOKEN = "x" * 40
_AUTH = {"Authorization": "Bearer " + _TOKEN}

#: 생성이 내는 필드. 답변 근거만 받은 응답에서 이 필드들은 **측정 안 함(None)** 이어야 한다.
GENERATION_KEYS = ("answer", "citations", "unverified_citations", "unverified_numbers",
                   "numbers", "usage", "abstained", "abstain_reason",
                   "llm_failed", "llm_failure_reason")


#: `_NoModel` 이 만져진 기록. 시험마다 비운다.
_TOUCHED: list[str] = []


class _NoModel:
    """만지면 **기록된다** — 「생성을 안 한다」를 호출로 단언한다.

    ⛔ 예외만 던지면 안 된다. 생성 실패를 삼키는 것이 제품의 정책이라(`llm_failed`), 던진
    예외는 그 자리에서 「생성 실패」가 되고 시험은 초록으로 남는다 — 가드 검사를 일부러 깨 본
    버전에서 **실제로 그렇게 통과했다.** 그래서 기록을 남기고, 시험은 기록을 본다.
    """

    def __getattr__(self, name):
        _TOUCHED.append(name)
        raise AssertionError(f"근거만 요청인데 모델을 만졌다: {name}")


@pytest.fixture(autouse=True)
def _fresh_touch_record():
    _TOUCHED.clear()
    yield
    _TOUCHED.clear()


class _FakeModel:
    """생성하는 버전의 대조군 — 고정 답을 낸다."""

    configured = True

    async def generate_full(self, system_prompt, user_prompt):
        usage = SimpleNamespace(input_tokens=1, output_tokens=1, cost_usd=0.0, model="fake")
        return SimpleNamespace(text="답 [출처: SOP-01 §1]", usage=usage)


def _hit(rid: str, doc: str, title: str, score: float) -> SearchHit:
    return SearchHit(rid=rid, doc_rid=doc, doc_title=title, section_path="§1",
                     snippet=f"{title} 본문", chunk_text=f"{title} 본문", score=score)


def _result() -> SearchResult:
    """상위 k 둘 + 필 하나. 필은 정정 확인 패스처럼 **점수가 있다**."""
    r = SearchResult(route_used="hybrid_only")
    r.hits = [_hit("c1", "d1", "SOP-01", 0.05), _hit("c2", "d2", "운영 가이드", 0.04)]
    r.fill = [_hit("c9", "d9", "벤더 노트", 0.03)]
    r.confidence = Confidence(top_distance=0.9, top_bm25=0.1)
    return r


# ── 답변 근거를 만드는 함수 계층 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_without_narration_the_evidence_is_built_and_the_model_is_never_touched():
    packet = await assemble_packet(_result().hits, None, "")   # tenant "" → DB 안 감

    r = await generate_answer("질의", packet, _NoModel(), narrate=False)

    assert _TOUCHED == [], f"모델을 만졌다: {_TOUCHED}"
    assert [s["chunk_rid"] for s in r.evidence_snippets] == ["c1", "c2"]
    assert r.citations == [] and not r.llm_failed


@pytest.mark.asyncio
async def test_the_bundle_is_the_one_the_answer_path_builds():
    """⭐ **같은 코드가 만든다** — 생성하는 버전과 근거 필드가 글자 그대로 같다."""
    res = _result()
    packet = await assemble_packet(res.hits, None, "", fill=res.fill)

    narrated = await generate_answer("질의", packet, _FakeModel(), confidence=res.confidence)
    bare = await generate_answer("질의", packet, _NoModel(), confidence=res.confidence,
                                 narrate=False)

    assert _TOUCHED == [], f"모델을 만졌다: {_TOUCHED}"
    assert bare.evidence_snippets == narrated.evidence_snippets
    assert bare.provenance == narrated.provenance
    assert (bare.n_stale, bare.weak_evidence) == (narrated.n_stale, narrated.weak_evidence)
    assert narrated.answer and not bare.answer, "대조군이 생성을 안 했다 — 비교가 성립 안 한다"


@pytest.mark.asyncio
async def test_the_answer_stage_is_recorded_as_not_run():
    """안 돈 단계도 남긴다 — 「꺼져 있었다」와 「돌았는데 0」은 다른 사실이다(`fired`)."""
    packet = await assemble_packet(_result().hits, None, "")
    spans = SpanSet(max_candidates=100)

    await generate_answer("질의", packet, _NoModel(), spans=spans, narrate=False)

    answer = [s for s in spans.spans if s.stage == "answer"]
    assert len(answer) == 1 and answer[0].fired is False


# ── 엔드포인트 계층 ───────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    """DB·임베딩·LLM 없이 **엔드포인트 본문**을 돌린다. 패킷 조립과 답변 근거 변환은 진짜다."""
    from nexus import db

    monkeypatch.setenv("NEXUS_DEV_TOKEN", _TOKEN)

    async def _noop_async(*a, **k):
        return None

    async def _no_rows(*a, **k):
        return {}

    async def _search(*a, **k):
        return _result()

    monkeypatch.setattr(api, "_load_config", lambda *a, **k: {})
    monkeypatch.setattr(api, "embedding_service_from_config", lambda *a, **k: None)
    monkeypatch.setattr(api, "LLMService", _NoModel)
    monkeypatch.setattr(api.db, "get_pool", _noop_async)
    monkeypatch.setattr(api, "PostgresGraphRepository", lambda *a, **k: None)
    monkeypatch.setattr(api, "_load_gazetteer", lambda *a, **k: {})
    monkeypatch.setattr(api, "_build_entity_patterns", lambda *a, **k: {})
    monkeypatch.setattr(api, "find_entities_in_text", lambda *a, **k: [])
    monkeypatch.setattr(api, "hybrid_search", _search)
    monkeypatch.setattr(evidence_packet, "statuses_for_chunks", _no_rows)
    monkeypatch.setattr(evidence_packet, "debts_for_docs", _no_rows)
    monkeypatch.setattr(api, "extract_signals", lambda *a, **k: None)
    monkeypatch.setattr(api, "record_search", _noop_async)

    saved = db._pool
    try:
        yield TestClient(api.app)
    finally:
        db._pool = saved


def _post(client, **body):
    r = client.post("/search/answer", json={"query": "정책 알려줘", **body}, headers=_AUTH)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_evidence_only_returns_the_bundle_without_generating(client):
    data = _post(client, evidence_only=True)

    assert _TOUCHED == [], f"근거만 요청인데 모델을 만졌다: {_TOUCHED}"
    assert data["evidence_only"] is True
    assert [s["chunk_rid"] for s in data["evidence_snippets"]] == ["c1", "c2", "c9"]
    assert data["searched_tenants"], "근거 말고 검색이 낸 사실도 그대로 나가야 한다"


def test_what_generation_would_say_is_not_measured_rather_than_zero(client):
    """⛔ 0 · False 로 두면 「인용 0건」·「생성 실패 안 함」으로 읽힌다 — 인용 0건은 지표다."""
    data = _post(client, evidence_only=True)

    for key in GENERATION_KEYS:
        assert key in data, f"{key} 가 응답에서 사라졌다 — 칸 모양은 같아야 한다"
        assert data[key] is None, f"생성을 안 했는데 {key} = {data[key]!r}"


def test_without_the_flag_the_model_is_called_as_today(client, monkeypatch):
    """⭐ **대조군.** 필드를 안 보내면 생성한다 — 기본값이 오늘이다."""
    calls = []

    async def _generate(*a, **k):
        calls.append(k.get("narrate", True))
        return AnswerResult(answer="답")

    monkeypatch.setattr(api, "generate_answer", _generate)
    monkeypatch.setattr(api, "LLMService", lambda *a, **k: object())
    monkeypatch.setattr(api, "format_for_llm", lambda *a, **k: "")

    data = _post(client)

    assert calls == [True], f"생성 판이 생성을 안 불렀다: {calls}"
    assert data["answer"] == "답" and data["evidence_only"] is False


def test_evidence_only_is_recorded_apart_from_answers_and_wakes_no_judge(client, monkeypatch):
    """답변 지표(인용 0건 비율 등)에 섞이면 안 된다 — 기록의 `path` 가 다르다.

    판정자는 LLM 을 부른다. 생성 없는 요청에서 그것이 돌면 이 필드를 만든 이유가 사라진다.
    """
    seen: dict = {}

    def _signals(result, answer, **kw):
        seen["answer"], seen["path"] = answer, kw["path"]
        seen["prompt_version"] = kw.get("prompt_version")
        return object()

    async def _record(sig, **kw):
        seen["judge_input"] = kw.get("judge_input")

    monkeypatch.setattr(api, "extract_signals", _signals)
    monkeypatch.setattr(api, "record_search", _record)

    _post(client, evidence_only=True)

    assert seen["path"] == "search_answer_evidence"
    assert seen["answer"] is None, "답이 없는데 답의 칸을 기록하면 0 이 적힌다"
    assert seen["judge_input"] is None, "생성 없는 요청이 판정자(LLM)를 깨웠다"
    assert seen["prompt_version"], "묶음을 만든 코드의 판은 그대로 남아야 한다"


def test_the_material_for_narration_is_not_used_when_nothing_is_narrated(client):
    """자료(`answer_context`)는 답변 프롬프트에만 들어간다 — 프롬프트가 없으면 안 쓴 것이다."""
    data = _post(client, evidence_only=True, answer_context="후보: A · B")

    assert data["answer_context_len"] == 0


def test_the_field_lives_only_where_it_works():
    """스트림 · 검색 전용 요청에는 필드가 없다. 거기 보내면 조용히 생성하지 않고 422 다."""
    assert "evidence_only" in api.SearchAnswerRequest.model_fields
    assert "evidence_only" not in api.AnswerRequest.model_fields
    assert "evidence_only" not in api.SearchRequest.model_fields
    with pytest.raises(ValidationError) as e:
        api.AnswerRequest(query="q", evidence_only=True)
    assert "evidence_only" in str(e.value)


def test_the_stream_refuses_it_at_the_boundary(client):
    r = client.post("/search/answer/stream",
                    json={"query": "정책 알려줘", "evidence_only": True}, headers=_AUTH)

    assert r.status_code == 422, r.text
    assert "evidence_only" in r.text
