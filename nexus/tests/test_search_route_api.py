"""알 수 없는 `route` 는 400 이다 — SPEC-nexus-search-recall §5, §6.

500 은 "우리 잘못" 이라는 뜻이다. 존재하지 않는 route 를 고른 것은 호출자의 잘못이고,
그 사실을 알려 주어야 다음 호출을 고칠 수 있다. 지금은 스택트레이스가 detail 로 나간다.
"""

from __future__ import annotations

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
