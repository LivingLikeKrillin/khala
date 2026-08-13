"""이력 배관 — 받고, 상한을 걸고, **버린다** (SPEC-nexus-multi-turn-retrieval §3.1, U2).

U2 는 동작을 바꾸지 않는다. 그래서 여기서 지키는 것은 두 가지뿐이다:

  1. 이력이 없으면 오늘과 **바이트 단위로 같다** (§4 I1). 배관이 조용히 무언가를 바꾸면
     U3 의 회귀가 어느 쪽에서 왔는지 못 가린다 — 그것이 배관과 행동을 나눈 이유 전부다.
  2. 상한은 **서버가** 걸고, 두 표면이 **같은 규칙**을 쓴다. 규칙이 두 벌이면 갈라진다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.api import app  # noqa: E402
from nexus.search import history as H  # noqa: E402

_TOKEN = "x" * 40
_AUTH = {"Authorization": "Bearer " + _TOKEN}


@pytest.fixture
def client(monkeypatch):
    """`test_search_route_api.py` 와 같은 이유로 풀을 되돌린다: TestClient 의 루프가 닫히면
    모듈 전역 asyncpg 풀은 죽은 손잡이가 되고, 다음 테스트가 그것을 집어 죽는다."""
    from nexus import db

    monkeypatch.setenv("NEXUS_DEV_TOKEN", _TOKEN)
    saved = db._pool
    try:
        yield TestClient(app)
    finally:
        db._pool = saved


def _turns(n: int, text: str = "안녕") -> list[dict]:
    return [{"role": "user" if i % 2 == 0 else "assistant", "content": text} for i in range(n)]


# ── 정본이 하나인가 ────────────────────────────────────────────────────────────

def test_the_limits_live_in_one_place():
    """HTTP 와 A2A 가 같은 상수를 읽는다. 두 벌이면 한쪽만 고쳐지고 그 차이는 안 적힌다."""
    assert H.MAX_TURNS == 8 and H.MAX_BYTES == 8 * 1024
    from nexus import api
    from nexus.a2a import server as a2a
    assert api.history_module is H and a2a.history_module is H


def test_bytes_are_counted_in_utf8_not_characters():
    """한국어는 글자당 3바이트다. 문자 수로 세면 상한이 조용히 3배가 된다."""
    korean = H.Turn(role="user", content="가" * 100)
    assert H.byte_size([korean]) == 300


def test_parse_rejects_a_shape_that_is_not_the_contract():
    with pytest.raises(H.MalformedHistory):
        H.parse("문자열")
    with pytest.raises(H.MalformedHistory):
        H.parse([{"role": "system", "content": "x"}])      # 낯선 역할
    with pytest.raises(H.MalformedHistory):
        H.parse([{"role": "user", "content": 3}])          # 문자열이 아님
    assert H.parse(None) == []
    assert H.parse([]) == []


def test_over_the_cap_raises_instead_of_silently_truncating():
    """조용한 절단은 클라이언트가 관측할 수 없다 — 맥락 절반이 사라진 것을 아무도 모른다."""
    with pytest.raises(H.HistoryTooLarge):
        H.parse(_turns(H.MAX_TURNS + 1))
    with pytest.raises(H.HistoryTooLarge):
        H.parse([{"role": "user", "content": "가" * (H.MAX_BYTES // 3 + 10)}])
    assert len(H.parse(_turns(H.MAX_TURNS))) == H.MAX_TURNS   # 경계는 통과한다


# ── HTTP 표면 ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", ["/search", "/search/answer"])
def test_history_is_accepted_by_both_search_endpoints(client, path, monkeypatch):
    """필드가 계약에 있다 — 없으면 422 로 튕긴다. U2 는 받는 것까지가 전부다."""
    r = client.post(path, json={"query": "결제", "route": "nope", "history": _turns(2)},
                    headers=_AUTH)
    # route 가 틀렸으므로 400 이다. **422 가 아니라는 것**이 이 시험이 보는 것: 400 은 요청이
    # 모델을 통과해 라우트 검증까지 갔다는 뜻이다.
    assert r.status_code == 400, r.text


@pytest.mark.parametrize("path", ["/search", "/search/answer"])
def test_too_much_history_is_413_not_500(client, path):
    """상한 초과는 **호출자 잘못**이다. 500 은 '우리 잘못' 이라는 뜻이라 여기선 거짓말이다."""
    r = client.post(path, json={"query": "결제", "history": _turns(H.MAX_TURNS + 1)},
                    headers=_AUTH)
    assert r.status_code == 413, r.text
    assert str(H.MAX_TURNS) in r.text          # 무엇이 상한인지 말해 준다


def test_a_malformed_history_is_a_client_error(client):
    r = client.post("/search", json={"query": "결제",
                                     "history": [{"role": "system", "content": "x"}]},
                    headers=_AUTH)
    assert r.status_code in (400, 413, 422), r.text
    assert r.status_code != 500


@pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"),
                    reason="NEXUS_TEST_DB_URL 필요 — 검색을 끝까지 태워야 '변화 0' 을 보인다")
def test_history_changes_nothing_about_the_search(client, monkeypatch):
    """**§4 I1.** 이력을 줘도 검색이 받는 인자는 이력이 없을 때와 같아야 한다.

    U2 의 약속은 '동작 변화 0' 이다. 그 약속을 문장이 아니라 검사로 박는다 — 배관이 조용히
    무언가를 바꾸면 U3 에서 회귀의 출처를 못 가린다.
    """
    from nexus.search.hybrid import SearchResult

    seen = []

    async def spy(*a, **k):
        seen.append({"query": k.get("query", a[0] if a else None),
                     "tenant": k.get("tenant"), "clearance": k.get("clearance"),
                     "route": k.get("route"), "top_k": k.get("top_k")})
        return SearchResult(hits=[], route_used="keyword_only", timing_ms={"total_ms": 1})

    monkeypatch.setattr("nexus.api.hybrid_search", spy)

    async def no_signal(*a, **k):
        return None
    monkeypatch.setattr("nexus.api.record_search", no_signal)

    body = {"query": "결제 서비스 토픽", "route": "keyword_only"}
    assert client.post("/search", json=body, headers=_AUTH).status_code == 200
    assert client.post("/search", json={**body, "history": _turns(4)},
                       headers=_AUTH).status_code == 200
    assert len(seen) == 2
    assert seen[0] == seen[1], "이력이 검색 인자를 바꿨다 — U2 는 동작을 바꾸지 않는다"


# ── A2A 표면 ──────────────────────────────────────────────────────────────────
#
# 에이전트 정문도 같은 규칙을 쓴다. 한 표면만 멀티턴이면 "기능 → HTTP 엔드포인트 →
# (웹·MCP·CLI)" 원칙이 깨지고, 상한이 표면마다 달라지면 그 차이는 아무 데도 안 적힌다.

from fastapi import FastAPI  # noqa: E402

from nexus.a2a.config import A2AConfig  # noqa: E402
from nexus.a2a.server import mount_a2a  # noqa: E402
from nexus.auth.principal import hash_token  # noqa: E402
from nexus.llm.answer import AnswerResult  # noqa: E402

_A2A_TOKEN = "history-token"
_A2A_PRINCIPAL = {"name": "ext-agent", "token_sha256": hash_token(_A2A_TOKEN),
                  "tenant": "acme", "clearance": "INTERNAL"}


def _grounded(query: str, tenant: str, clearance: str) -> AnswerResult:
    return AnswerResult(
        answer="ok",
        evidence_snippets=[{"chunk_rid": "c1", "doc_title": "D", "section_path": "S",
                            "source_uri": "git://d.md", "text": "근거", "score": 0.9}],
        provenance=[{"doc_rid": "d", "source_uri": "git://d.md", "source_version": "v1"}],
        route_used="vector",
    )


def _a2a_client() -> TestClient:
    app_ = FastAPI()
    mount_a2a(app_, A2AConfig(enabled=True, principals=[_A2A_PRINCIPAL]), answer_fn=_grounded)
    return TestClient(app_)


def _a2a_send(client: TestClient, *, history=None, text: str = "q"):
    meta = {"history": history} if history is not None else {}
    return client.post(
        "/a2a", headers={"Authorization": f"Bearer {_A2A_TOKEN}"},
        json={"jsonrpc": "2.0", "id": "r1", "method": "message/send",
              "params": {"message": {"role": "user", "messageId": "m1", "kind": "message",
                                     "metadata": meta,
                                     "parts": [{"kind": "text", "text": text}]}}},
    )


def test_a2a_accepts_history_in_metadata():
    r = _a2a_send(_a2a_client(), history=_turns(2))
    assert r.status_code == 200 and "error" not in r.json(), r.text


def test_a2a_rejects_too_much_history_with_invalid_params():
    r = _a2a_send(_a2a_client(), history=_turns(H.MAX_TURNS + 1))
    assert r.status_code == 200          # JSON-RPC 는 오류도 200 으로 싣는다
    err = r.json()["error"]
    assert err["code"] == -32602 and "history" in err["message"]


def test_a2a_history_does_not_leak_into_the_query():
    """**이력은 `parts` 가 아니라 `metadata` 로 온다.**

    `_extract_query` 는 text part 를 전부 이어 붙인다. 앞턴을 part 로 실으면 그것이 조용히
    질의에 섞이고, 그것이 곧 U2 의 '동작 변화 0' 을 깨는 모양이다. metadata 경로는 질의를
    건드리지 않아야 한다.
    """
    seen = []

    def spy(query: str, tenant: str, clearance: str) -> AnswerResult:
        seen.append(query)
        return _grounded(query, tenant, clearance)

    app_ = FastAPI()
    mount_a2a(app_, A2AConfig(enabled=True, principals=[_A2A_PRINCIPAL]), answer_fn=spy)
    c = TestClient(app_)

    _a2a_send(c, text="결제 토픽")
    _a2a_send(c, text="결제 토픽", history=[{"role": "user", "content": "앞턴 내용"}])
    assert seen == ["결제 토픽", "결제 토픽"], f"이력이 질의에 섞였다: {seen}"


# ── 답변자도 재작성된 질의를 본다 (SPEC §2·§4 I3) ───────────────────────────────
#
# 2026-08-13 라이브에서 잡혔다: 검색은 고쳐졌는데 답변자에게 **생략형 원문**이 갔고, 근거
# 5건을 손에 쥐고도 "'그건' 이 무엇을 가리키는지 파악하기 어렵습니다" 라고 답했다. 검색만
# 검사하는 그물은 이 결함을 통과시킨다.
#
# 이력을 프롬프트에 넣는 것과 혼동하지 마라 — 들어가는 것은 **질의 하나**다. I3 은 그대로다.

@pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"),
                    reason="NEXUS_TEST_DB_URL 필요 — 답변 경로를 끝까지 태워야 한다")
def test_the_answerer_receives_the_rewritten_query_not_the_ellipsis(client, monkeypatch):
    from nexus.llm.answer import AnswerResult
    from nexus.search.hybrid import SearchHit, SearchResult

    async def one_hit(*a, **k):
        return SearchResult(hits=[SearchHit(rid="c1", doc_rid="d1", doc_title="문서",
                                            chunk_text="근거 본문", score=0.9)],
                            route_used="keyword_only", timing_ms={"total_ms": 1})
    monkeypatch.setattr("nexus.api.hybrid_search", one_hit)

    async def no_signal(*a, **k):
        return None
    monkeypatch.setattr("nexus.api.record_search", no_signal)

    async def fake_rewrite(query, history, llm_svc, **kw):
        return "로그인 정책은 어디에 적혀 있어?"
    monkeypatch.setattr("nexus.api.rewrite_query", fake_rewrite)

    seen = {}

    async def spy_answer(query, packet, **kw):
        seen["query"] = query
        return AnswerResult(answer="답", evidence_snippets=[], provenance=[],
                            route_used="keyword_only")
    monkeypatch.setattr("nexus.api.generate_answer", spy_answer)

    r = client.post("/search/answer",
                    json={"query": "그럼 그건 어디에 적혀 있어?", "route": "keyword_only",
                          "history": _turns(2)},
                    headers=_AUTH)
    assert r.status_code == 200, r.text
    assert seen["query"] == "로그인 정책은 어디에 적혀 있어?", (
        "답변자가 생략형 원문을 받았다 — 근거를 쥐고도 무엇을 묻는지 모른다고 답하게 된다")


@pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"),
                    reason="NEXUS_TEST_DB_URL 필요")
def test_without_history_the_answerer_gets_the_query_unchanged(client, monkeypatch):
    """§4 I1. 이력이 없으면 재작성도 없고, 답변자가 받는 것은 오늘과 같다."""
    from nexus.llm.answer import AnswerResult
    from nexus.search.hybrid import SearchResult

    async def empty(*a, **k):
        return SearchResult(hits=[], route_used="keyword_only", timing_ms={"total_ms": 1})
    monkeypatch.setattr("nexus.api.hybrid_search", empty)

    async def no_signal(*a, **k):
        return None
    monkeypatch.setattr("nexus.api.record_search", no_signal)

    seen = {}

    async def spy_answer(query, packet, **kw):
        seen["query"] = query
        return AnswerResult(answer="답", evidence_snippets=[], provenance=[],
                            route_used="keyword_only")
    monkeypatch.setattr("nexus.api.generate_answer", spy_answer)

    client.post("/search/answer", json={"query": "로그인 정책", "route": "keyword_only"},
                headers=_AUTH)
    assert seen["query"] == "로그인 정책"
