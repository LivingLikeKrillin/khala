"""알 수 없는 `route` 는 400 이다 — SPEC-nexus-search-recall §5, §6.

500 은 "우리 잘못" 이라는 뜻이다. 존재하지 않는 route 를 고른 것은 호출자의 잘못이고,
그 사실을 알려 주어야 다음 호출을 고칠 수 있다. 지금은 스택트레이스가 detail 로 나간다.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from nexus.api import app


@pytest.fixture
def client(monkeypatch):
    """DB·Ollama 없이 라우팅 검증만 한다.

    `TestClient` 는 자기 이벤트 루프에서 요청을 돌리고, 그 안에서 만들어진 asyncpg 풀이
    모듈 전역 `db._pool` 에 남는다. 루프가 닫히면 그 풀은 죽은 손잡이가 되고, 다음 테스트가
    그것을 집어 `RuntimeError: Event loop is closed` 로 죽는다 — 실제로 그렇게 죽였다.
    끝나면 되돌린다.
    """
    from nexus import db

    monkeypatch.setenv("NEXUS_DEV_TOKEN", "x" * 40)
    saved = db._pool
    try:
        yield TestClient(app)
    finally:
        db._pool = saved


def test_an_unknown_route_is_a_client_error_not_a_server_error(client):
    r = client.post("/search", json={"query": "결제", "route": "nope"},
                    headers={"Authorization": "Bearer " + "x" * 40})
    assert r.status_code == 400, r.text
    body = r.json()
    detail = body.get("detail") or body.get("error") or ""
    assert "unknown_route" in detail
    assert "keyword_only" in detail          # 무엇을 고를 수 있는지 알려준다


@pytest.mark.parametrize("path", ["/search", "/search/answer", "/search/answer/stream"])
def test_every_search_endpoint_validates_the_route_before_touching_the_db(client, path):
    """DB 가 없는 환경에서 없는 route 가 503 으로 보고되면, 호출자는 자기 오타를 우리 장애로 읽는다.

    CI 의 무-DB 잡이 실제로 그렇게 붉었다. 검증은 첫 줄에 있어야 한다.
    """
    r = client.post(path, json={"query": "결제", "route": "nope"},
                    headers={"Authorization": "Bearer " + "x" * 40})
    assert r.status_code == 400, f"{path} → {r.status_code} {r.text[:80]}"
    assert "unknown_route" in r.json()["detail"]


# ── 0건의 원인은 **자기 엔드포인트**가 답한다 (2026-08-13 슬랙 파일럿) ─────────────

@pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"),
                    reason="NEXUS_TEST_DB_URL 필요 — /search 를 끝까지 태우려면 DB 가 있어야 한다")
def test_search_never_runs_the_visibility_query(client, monkeypatch):
    """검색 응답 조립은 DB 진단을 하지 않는다.

    이 검사가 지키는 것은 성능이 아니라 **스위트가 도는 것**이다. 같은 진단을 검색 경로에 얹은
    두 판이 전부 CI 를 매달았다: 죽은 이벤트 루프에 묶인 풀에서 커넥션이 열린 트랜잭션째 남아
    `documents` 락을 쥐었고, 뒤따르는 TRUNCATE 가 전부 그 뒤에 섰다.
    """
    from nexus.search.hybrid import SearchResult

    async def empty(*a, **k):
        return SearchResult(hits=[], route_used="keyword_only", timing_ms={"total_ms": 1})
    monkeypatch.setattr("nexus.api.hybrid_search", empty)
    # 신호 기록은 DB 를 친다. 이 시험이 보는 것은 가시성 진단이 도는지이지 신호 적재가 아니다 —
    # 유닛 잡에는 DB 가 없고, 스텁하지 않으면 그 500 이 이 단언을 대신 실패시킨다.
    async def no_signal(*a, **k):
        return None
    monkeypatch.setattr("nexus.api.record_search", no_signal)

    ran = []

    async def tripwire(tenant, clearance):
        ran.append(1)
        return {"total": 0, "visible": 0, "newest": None, "sources": {}, "sample_titles": []}
    monkeypatch.setattr("nexus.api.visibility_counts", tripwire)

    r = client.post("/search", json={"query": "무엇이든", "route": "keyword_only"},
                    headers={"Authorization": "Bearer " + "x" * 40})
    assert r.status_code == 200, r.text
    assert ran == [], "검색이 가시성 진단을 돌렸다"
    assert "no_visible_documents" not in r.json()["data"]


def test_visibility_endpoint_separates_empty_from_invisible(client, monkeypatch):
    """`/visibility` 는 '문서가 없다' 와 '내 등급으로 안 보인다' 를 가른다.

    `/status` 의 `documents_count` 는 전역 수라 이 질문에 답하지 못한다 — 그 수를 보고 봇이
    "문서에서 못 찾았다" 고 답한 것이 이 엔드포인트가 생긴 이유다.
    """
    async def counts(tenant, clearance):
        return {"total": 116, "visible": 0, "newest": None, "sources": {}, "sample_titles": []}
    monkeypatch.setattr("nexus.api.visibility_counts", counts)

    r = client.get("/visibility", headers={"Authorization": "Bearer " + "x" * 40})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["documents_total"] == 116 and d["documents_visible"] == 0
    assert d["no_visible_documents"] is True


def test_visibility_of_an_empty_corpus_is_not_a_config_defect(client, monkeypatch):
    """문서가 아예 없으면 그것은 설정 결함이 아니라 빈 코퍼스다 — 고칠 사람이 다르다."""
    async def counts(tenant, clearance):
        return {"total": 0, "visible": 0, "newest": None, "sources": {}, "sample_titles": []}
    monkeypatch.setattr("nexus.api.visibility_counts", counts)

    r = client.get("/visibility", headers={"Authorization": "Bearer " + "x" * 40})
    assert r.json()["data"]["no_visible_documents"] is False


def test_visibility_requires_a_token(client):
    """열람 가능 문서 수는 **당신의** 범위다 — 무인증으로 남의 코퍼스 크기를 알려주지 않는다."""
    assert client.get("/visibility").status_code == 401
