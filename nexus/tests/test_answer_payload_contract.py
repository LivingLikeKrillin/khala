"""`/search/answer` 응답에 **표면이 필요한 사실이 실려 있는가** — 엔드포인트를 실제로 돌려서.

`weak_evidence` 는 2026-08-18 부터 계산되고 있었지만(`search/confidence.py`) 응답에 실리지
않아서, 표면들은 *"잘 찾았다"* 와 *"제일 덜 나쁜 걸 골랐다"* 를 구별할 수 없었다. 서버 혼자
알고 프롬프트만 바꾼 것이다. 그 부류의 결함은 **payload 를 만드는 코드를 실행해야** 잡힌다 —
`AnswerResult` 에 필드가 있는지 묻는 검사는 이 구멍을 통과시킨다(실제로 통과시켰다).

그래서 여기서는 필드 하나가 아니라 **계약 전체**를 건다: 답변·기권·생성실패·적합도. 이 중
무엇이든 조용히 빠지면 어떤 표면인가는 그 사실을 표현할 방법이 없어진다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus import api  # noqa: E402
from nexus.llm.answer import AnswerResult  # noqa: E402
from nexus.search.confidence import Confidence  # noqa: E402

_TOKEN = "x" * 40
_AUTH = {"Authorization": "Bearer " + _TOKEN}


class _Search:
    """`hybrid_search` 가 돌려주는 것 중 엔드포인트가 만지는 부분만."""

    def __init__(self, confidence):
        self.hits, self.graph, self.fill = [], None, None
        self.timing_ms, self.degraded, self.confidence = {}, False, confidence


@pytest.fixture
def client(monkeypatch):
    """DB·임베딩·LLM 없이 **엔드포인트 본문**을 돌린다.

    풀을 되돌리는 이유는 `test_search_route_api.py` 와 같다(TestClient 의 루프가 닫히면
    모듈 전역 asyncpg 풀이 죽은 손잡이가 된다).
    """
    from nexus import db

    monkeypatch.setenv("NEXUS_DEV_TOKEN", _TOKEN)

    async def _noop_async(*a, **k):
        return None

    monkeypatch.setattr(api, "_load_config", lambda *a, **k: {})
    monkeypatch.setattr(api, "embedding_service_from_config", lambda *a, **k: None)
    monkeypatch.setattr(api, "LLMService", lambda *a, **k: object())
    monkeypatch.setattr(api.db, "get_pool", _noop_async)
    monkeypatch.setattr(api, "PostgresGraphRepository", lambda *a, **k: None)
    monkeypatch.setattr(api, "_load_gazetteer", lambda *a, **k: {})
    monkeypatch.setattr(api, "_build_entity_patterns", lambda *a, **k: {})
    monkeypatch.setattr(api, "find_entities_in_text", lambda *a, **k: [])
    monkeypatch.setattr(api, "assemble_packet", _noop_async)
    monkeypatch.setattr(api, "format_for_llm", lambda *a, **k: "")
    monkeypatch.setattr(api, "extract_signals", lambda *a, **k: None)
    monkeypatch.setattr(api, "record_search", _noop_async)

    saved = db._pool
    try:
        yield TestClient(api.app)
    finally:
        db._pool = saved


def _answer_with(monkeypatch, result: AnswerResult, confidence: Confidence):
    async def _search(*a, **k):
        return _Search(confidence)

    async def _generate(*a, **k):
        return result

    monkeypatch.setattr(api, "hybrid_search", _search)
    monkeypatch.setattr(api, "generate_answer", _generate)


def _post(client, query="정책 알려줘"):
    r = client.post("/search/answer", json={"query": query}, headers=_AUTH)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_a_weak_fit_reaches_the_client(client, monkeypatch):
    """서버만 아는 사실은 없는 사실이다 — 표면이 배지를 달려면 이 값이 나가야 한다."""
    _answer_with(monkeypatch, AnswerResult(answer="답", weak_evidence=True),
                 Confidence(top_distance=0.9, top_bm25=0.1))
    assert _post(client)["weak_evidence"] is True


def test_a_good_fit_is_reported_as_such(client, monkeypatch):
    """**가르는 값인지 먼저 확인한다.** 늘 참인 플래그는 신호가 아니다."""
    _answer_with(monkeypatch, AnswerResult(answer="답", weak_evidence=False),
                 Confidence(top_distance=0.2, top_bm25=4.0))
    assert _post(client)["weak_evidence"] is False


def test_the_payload_keeps_the_facts_a_surface_cannot_infer(client, monkeypatch):
    """이 넷은 답변 문장에서 되읽을 수 없다. 빠지면 표면은 추측하거나 침묵한다."""
    _answer_with(monkeypatch, AnswerResult(answer="답", abstained=True,
                                           abstain_reason="no_evidence"),
                 Confidence())
    data = _post(client)
    for key in ("answer", "abstained", "abstain_reason", "llm_failed", "weak_evidence"):
        assert key in data, f"{key} 가 응답에서 사라졌다"
