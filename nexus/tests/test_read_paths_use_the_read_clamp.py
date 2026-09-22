"""읽기 엔드포인트가 **읽기용 클램프**로 범위를 정하는가 — 두 표면을 나란히 친다.

⛔ **이 파일이 생긴 이유.** `auth/scope.py` 에는 클램프가 둘이고 머리말이 용도를 갈라 적어
뒀다 — `effective_scope` 는 쓰기·관리용이라 **요청 tenant 를 아예 안 보고** `principal.tenant`
하나를 돌려주고, `effective_read_scope` 는 요청이 없으면 `read_scope` 전체를, 목록 안이면 그
하나로 좁힌다. 그런데 `/search/answer` 만 옮겨 갔고 **`/search` 는 쓰기용 클램프에 남아
있었다.** 결과가 둘이었다: 범위 안의 테넌트를 지목해도 조용히 무시됐고, `read_scope` 가
여럿이어도 그 엔드포인트만 언제나 하나만 봤다.

**그리고 그것을 잡는 검사가 하나도 없었다.** 범위가 넓어지는 쪽이 아니라 좁아지는 쪽이라
오류도 안 나고 응답도 정상이다 — 안 보이는 코퍼스와 없는 코퍼스가 화면에서 같아 보인다.

그래서 여기서는 **표면마다 같은 세 경우**를 친다. 한쪽만 고치면 다른 쪽에서 붉어진다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexus import api

_TOKEN = "u" * 40
_AUTH = {"Authorization": "Bearer " + _TOKEN}
_SCOPE = ("default", "design_docs")


class _Result:
    """`hybrid_search` 가 돌려주는 것 중 두 엔드포인트가 만지는 부분만."""

    def __init__(self):
        self.hits, self.graph, self.fill = [], None, None
        self.timing_ms, self.degraded = {}, False
        self.route_used, self.spans = "hybrid_only", None
        self.n_unknown_origin_time = None
        #: 응답 조립이 읽는 칸. 가짜가 실물의 칸을 안 들면 엔드포인트가 여기서 죽는다.
        self.excluded_doc_types = []
        self.identifier_channel = []
        #: 터진 보강 패스. ⭐ 이 칸이 빠지면 엔드포인트가 **500 으로 죽는다** — 대역이 실물을
        #: 안 따라간 것이 조용하지 않게 드러나는 자리라, 여기 손이 가는 것은 결함이 아니다.
        self.enrichment_failed = []
        from nexus.search.confidence import Confidence
        self.confidence = Confidence()


@pytest.fixture
def seen(monkeypatch):
    """두 엔드포인트를 DB 없이 돌리고, `hybrid_search` 가 받은 범위를 붙잡는다."""
    from nexus import db

    monkeypatch.setenv("NEXUS_DEV_TOKEN", _TOKEN)
    monkeypatch.setenv("NEXUS_DEV_READ_TENANTS", ",".join(_SCOPE))
    monkeypatch.setenv("NEXUS_DEV_CLEARANCE_VERIFIED", "2026-09-18 tests")
    api.get_principal.cache_clear() if hasattr(api.get_principal, "cache_clear") else None

    captured: dict = {}

    async def _search(*a, **k):
        captured["tenant"] = k.get("tenant")
        return _Result()

    async def _noop_async(*a, **k):
        return None

    async def _generate(*a, **k):
        from nexus.llm.answer import AnswerResult
        return AnswerResult(answer="ok")

    monkeypatch.setattr(api, "hybrid_search", _search)
    monkeypatch.setattr(api, "generate_answer", _generate)
    monkeypatch.setattr(api, "_load_config", lambda *a, **k: {})
    monkeypatch.setattr(api, "embedding_service_from_config", lambda *a, **k: None)
    monkeypatch.setattr(api, "LLMService", lambda *a, **k: object())
    monkeypatch.setattr(api.db, "get_pool", _noop_async)
    monkeypatch.setattr(api, "PostgresGraphRepository", lambda *a, **k: None)
    monkeypatch.setattr(api, "_load_gazetteer", lambda *a, **k: {})
    monkeypatch.setattr(api, "_build_entity_patterns", lambda *a, **k: {})
    monkeypatch.setattr(api, "find_entities_in_text", lambda *a, **k: [])
    monkeypatch.setattr(api, "format_for_llm", lambda *a, **k: "")
    monkeypatch.setattr(api, "extract_signals", lambda *a, **k: None)
    monkeypatch.setattr(api, "record_search", _noop_async)

    saved = db._pool
    captured["client"] = TestClient(api.app)
    try:
        yield captured
    finally:
        db._pool = saved


def _post(seen, path, body):
    r = seen["client"].post(path, json=body, headers=_AUTH)
    assert r.status_code == 200, r.text
    return seen["tenant"]


PATHS = ["/search", "/search/answer"]


@pytest.mark.parametrize("path", PATHS)
def test_omitting_the_tenant_reads_the_whole_scope(seen, path):
    """⛔ **쓰기용 클램프를 쓰면 여기서 붉어진다** — 그 함수는 언제나 하나를 돌려준다.

    모델 기본값(`tenant="default"`)을 "요청했다" 로 읽어도 같이 붉어진다. 두 사고가 같은
    증상을 내므로 한 검사로 잡는다."""
    scope = _post(seen, path, {"query": "결제 승인 흐름"})
    assert tuple(scope) == _SCOPE, f"{path} 가 {scope} 로 좁혔다"


@pytest.mark.parametrize("path", PATHS)
def test_naming_a_tenant_in_scope_narrows_to_it(seen, path):
    """요청은 **좁힐 수만** 있다. 지목이 무시되면 운영자는 물은 코퍼스와 다른 곳의 답을 읽는다."""
    scope = _post(seen, path, {"query": "x", "tenant": "design_docs"})
    assert tuple(scope) == ("design_docs",)


@pytest.mark.parametrize("path", PATHS)
def test_a_tenant_outside_the_scope_falls_back_without_erroring(seen, path):
    """⛔ 오류를 내지 않는다 — 그 테넌트가 있는지조차 흘리지 않는다. 대신 principal 의
    테넌트로 떨어지고 호출부가 기록을 남긴다."""
    scope = _post(seen, path, {"query": "x", "tenant": "somebody_elses"})
    assert tuple(scope) == ("default",)


@pytest.mark.parametrize("path", PATHS)
def test_the_request_cannot_widen_the_scope(seen, path):
    """넓히기가 되면 클램프가 아니다. 범위 밖 지목이 범위를 늘리지 않는지 못박는다."""
    scope = _post(seen, path, {"query": "x", "tenant": "somebody_elses"})
    assert set(scope) <= set(_SCOPE)
