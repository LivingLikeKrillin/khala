"""답이 **자기가 무엇을 뒤졌는지** 말하는가.

⛔ **왜 생겼나 (실측 2026-09-03).** 설계 문서 122건이 `design_docs` 테넌트에 있는데, 웹·CLI 가
쓰는 principal(`local-dev`)의 읽기 범위는 `default` 하나였다. 그래서 설계 질문을 던지면
**정책 코퍼스만 본 답**이 확신 있게 나왔고, 사용자는 그것이 설계 문서를 본 답인 줄 읽었다.
근거 인용은 *어느 문서를 썼나*를 보여 주지만 *어느 코퍼스가 애초에 후보였나*는 어디에도 없었다.

그 사실을 알아내는 데 코드를 읽어야 했다 — 로그의 `read_scope` 는 1,083행이 비어 있었고 응답에는
아예 없었다. **답이 스스로 말하지 않으면, 답이 무엇 위에 섰는지는 매번 조사거리가 된다.**

⚠ **`out_of_scope` 는 여기 안 싣는다.** 범위 밖 테넌트를 물었다는 사실을 호출자에게 알리면
**그 테넌트의 존재가 새어 나간다**(`api.py` 1R I-009). 그건 운영자 로그로만 간다. 여기서 다루는
것은 호출자 자신의 범위와, 실제로 기여한 코퍼스뿐이다 — 둘 다 호출자가 이미 볼 수 있는 것이다.
"""

from __future__ import annotations

import pytest

from nexus.search.evidence_packet import EvidencePacket


def test_a_packet_carries_the_scope_it_was_built_for():
    """공유 이음매가 범위를 받는다 — 표면마다 붙이면 하나가 조용히 빠진다(외부 평가 F2)."""
    p = EvidencePacket(searched_tenants=["default", "design_docs"])
    assert p.searched_tenants == ["default", "design_docs"]


def test_a_packet_without_a_scope_says_nothing_rather_than_guessing():
    """모르면 비운다. 기본값으로 `default` 를 넣으면 **틀린 사실**을 답에 싣게 된다."""
    assert EvidencePacket().searched_tenants == []


def test_the_contributing_corpora_are_counted_from_the_packet_not_the_hits():
    """근거 점유율은 패킷에서 센다 — 히트만 세면 채운 절·짝 문서·정정 패스가 빠진다.

    (SPEC-nexus-design-corpus-cutover §5.3 이 같은 이유로 같은 자리를 고른다.)
    """
    from nexus.search.evidence_share import counts

    class _S:
        def __init__(self, t):
            self.tenant = t

    got = dict(counts([_S("default"), _S("design_docs"), _S("default")]))
    assert got == {"default": 2, "design_docs": 1}


def test_every_answer_surface_reports_the_scope():
    """표면 하나만 고치면 F2 가 그대로 재현된다 — **셋 다** 범위를 응답에 실어야 한다.

    소스 문자열이 아니라 **컴파일된 참조**를 본다. 서식이 바뀌어도 안 깨지고, 이름을 지운
    판에서는 깨진다.
    """
    from nexus import api

    surfaces = {
        "search_answer": api.search_answer,
        "search_answer_stream": api.search_answer_stream,
    }
    missing = [name for name, fn in surfaces.items()
               if "searched_tenants" not in _names(fn)]
    assert not missing, f"범위를 응답에 안 싣는 표면: {missing}"


def _names(func) -> set[str]:
    """이 함수와 **중첩 함수들**이 쓰는 이름과 문자열 상수 전부.

    스트리밍 핸들러는 응답 조립이 `event_stream()` 안에 있어서, 바깥 함수의 `co_names` 만
    보면 결함이 있는 판에서도 초록이다 — `test_answer_surfaces_share_the_seam` 이 같은 자리에서
    같은 이유로 중첩을 걷는다.

    ⛔ **상수를 걷는 줄이 죽어 있었다** (실측 2026-09-23). 원래 이랬다:

        out |= set(code.co_names) | set(code.co_consts and () or ())

    `co_consts and () or ()` 는 `co_consts` 가 무엇이든 **언제나 `()`** 다. 그래서 이 함수는
    `co_names`(속성·전역 이름)만 봤고, 응답 **키**는 한 번도 안 봤다.

    ⇒ 그 판정은 *"`packet.searched_tenants` 를 읽는가"* 였지 *"응답에 싣는가"* 가 아니다.
    읽어 놓고 안 싣는 표면은 통과한다 — 이 파일이 바로 아래에서 경고하는 그 구멍이고,
    가드가 **자기 경고에 걸려 있었다.** 응답 키는 딕셔너리 리터럴이라 `co_consts` 에만 있다.

    ⚠ **그리고 키는 낱개 상수가 아니다.** 상수 키만 있는 딕셔너리는 `BUILD_CONST_KEY_MAP`
    으로 컴파일되어 키 전부가 **튜플 상수 하나** 안에 들어간다. `isinstance(c, str)` 만
    보면 여전히 못 찾는다 — 고치는 김에 한 겹 들어간다.
    """
    seen: set = set()
    out: set[str] = set()
    stack = [func.__code__]
    while stack:
        code = stack.pop()
        if id(code) in seen:
            continue
        seen.add(id(code))
        out |= set(code.co_names)
        for c in code.co_consts:
            if isinstance(c, str):
                out.add(c)
            elif isinstance(c, (tuple, frozenset)):
                out |= {x for x in c if isinstance(x, str)}
            elif hasattr(c, "co_names"):
                stack.append(c)
    return out


# ── 이름이 아니라 **행동**을 건다 ────────────────────────────────────────────
#
# ⛔ 위의 표면 검사는 이름만 본다. 처음 판에서 이음매의 대입을 통째로 지워도 **한 검사도 안
# 깨졌다** — 표면은 여전히 `packet.searched_tenants` 를 읽고 있었고 그 값이 비었을 뿐이다.
# 이 리포가 이미 적어 둔 실패다: *"문자열은 그 코드가 돌았다는 것을 증명하지 않는다."*

async def test_the_seam_actually_fills_the_scope(monkeypatch):
    """공유 이음매가 범위를 **채우는지** 본다. 지우면 이 검사가 깨진다."""
    from nexus.search import reconcile

    class _R:
        hits: list = []
        graph = None
        fill: list = []

    packet = await reconcile.packet_for_answer(
        _R(), ["default", "design_docs"], "INTERNAL",
        config={"search": {}}, search=None, question=None, pool=None)
    assert packet.searched_tenants == ["default", "design_docs"]


async def test_a_single_tenant_string_still_becomes_a_list():
    """호출부 넷 중 옛 서명을 쓰는 곳이 남아 있다 — 문자열이 와도 목록으로 나가야 한다."""
    from nexus.search import reconcile

    class _R:
        hits: list = []
        graph = None
        fill: list = []

    packet = await reconcile.packet_for_answer(
        _R(), "default", "INTERNAL", config={"search": {}},
        search=None, question=None, pool=None)
    assert packet.searched_tenants == ["default"]


# ── 검색 전용 경로도 같은 사실을 내야 한다 ───────────────────────────────────
#
# ⛔ **여기는 보상 통제의 절반만 있었다** (실측 2026-09-23). `auth/scope.py` 의
# `resolve_read_scope` 는 범위 밖 요청에 **오류를 내지 않는** 이유를 자기 docstring 에 적어
# 뒀다 — 그 테넌트가 있는지를 흘리지 않으려고 일부러다. 그리고 그 대신을 같은 자리에 적었다:
# *"응답에는 해소된 범위가 실린다. 그게 없으면 호출자는 코퍼스 X 를 묻고 Y 로 답을 받고도
# 아무 신호를 못 받는다"*(비평 3R I-010).
#
# `/search` 는 `_scope` 를 계산해 **신호에만** 남기고 응답에는 안 실었다. 보상 통제가 없는
# 쪽에서 *"오류를 안 낸다"* 는 보안 결정이 아니라 그냥 침묵이다.

_TOKEN = "x" * 40
_AUTH = {"Authorization": "Bearer " + _TOKEN}


@pytest.fixture
def read_client(monkeypatch):
    """DB·임베딩·LLM 없이 `/search` **본문**을 돌린다.

    스텁 목록과 풀 되돌리기는 `test_answer_payload_contract` 와 같은 모양이다 —
    `TestClient` 의 루프가 닫히면 모듈 전역 asyncpg 풀이 죽은 식별자가 되고 다음 시험이
    그것을 집는다.
    """
    from fastapi.testclient import TestClient

    from nexus import api, db
    from nexus.search.hybrid import SearchResult

    monkeypatch.setenv("NEXUS_DEV_TOKEN", _TOKEN)

    async def _noop_async(*a, **k):
        return None

    async def _empty(*a, **k):
        return SearchResult(hits=[], route_used="keyword_only", timing_ms={"total_ms": 1})

    monkeypatch.setattr(api, "_load_config", lambda *a, **k: {})
    monkeypatch.setattr(api, "embedding_service_from_config", lambda *a, **k: None)
    monkeypatch.setattr(api, "LLMService", lambda *a, **k: object())
    monkeypatch.setattr(api.db, "get_pool", _noop_async)
    monkeypatch.setattr(api, "PostgresGraphRepository", lambda *a, **k: None)
    monkeypatch.setattr(api, "_load_gazetteer", lambda *a, **k: {})
    monkeypatch.setattr(api, "_build_entity_patterns", lambda *a, **k: {})
    monkeypatch.setattr(api, "find_entities_in_text", lambda *a, **k: [])
    monkeypatch.setattr(api, "extract_signals", lambda *a, **k: None)
    monkeypatch.setattr(api, "record_search", _noop_async)
    monkeypatch.setattr(api, "hybrid_search", _empty)

    saved = db._pool
    try:
        yield TestClient(api.app)
    finally:
        db._pool = saved


def test_the_read_surface_says_which_corpora_it_searched(read_client):
    """`/search` 응답에 범위가 실린다. **이름이 아니라 본문을 본다.**"""
    r = read_client.post("/search", json={"query": "무엇이든", "route": "keyword_only"},
                         headers=_AUTH)

    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert isinstance(data.get("searched_tenants"), list) and data["searched_tenants"], \
        f"범위가 응답에 없다: {sorted(data)}"


def test_it_reports_the_resolved_scope_not_what_the_request_asked_for(read_client, monkeypatch):
    """⛔ **요청을 되울리면 이 칸은 거짓말을 한다.**

    범위는 토큰이 정하고 요청은 좁히기만 한다(`auth/scope.py`). 그 둘이 **갈리는** 순간이
    이 칸이 필요한 유일한 순간이므로, 단언은 *"보낸 것과 같다"* 가 아니라 *"해소된 것과
    같다"* 여야 한다. 하나를 물었는데 둘이 해소되는 판을 일부러 만든다.
    """
    from nexus import api

    monkeypatch.setattr(api, "effective_read_scope",
                        lambda *a, **k: (("design_docs", "default"), "INTERNAL", False))

    r = read_client.post(
        "/search",
        json={"query": "무엇이든", "tenant": "design_docs", "route": "keyword_only"},
        headers=_AUTH)

    assert r.status_code == 200, r.text
    assert r.json()["data"]["searched_tenants"] == ["design_docs", "default"]


def test_the_surface_list_now_covers_the_read_path_too():
    """⚠ **표면 목록에서 빠지는 것이 이 파일이 막으려던 결함이다**(F2).

    위 `test_every_answer_surface_reports_the_scope` 는 **답변** 표면 둘만 본다. 검색 전용
    경로는 그 목록 밖이라 초록인 채로 비어 있었다 — 가드가 있는데 지킬 대상에서 빠지는 것이
    이 부류의 전형이다. 목록을 늘린다.
    """
    from nexus import api

    surfaces = {"search": api.search,
                "search_answer": api.search_answer,
                "search_answer_stream": api.search_answer_stream}
    missing = [n for n, fn in surfaces.items() if "searched_tenants" not in _names(fn)]
    assert not missing, f"범위를 응답에 안 싣는 표면: {missing}"
