"""모르는 요청 칸은 **거절한다** — 200 과 함께 조용히 버리지 않는다.

⛔ **이 파일의 앞판은 반대를 적고 있었다** (`..._is_dropped_in_silence.py`, 2026-09-23).
그날 나는 결함 하나를 **틀리게 보고했다.**

기계로 「기본 인자를 안 넘기는 호출부」를 세다가 `api.py` 의 `/search` 가
`_search_channels(..., identifiers=…)` 를 안 넘기는 것을 봤다. 거기까지는 참이다. 그런데
**「요청 모델이 셋을 공유하니 호출자가 `/search` 에도 켤 수 있다」고 이어 붙였고, 그것이
틀렸다** — `identifier_channel` 은 `AnswerRequest` 의 칸이고 `/search` 는 `SearchRequest` 를
받는다. **그 라우트는 그 깃발을 받은 적이 없다.** 오보로 결재까지 받았고, 구현이
`req.identifier_channel` 을 읽어 매 요청에 `AttributeError` 를 낼 뻔했다.

⭐ **증상은 그대로 참이었고 기제가 더 넓었다.** 켜서 보내면 200 이 오고 아무 일도 안 난다 —
다만 버리는 것은 그 라우트가 아니라 **pydantic 의 기본값**(`extra="ignore"`)이다. ⇒ 자리는
한 라우트의 한 깃발이 아니라 **요청 모델 전부**였다.

⚠ **왜 그때는 안 고쳤나.** 리포 안 파급이 0이었지만 그것은 **밖의 호출자에 대한 계약
변경**이고, 결재받은 것(라우트 하나의 깃발 하나)과 다른 결정이었다. 그래서 그날은 사실만
적어 두고 소유자에게 올렸다. 이 파일은 그 결정이 난 뒤의 판이다.

⭐ **무엇이 결정을 만들었나.** 가정이 아니라 **소비자가 자기 소스에 적어 둔 것**이다. 설명 층
클라이언트 머리말이 우리 표면 하나를 덫으로 적고 우회한다 — *"켜서 보내면 200 이 오는데
처치는 안 걸린다 … 응답에 실리지도 않아서 버려졌다는 것을 알 방법이 없다."* 422 면 그 덫이
없어진다.

⚠ **되울림을 대신하지 않는다.** 이것이 잡는 것은 *모르는 이름*뿐이다. 이름이 멀쩡한데 값이
안 먹은 것은 여전히 응답이 말해야 잡힌다 — 둘은 같은 이음매의 반대쪽 반이고, 서로 대신
못 한다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from nexus import api
from nexus.api import AnswerRequest, ExplainRequest, NexusResponse, SearchRequest, Turn

#: 요청을 받는 모델 전부. **정책이 갈리면 그 자체가 결함이다** — 같은 API 의 두 표면이 모르는
#: 칸을 다르게 다루면, 호출자는 한쪽에서 통과한 오타를 다른 쪽에서 422 로 만난다.
REQUEST_MODELS = tuple(
    obj for obj in vars(api).values()
    if isinstance(obj, type) and issubclass(obj, api.RequestModel)
    and obj is not api.RequestModel
)

_TOKEN = "x" * 40
_AUTH = {"Authorization": "Bearer " + _TOKEN}


def test_the_treatment_flag_is_not_a_field_of_the_search_request():
    """⛔ **내 오보의 핵심이 이것이다.** 「받아 놓고 버린다」가 아니라 **받은 적이 없다.**"""
    assert "identifier_channel" not in SearchRequest.model_fields
    assert "identifier_channel" in AnswerRequest.model_fields


# ── 모델 층 ─────────────────────────────────────────────────────────────────

def test_sending_it_to_search_is_now_refused():
    """⭐ **앞판이 단언하던 것의 반대다.** 그때는 조용히 버려지는 것이 사실이었다."""
    with pytest.raises(ValidationError) as e:
        SearchRequest(query="무엇이든", identifier_channel=True)

    assert "identifier_channel" in str(e.value), "무엇이 걸렸는지 말해야 고칠 수 있다"


@pytest.mark.parametrize("model", REQUEST_MODELS, ids=lambda m: m.__name__)
def test_every_request_model_refuses_what_it_does_not_know(model):
    """⚠ **한 깃발의 문제가 아니라 모델 전부의 성질이다.**

    오타(`identifier_channe`)든 낡은 깃발이든 이 표면에 없는 깃발이든 결과가 같아야 한다 —
    그리고 이제 그 결과는 **거절**이다.
    """
    assert model.model_config.get("extra") == "forbid"


def test_the_models_agree_with_each_other():
    """⛔ **갈리는 것이 조용한 것보다 나쁘다.**

    한쪽이 `forbid` 이고 다른 쪽이 `ignore` 면, 같은 오타가 한 표면에서는 422 이고 다른
    표면에서는 통과한다. 공통 기반 클래스 하나가 그것을 **구조적으로** 막는다 — 이 단언은
    누군가 모델 하나에 `model_config` 를 덮어썼을 때 운다.
    """
    policies = {m.model_config.get("extra") for m in REQUEST_MODELS}

    assert policies == {"forbid"}, f"요청 모델의 모르는 칸 정책이 갈렸다: {policies}"


def test_the_list_is_not_empty():
    """⚠ **대조군.** 위 둘은 목록이 비면 공짜로 초록이다 — 실제로 그렇게 통과하는 판이 있다."""
    assert len(REQUEST_MODELS) >= 10, f"요청 모델을 못 찾았다: {[m.__name__ for m in REQUEST_MODELS]}"


def test_the_response_wrapper_is_not_touched():
    """⛔ **응답에는 걸지 않는다.** 나가는 것을 거절하면 우리 잘못이 호출자 잘못으로 나간다."""
    assert NexusResponse.model_config.get("extra") in (None, "ignore")


def test_a_nested_turn_is_covered_too():
    """이력 한 턴도 요청 본문의 일부다 — 여기만 새면 같은 오타가 한 겹 아래에서 되살아난다."""
    assert Turn in REQUEST_MODELS

    with pytest.raises(ValidationError):
        Turn(role="user", content="안녕", speaker="누구")


# ── 라우트 층 ───────────────────────────────────────────────────────────────
#
# ⛔ **모델 설정을 읽는 검사는 라우트가 그 모델을 쓴다는 것을 증명하지 않는다.** 이 리포가
# 이미 적어 둔 실패다 — *"문자열은 그 코드가 돌았다는 것을 증명하지 않는다."* 그래서 실제로
# 친다.


@pytest.fixture
def client(monkeypatch):
    """DB 없이 **검증 단계**까지만 돌린다.

    422 는 본문 파싱에서 나므로 엔드포인트 본문이 돌 필요가 없다. 대조군(200 이 아니라
    **400**)도 같은 이유로 DB 앞에서 끝난다.
    """
    from nexus import db

    monkeypatch.setenv("NEXUS_DEV_TOKEN", _TOKEN)
    saved = db._pool
    try:
        yield TestClient(api.app)
    finally:
        db._pool = saved


@pytest.mark.parametrize("path", ["/search", "/search/answer", "/search/answer/stream"])
def test_an_unknown_field_is_refused_at_the_boundary(client, path):
    """⭐ **판을 한 번 돌리고 나서가 아니라 경계에서 안다.**"""
    r = client.post(path, json={"query": "무엇이든", "identifier_channe": True},
                    headers=_AUTH)

    assert r.status_code == 422, f"{path} → {r.status_code} {r.text[:120]}"
    assert "identifier_channe" in r.text, "무엇이 걸렸는지 응답이 말해야 한다"


@pytest.mark.parametrize("path", ["/search", "/search/answer", "/search/answer/stream"])
def test_a_known_field_is_still_accepted(client, path):
    """⚠ **음성 대조군 — 이게 없으면 「전부 422」인 판도 위 검사를 통과한다.**

    DB 가 없으니 200 까지는 못 간다. 대신 **422 가 아닌 것**을 단언한다: 없는 `route` 는
    400 이고(`_validate_route`), 그 400 은 본문 검증을 **지나쳤다**는 증거다.
    """
    r = client.post(path, json={"query": "무엇이든", "route": "nope"}, headers=_AUTH)

    assert r.status_code == 400, f"{path} → {r.status_code} {r.text[:120]}"
    assert "unknown_route" in r.text


def test_the_refusal_only_echoes_what_the_caller_sent(client):
    """⚠ **거절이 우리 쪽 사정을 흘리면 안 된다.**

    422 본문은 호출자가 보낸 칸 이름을 되울린다 — 그건 호출자 자신의 입력이다. 여기서
    확인하는 것은 그 밖의 것(아는 칸 목록·테넌트 이름)이 같이 나가지 않는다는 것이다.
    """
    r = client.post("/search", json={"query": "무엇이든", "wat": 1}, headers=_AUTH)

    assert r.status_code == 422
    assert "design_docs" not in r.text
    assert "classification_max" not in r.text
