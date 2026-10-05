"""답변 경로가 **검색 글과 질문을 따로** 받을 수 있다 (`search_text`).

⛔ **왜 생겼나 (2026-10-05).** 소비자(진단 · 설명 층)가 호출자 쪽 처치를 두 경로에서 측정했다.
물음을 뗀 짧은 글로 검색하면 근거가 좋아졌다(설명 경로 G3 통과 · 진단 경로 R01 이 SOP-01 을
받음). 그런데 그 글을 `query` 로 보내려면 물음을 `answer_context` 로 옮겨야 했고, 진단 경로에서
그 자리 옮김이 **답의 형식**(머리 줄 · 카드)을 깨뜨렸다 — D3 기각. 처치가 묶음이라 둘을 가를 수
없었다.

⭐ 그래서 칸을 나눈다 — **검색 쪽은 `search_text` 만, 답 쪽은 `query` 만** 본다. 그러면 검색은
짧은 글로 돌고, 프롬프트의 질문 자리는 오늘 그대로다.

이 파일이 지키는 것:

- 칸을 주면 원문 경로 · 식별자 채널 · 엔티티 · 경로 이름 · 묶음의 코드 값 맞추기가 그 글을 쓴다
- 칸을 주면 재작성기가 **돌지 않는다** — 재작성문이 답변 프롬프트의 질문 자리로 새기 때문이다
- 칸을 주면 답변 프롬프트 · 숫자 검증 · 충분성 판정자는 `query` 를 본다
- 안 주거나 비었거나 공백뿐이면 오늘과 같다
- 응답과 기록은 쓴 길이를 말한다(본문은 안 남긴다)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus import api  # noqa: E402
from nexus.llm.answer import AnswerResult  # noqa: E402
from nexus.llm.prompts import build_prompts  # noqa: E402
from nexus.search import evidence_packet  # noqa: E402
from nexus.search.confidence import Confidence  # noqa: E402
from nexus.search.hybrid import SearchHit, SearchResult  # noqa: E402
from nexus.search.signals import extract_signals  # noqa: E402

_TOKEN = "x" * 40
_AUTH = {"Authorization": "Bearer " + _TOKEN}

QUESTION = "이 사건에서 무엇을 권고해야 하나? 후보 중 하나를 골라라"
SEARCH = "PAYLOAD_LOST 재승인 절차 적용 범위"


def _req(**kw):
    return api.SearchAnswerRequest(query=QUESTION, **kw)


# ── 검색 쪽: 채널을 짓는 자리 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_search_runs_on_the_search_text():
    query, channels, rw = await api._search_channels(_req(search_text=SEARCH), llm_svc=None)

    assert query == SEARCH
    assert channels is None and rw is None, "식별자 채널을 안 켰으면 채널은 하나다 — 오늘과 같은 모양"


@pytest.mark.asyncio
async def test_identifier_tokens_come_from_the_search_text_not_the_question():
    """⚠ 토큰은 검색 글에서만 뽑는다 — 질문에만 있는 토큰은 검색에 안 쓰인다."""
    req = api.SearchAnswerRequest(query="SOURCE_MISSING 이면 무엇을 하나?", search_text=SEARCH)

    _, channels, _ = await api._search_channels(req, llm_svc=None, identifiers=True)

    by_name = {c.name: c.text for c in channels}
    assert by_name["original"] == SEARCH
    assert by_name["identifier"] == "PAYLOAD_LOST"


@pytest.mark.asyncio
async def test_the_rewriter_does_not_run_when_the_caller_wrote_the_search_text(monkeypatch):
    called = []

    async def _rewrite(*a, **k):
        called.append(a)
        raise AssertionError("검색 글을 받았는데 재작성기를 불렀다")

    monkeypatch.setattr(api, "rewrite_query", _rewrite)
    req = _req(search_text=SEARCH, history=[{"role": "user", "content": "앞 턴"},
                                            {"role": "assistant", "content": "앞 답"}])

    query, channels, rw = await api._search_channels(req, llm_svc=None)

    assert called == []
    assert (query, channels, rw) == (SEARCH, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("blank", [None, "", "   \n\t "])
async def test_without_a_search_text_the_question_is_searched_as_today(blank):
    query, channels, rw = await api._search_channels(_req(search_text=blank), llm_svc=None)

    assert (query, channels, rw) == (QUESTION, None, None)


# ── 엔드포인트 층 ───────────────────────────────────────────────────────────────

def _hit(rid: str, doc: str, title: str, score: float) -> SearchHit:
    return SearchHit(rid=rid, doc_rid=doc, doc_title=title, section_path="§1",
                     snippet=f"{title} 본문", chunk_text=f"{title} 본문", score=score)


def _result() -> SearchResult:
    r = SearchResult(route_used="hybrid_only")
    r.hits = [_hit("c1", "d1", "SOP-01", 0.05), _hit("c2", "d2", "운영 가이드", 0.04)]
    r.confidence = Confidence(top_distance=0.9, top_bm25=0.1)
    return r


class _Model:
    configured = True

    async def stream(self, system_prompt, user_prompt, usage_out=None):
        _SEEN["stream_prompts"] = (system_prompt, user_prompt)
        yield "답"


_SEEN: dict = {}


@pytest.fixture
def client(monkeypatch):
    """DB·임베딩·LLM 없이 **엔드포인트 본문**을 돌리고, 각 자리가 받은 글을 적어 둔다."""
    from nexus import db

    _SEEN.clear()
    monkeypatch.setenv("NEXUS_DEV_TOKEN", _TOKEN)

    async def _noop_async(*a, **k):
        return None

    async def _no_rows(*a, **k):
        return {}

    async def _search(*a, **k):
        _SEEN["search_query"] = k["query"]
        return _result()

    real_packet = api.packet_for_answer

    async def _packet(*a, **k):
        _SEEN["packet_question"] = k.get("question")
        k["pool"] = None                          # 코드 값 맞추기는 DB 를 안 간다
        return await real_packet(*a, **k)

    def _entities(text, patterns):
        _SEEN["entity_text"] = text
        return []

    async def _generate(*a, **k):
        _SEEN["generate"] = (k["query"], k["user_query"])
        return AnswerResult(answer="답")

    def _signals(result, answer, **kw):
        _SEEN["signals"] = kw
        return object()

    async def _record(sig, **kw):
        _SEEN["judge_query"] = getattr(kw.get("judge_input"), "query", None)
        _SEEN["retained"] = kw.get("query_text")

    monkeypatch.setattr(api, "_load_config", lambda *a, **k: {})
    monkeypatch.setattr(api, "embedding_service_from_config", lambda *a, **k: None)
    monkeypatch.setattr(api, "LLMService", _Model)
    monkeypatch.setattr(api.db, "get_pool", _noop_async)
    monkeypatch.setattr(api, "PostgresGraphRepository", lambda *a, **k: None)
    monkeypatch.setattr(api, "_load_gazetteer", lambda *a, **k: {})
    monkeypatch.setattr(api, "_build_entity_patterns", lambda *a, **k: {})
    monkeypatch.setattr(api, "find_entities_in_text", _entities)
    monkeypatch.setattr(api, "hybrid_search", _search)
    monkeypatch.setattr(api, "packet_for_answer", _packet)
    monkeypatch.setattr(api, "generate_answer", _generate)
    monkeypatch.setattr(evidence_packet, "statuses_for_chunks", _no_rows)
    monkeypatch.setattr(evidence_packet, "debts_for_docs", _no_rows)
    monkeypatch.setattr(api, "extract_signals", _signals)
    monkeypatch.setattr(api, "record_search", _record)

    saved = db._pool
    try:
        yield TestClient(api.app)
    finally:
        db._pool = saved


def _post(client, **body):
    r = client.post("/search/answer", json={"query": QUESTION, **body}, headers=_AUTH)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_search_reads_the_search_text_and_the_answer_reads_the_question(client):
    data = _post(client, search_text=SEARCH)

    assert _SEEN["search_query"] == SEARCH
    assert _SEEN["entity_text"] == SEARCH
    assert _SEEN["packet_question"] == SEARCH
    assert _SEEN["generate"] == (QUESTION, QUESTION), \
        "질문 자리에 검색 글이 새면 프롬프트가 「두 문장」 모양으로 바뀐다"
    assert _SEEN["judge_query"] == QUESTION
    assert _SEEN["retained"] == QUESTION, "질문 원문 보존은 질문이다 — 호출자가 쓴 검색 글이 아니다"
    assert data["search_text_len"] == len(SEARCH)


def test_the_record_gets_the_search_text_and_keeps_the_question(client):
    _post(client, search_text=SEARCH)

    assert _SEEN["signals"]["query"] == QUESTION, "query_sha256 은 계속 질문의 값이다"
    assert _SEEN["signals"]["search_text"] == SEARCH


@pytest.mark.parametrize("body", [{}, {"search_text": ""}, {"search_text": "  "}])
def test_without_it_every_place_reads_the_question_as_today(client, body):
    data = _post(client, **body)

    assert _SEEN["search_query"] == QUESTION
    assert _SEEN["packet_question"] == QUESTION
    assert _SEEN["generate"] == (QUESTION, QUESTION)
    assert _SEEN["signals"]["search_text"] is None
    assert data["search_text_len"] == 0


def test_the_stream_splits_the_same_way(client):
    r = client.post("/search/answer/stream",
                    json={"query": QUESTION, "search_text": SEARCH}, headers=_AUTH)
    assert r.status_code == 200, r.text

    assert _SEEN["search_query"] == SEARCH
    assert _SEEN["packet_question"] == SEARCH
    # 「오늘과 같다」는 **근거 자리를 뺀 나머지**다 — 근거는 검색 글로 찾은 것이라 같은 근거를
    # 넣고 견준다(지시문 · 질문 자리 · 자료 칸이 같은가).
    expected = build_prompts(QUESTION, _stream_evidence(), QUESTION,
                             weak_evidence=_result().confidence.weak)
    assert _SEEN["stream_prompts"] == expected, "스트림의 프롬프트가 질문만 보낸 오늘의 요청과 다르다"
    done = [json.loads(line[len("data: "):]) for block in r.text.split("\n\n")
            if block.startswith("event: done") for line in block.split("\n")
            if line.startswith("data: ")]
    assert done and done[0]["search_text_len"] == len(SEARCH)
    assert _SEEN["signals"]["search_text"] == SEARCH


def _stream_evidence() -> str:
    """스트림이 프롬프트에 실은 근거 — 같은 패킷을 같은 함수로 다시 만든다."""
    import asyncio

    from nexus.search.evidence_packet import assemble_packet, format_for_llm

    packet = asyncio.run(assemble_packet(_result().hits, None, ""))
    return format_for_llm(packet)


_SIG = {"path": "search_answer", "tenant": "t", "clearance": "INTERNAL", "query": QUESTION}


# ── 기록 ───────────────────────────────────────────────────────────────────────

def test_the_signal_keeps_length_and_hash_but_not_the_text():
    sig = extract_signals(_result(), None, search_text=SEARCH, **_SIG)

    assert sig.search_text_len == len(SEARCH)
    assert len(sig.search_text_sha256) == 64
    assert SEARCH not in repr(sig)


def test_no_search_text_records_zero_and_empty():
    sig = extract_signals(_result(), None, **_SIG)

    assert (sig.search_text_len, sig.search_text_sha256) == (0, "")


def test_the_field_is_on_both_answer_surfaces_and_not_on_search():
    assert "search_text" in api.AnswerRequest.model_fields
    assert "search_text" in api.SearchAnswerRequest.model_fields
    assert "search_text" not in api.SearchRequest.model_fields


def test_the_prompt_is_today_s_when_the_question_alone_is_shown():
    """⭐ 질문 자리가 오늘과 같다는 것의 뜻 — `query == user_query` 면 한 문장 모양이다."""
    one = build_prompts(QUESTION, "근거", QUESTION)
    today = build_prompts(QUESTION, "근거", None)

    assert one == today

