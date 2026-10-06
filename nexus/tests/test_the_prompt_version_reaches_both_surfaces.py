"""프롬프트 버전이 **두 답변 API 표면의 응답**에 실리고, **기록과 같은 값**인가 — 엔드포인트를 실제로 돌려서.

⛔ **왜 생겼나 (2026-09-27, 설명 레이어 자문).** 버전은 `search_log` 에만 있었고 응답에는 없었다. 답을
받는 쪽은 *"이 답을 만든 프롬프트가 어제와 같은가"* 를 물을 방법이 없었다. 그리고 스트리밍 경로는
기록에조차 버전을 안 남겼다 — 그 경로는 `AnswerResult` 없이 기록하는데, 버전을 거기서만 읽었다.

⚠ 답변 근거가 0건인 질의로 돈다. 그래야 DB 없이 **실물 접합부**(`packet_for_answer`)와 실물 답변
경로(기권 분기)를 끝까지 태울 수 있다 — 버전은 LLM 을 불렀는가와 무관하게 실린다.
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
from nexus.llm import prompt_version as V  # noqa: E402

_TOKEN = "x" * 40
_AUTH = {"Authorization": "Bearer " + _TOKEN}


@pytest.fixture
def client_and_rows(monkeypatch):
    """DB·임베딩·LLM 없이 두 엔드포인트의 **본문**을 돌리고, 기록될 신호를 받아 적는다."""
    from nexus import db
    from nexus.search.hybrid import SearchResult

    monkeypatch.setenv("NEXUS_DEV_TOKEN", _TOKEN)
    rows: list = []

    async def _noop_async(*a, **k):
        return None

    async def _no_hits(*a, **k):
        return SearchResult(route_used="keyword_only", timing_ms={"total_ms": 1})

    async def _record(sig, *a, **k):
        rows.append(sig)

    class _LLM:
        configured = True     # 답변 근거 0건이면 부르지 않는다 — 불리면 검사가 틀린 경로를 탄 것이다

    monkeypatch.setattr(api, "_load_config", lambda *a, **k: {})
    monkeypatch.setattr(api, "embedding_service_from_config", lambda *a, **k: None)
    monkeypatch.setattr(api, "LLMService", lambda *a, **k: _LLM())
    monkeypatch.setattr(api.db, "get_pool", _noop_async)
    monkeypatch.setattr(api, "PostgresGraphRepository", lambda *a, **k: None)
    monkeypatch.setattr(api, "_load_gazetteer", lambda *a, **k: {})
    monkeypatch.setattr(api, "_build_entity_patterns", lambda *a, **k: {})
    monkeypatch.setattr(api, "find_entities_in_text", lambda *a, **k: [])
    monkeypatch.setattr(api, "hybrid_search", _no_hits)
    monkeypatch.setattr(api, "record_search", _record)

    saved = db._pool
    try:
        yield TestClient(api.app), rows
    finally:
        db._pool = saved


def test_the_answer_response_carries_the_version(client_and_rows):
    client, rows = client_and_rows
    r = client.post("/search/answer", json={"query": "정책 알려줘"}, headers=_AUTH)
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    assert data.get("prompt_version") == V.prompt_version(), "응답에 판이 없거나 다르다"
    assert [row.prompt_version for row in rows] == [data["prompt_version"]], \
        "기록된 판이 응답의 판과 다르다"
    _the_other_versions_ride_along(data, rows)


def _the_other_versions_ride_along(payload: dict, rows: list) -> None:
    """코퍼스 버전과 검색 스택 핑거프린트도 같은 자리에서 찍히고 같은 값이 기록된다(2026-09-30).

    ⚠ 이 받침은 DB 가 없다(풀 `None`) — 그래서 코퍼스 버전은 「모른다」(빈 문자열)가 **맞는 값**이다.
    DB 가 있을 때의 값은 `test_corpus_and_search_versions.py` 가 접합부에서 확인한다."""
    from nexus.search.versions import search_fingerprint

    assert payload.get("search_fingerprint") == search_fingerprint({}), "검색 스택 지문이 안 실렸다"
    assert payload.get("corpus_version") == "", "DB 없이 코퍼스 판을 지어냈다"
    (row,) = rows
    assert (row.search_fingerprint, row.corpus_version) == \
        (payload["search_fingerprint"], payload["corpus_version"]), "기록이 응답과 다르다"


def test_the_streaming_response_carries_the_version(client_and_rows):
    """웹 채팅이 타는 경로다. 옛 버전은 이 경로의 버전을 **기록에도** 안 남겼다."""
    client, rows = client_and_rows
    done: dict = {}
    with client.stream("POST", "/search/answer/stream",
                       json={"query": "정책 알려줘"}, headers=_AUTH) as r:
        assert r.status_code == 200
        event = ""
        for line in r.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: ") and event == "done":
                done = json.loads(line[6:])

    assert done, "done 이벤트가 안 왔다"
    assert done.get("prompt_version") == V.prompt_version(), "스트림 done 에 판이 없거나 다르다"
    assert [row.prompt_version for row in rows] == [done["prompt_version"]], \
        "스트림 기록에 판이 안 남았거나 응답과 다르다"
    _the_other_versions_ride_along(done, rows)
