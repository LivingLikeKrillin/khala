"""답변 근거 청크마다 **검색 순위**를 단다 — 상위 k 안이면 몇 위, 필이면 `None`.

⛔ **왜 생겼나 (2026-10-01).** 융합 처치의 주 변수는 「기대 문서가 **상위 20** 에 드는가」다
(`docs/FUSION_DOCUMENT_AGREEMENT_PREREGISTRATION.md` §3). 그런데 응답의 근거 묶음은 상위 20 에
필 넷(섹션 필 · 참조 필 · 페어 문서 · 정정 확인 패스)을 더한 것이고, 소비자는 근거 묶음만 받는다.

- 기록으로 확인: 09-20 뒤 picasso 답변 질의 33개 중 **20개**에서 근거 묶음에 상위 20 밖의 문서가 있었다
- **`score` 로는 못 가른다** — 정정 확인 패스는 검색을 한 번 더 돌린 결과라 점수가 0 보다 크다

그래서 서버가 안다(`SearchResult.hits`) 것을 그대로 싣는다. 소비자가 다시 계산하면 답이 둘이 된다.
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
from nexus.search import evidence_packet  # noqa: E402
from nexus.search.hybrid import SearchHit, SearchResult  # noqa: E402

_TOKEN = "x" * 40
_AUTH = {"Authorization": "Bearer " + _TOKEN}


def _hit(rid: str, doc: str, title: str, score: float) -> SearchHit:
    return SearchHit(rid=rid, doc_rid=doc, doc_title=title, section_path="§1",
                     snippet=f"{title} 본문", chunk_text=f"{title} 본문", score=score)


def _result() -> SearchResult:
    r = SearchResult(route_used="hybrid_only")
    r.hits = [_hit("c1", "d1", "SOP-01", 0.05), _hit("c2", "d2", "운영 가이드", 0.04)]
    # 정정 확인 패스가 데려온 청크처럼 **점수가 있다** — 그래도 순위 출신이 아니다.
    r.fill = [_hit("c9", "d9", "벤더 노트", 0.03)]
    return r


class _Unconfigured:
    """키 없는 배포 — 스트림이 모델을 안 부르고 고정 안내로 끝나는 길."""

    configured = False


@pytest.fixture
def client(monkeypatch):
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
    monkeypatch.setattr(api, "LLMService", _Unconfigured)
    monkeypatch.setattr(api.db, "get_pool", _noop_async)
    monkeypatch.setattr(api, "PostgresGraphRepository", lambda *a, **k: None)
    monkeypatch.setattr(api, "_load_gazetteer", lambda *a, **k: {})
    monkeypatch.setattr(api, "_build_entity_patterns", lambda *a, **k: {})
    monkeypatch.setattr(api, "find_entities_in_text", lambda *a, **k: [])
    monkeypatch.setattr(api, "hybrid_search", _search)
    monkeypatch.setattr(evidence_packet, "statuses_for_chunks", _no_rows)
    monkeypatch.setattr(evidence_packet, "debts_for_docs", _no_rows)
    monkeypatch.setattr(api, "format_for_llm", lambda *a, **k: "")
    monkeypatch.setattr(api, "extract_signals", lambda *a, **k: None)
    monkeypatch.setattr(api, "record_search", _noop_async)

    saved = db._pool
    try:
        yield TestClient(api.app)
    finally:
        db._pool = saved


def _ranks(snippets) -> dict:
    return {s["chunk_rid"]: s["rank"] for s in snippets}


def test_a_ranked_snippet_carries_its_place_and_a_filled_one_carries_none(client):
    r = client.post("/search/answer", json={"query": "q", "evidence_only": True}, headers=_AUTH)
    assert r.status_code == 200, r.text

    assert _ranks(r.json()["data"]["evidence_snippets"]) == {"c1": 1, "c2": 2, "c9": None}


def test_the_narrating_answer_carries_it_too(client, monkeypatch):
    """답변 근거만 받는 버전에만 있으면 두 버전의 근거 묶음이 다른 모양이 된다."""
    async def _generate(*a, **k):
        return AnswerResult(answer="답", evidence_snippets=[{"chunk_rid": "c2"},
                                                            {"chunk_rid": "c9"}])

    monkeypatch.setattr(api, "generate_answer", _generate)

    r = client.post("/search/answer", json={"query": "q"}, headers=_AUTH)
    assert r.status_code == 200, r.text

    assert _ranks(r.json()["data"]["evidence_snippets"]) == {"c2": 2, "c9": None}


def test_the_stream_carries_it_too(client):
    """API 표면마다 다른 답변 근거를 보이면 안 된다 — 스트림의 `evidence` 이벤트에도 같은 필드가 있다."""
    r = client.post("/search/answer/stream", json={"query": "q"}, headers=_AUTH)
    assert r.status_code == 200, r.text

    events = [blk for blk in r.text.split("\n\n") if blk.startswith("event: evidence")]
    assert len(events) == 1, r.text
    payload = json.loads(events[0].split("data: ", 1)[1])
    assert _ranks(payload["evidence_snippets"]) == {"c1": 1, "c2": 2, "c9": None}
