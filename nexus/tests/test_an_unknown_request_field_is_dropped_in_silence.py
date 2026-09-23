"""모르는 요청 칸은 **조용히 버려진다** — 지금 그렇다는 사실을 박아 둔다.

⛔ **왜 이 파일이 있나 (실측 2026-09-23).** 내가 결함 하나를 **틀리게 보고했다.**

기계로 「기본 인자를 안 넘기는 호출부」를 세다가 `api.py` 의 `/search` 가
`_search_channels(..., identifiers=…)` 를 안 넘기는 것을 봤다. 거기까지는 참이다. 그런데
**「요청 모델이 셋을 공유하니 호출자가 `/search` 에도 켤 수 있다」고 이어 붙였고, 그것이
틀렸다** — `identifier_channel` 은 `AnswerRequest` 의 칸이고 `/search` 는 `SearchRequest` 를
받는다. **그 라우트는 그 깃발을 받은 적이 없다.**

⚠ 그 오보로 「`/search` 는 400 으로 거절한다」를 소유자에게 올려 결재까지 받았고, 구현이
`req.identifier_channel` 을 읽어 **매 요청에 `AttributeError`** 를 낼 뻔했다. 검사가 그 자리에서
잡았다.

⭐ **증상은 그대로 참이다 — 기제만 달랐다.** 켜서 보내면 200 이 오고 처치는 안 걸리고
되울림도 없다. 다만 버리는 것은 내 라우트가 아니라 **pydantic 의 기본값**이다.

⇒ 그래서 실제 자리는 한 라우트의 한 깃발이 아니라 **요청 모델 전부**다. 오타든 낡은 깃발이든
모르는 칸은 전부 조용히 없던 일이 된다.

⚠ **고치지 않았다.** `extra="forbid"` 를 두 모델에 걸고 재 보니 **리포 안에서는 아무것도 안
깨진다**(2914 통과, 기준선 그대로). 그런데 그것은 **밖의 호출자에 대한 계약 변경**이고,
결재받은 것(라우트 하나의 깃발 하나)과 다른 결정이다. 소유자에게 수와 함께 올렸다.

이 파일은 **오늘의 사실을 적어 둔다.** 정책이 바뀌면 여기가 빨개지고, 그때 이 주석이 왜
바꿨는지를 묻는 자리가 된다.
"""

from __future__ import annotations

import pytest

from nexus.api import AnswerRequest, ExplainRequest, SearchRequest

#: 요청을 받는 모델들. **정책이 갈리면 그 자체가 결함이다** — 같은 API 의 두 표면이 모르는
#: 칸을 다르게 다루면, 호출자는 한쪽에서 통과한 오타를 다른 쪽에서 422 로 만난다.
REQUEST_MODELS = (SearchRequest, AnswerRequest, ExplainRequest)


def test_the_treatment_flag_is_not_a_field_of_the_search_request():
    """⛔ **내 오보의 핵심이 이것이다.** 「받아 놓고 버린다」가 아니라 **받은 적이 없다.**"""
    assert "identifier_channel" not in SearchRequest.model_fields
    assert "identifier_channel" in AnswerRequest.model_fields


def test_sending_it_to_search_is_dropped_rather_than_refused():
    """⭐ **증상은 참이다** — 보내도 아무 일이 없고 아무 말도 없다."""
    req = SearchRequest(query="무엇이든", identifier_channel=True)

    assert not hasattr(req, "identifier_channel"), "받았다면 이 파일의 전제가 바뀐다"


@pytest.mark.parametrize("model", REQUEST_MODELS, ids=lambda m: m.__name__)
def test_every_request_model_drops_the_unknown_in_silence(model):
    """⚠ **한 깃발의 문제가 아니라 모델 전부의 성질이다.**

    오타(`identifier_channe`)든 낡은 깃발이든 결과가 같다 — 200, 처치 없음, 신호 없음.
    """
    assert model.model_config.get("extra") in (None, "ignore"), \
        "정책이 바뀌었다 — 이 파일의 주석이 낡았으니 같이 고쳐라"


def test_the_models_agree_with_each_other():
    """⛔ **갈리는 것이 조용한 것보다 나쁘다.**

    한쪽이 `forbid` 이고 다른 쪽이 `ignore` 면, 같은 오타가 한 표면에서는 422 이고 다른
    표면에서는 통과한다. 바꿀 때 **같이** 바꿔야 한다는 것을 여기서 지킨다.
    """
    policies = {m.model_config.get("extra") or "ignore" for m in REQUEST_MODELS}

    assert len(policies) == 1, f"요청 모델의 모르는 칸 정책이 갈렸다: {policies}"
