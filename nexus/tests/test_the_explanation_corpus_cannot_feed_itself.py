"""설명 층의 산출이 **설명 층의 근거가 되지 않는다** — 기억이 아니라 천장으로.

⛔ **왜 생겼나 (실측 2026-09-23).** 설명 층(picasso-narrator)이 사건마다 낸 설명을 코퍼스로
되돌리기로 했다. 그러면 「LLM 산출이 LLM 근거가 되는 순환」이 열린다.

첫 제안은 **문서 종류로 빼는 것**이었다(`exclude_doc_types` 에 하나 더). 그러면 **빼는 쪽이
전부 기억해야 한다** — 이 코퍼스를 치는 것은 그 층만이 아니고(CLI·슬랙 봇·MCP·A2A), 하나라도
안 빼면 순환이 열리며 **그 누락은 조용하다.**

⇒ 테넌트로 갈랐다. 그러면 **안 보이는 것이 기본**이고 보려는 쪽만 지정한다.

⛔ **그런데 그것만으로는 안 샜을 뿐 안 막힌 것이다.** 범위를 정하는 것은 요청이 아니라
**토큰**이고(`auth/scope.py`), 한 토큰에 둘을 넣으면 *"사건 질의가 `tenant` 를 잊지 않는 것"*
에 안전이 걸린다. 그래서 신원을 둘로 갈랐다 — 사건 바퀴는 `narrator` 를 **못 보는 천장** 아래
돌고, 운영자 질의만 둘을 본다.

⭐ 이 파일이 지키는 것은 그 천장이다. 정본의 문장 그대로다:
*"요청은 좁힐 수만 있고 넓힐 수 없다. 범위의 상한은 설정이 정하고 요청은 그 안에서만 움직인다."*

⚠ **`served_corpora` 로는 이것을 표현할 수 없다.** 그 검사는 「선언된 코퍼스마다 **모든**
서빙 표면이 닿는가」를 묻는다. 여기서 필요한 것은 정반대 — **정확히 한 신원만 닿는가**다.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from nexus.auth.config import AuthConfig
from nexus.auth.principal import Principal
from nexus.auth.scope import resolve_read_scope

#: ⛔ **실물 `config.yaml` 을 읽는 파일이라 환경을 되돌린다.** `AuthConfig.from_dict` 는
#: `NEXUS_DEV_TOKEN` 등 env 를 함께 본다 — 안 격리하면 이 프로세스의 다른 검사가 다른
#: 신원 목록을 보게 된다. 이 리포는 그 모양에 이미 데였다(#503).
#: `test_auth_env_isolation.py` 가 이 선언을 **강제한다** — 빠뜨리자 그 자리에서 잡혔다.
pytestmark = pytest.mark.usefixtures("isolate_auth_env")

#: 이 테넌트를 읽어도 되는 신원. **이 집합 밖은 순환이다.**
MAY_READ_EXPLANATIONS = {"narrator-operator"}

EXPLANATION_TENANT = "narrator"
CONFIG = pathlib.Path(__file__).resolve().parents[1] / "config.yaml"


def _principal(name: str, scope: tuple[str, ...]) -> Principal:
    return Principal(name=name, tenant=scope[0], clearance="INTERNAL", read_tenants=scope)


# ── 천장 — 요청이 넓히지 못한다 ────────────────────────────────────────────────

def test_the_event_loop_cannot_reach_the_explanation_tenant_even_by_asking():
    """⛔ **이것이 핵심이다.** 사건 바퀴가 `tenant` 를 잊는 것이 아니라, **잊어도 안전한** 것.

    표현이 아니라 **행동**을 단언한다 — 설정에 뭐라고 적혀 있는지가 아니라 범위를 푸는
    함수가 무엇을 돌려주는지 본다.
    """
    events = _principal("narrator-events", ("picasso",))

    scope, out_of_scope = resolve_read_scope(events, EXPLANATION_TENANT)

    assert EXPLANATION_TENANT not in scope, "사건 바퀴가 제 산출을 근거로 볼 수 있다"
    assert scope == ("picasso",)
    assert out_of_scope is True, "범위 밖 요청이 기록에 안 남는다"


def test_forgetting_the_tenant_is_safe_for_the_event_loop():
    """⭐ **기억이 아니라 천장이라는 것의 실물.** 안 보내면 범위 전체인데 그 전체가 하나다."""
    events = _principal("narrator-events", ("picasso",))

    scope, out_of_scope = resolve_read_scope(events, None)

    assert scope == ("picasso",)
    assert out_of_scope is False
    assert EXPLANATION_TENANT not in scope


def test_the_operator_identity_does_reach_both():
    """대조군 — 막기만 하고 열지 못하면 그 코퍼스는 아무 값도 안 한다."""
    operator = _principal("narrator-operator", ("picasso", EXPLANATION_TENANT))

    scope, _ = resolve_read_scope(operator, None)

    assert set(scope) == {"picasso", EXPLANATION_TENANT}, \
        "운영자 질의가 사람 근거와 지난 설명을 **한 꾸러미에** 못 받는다"


def test_a_request_cannot_add_a_tenant_the_token_does_not_have():
    """⛔ **넓히기가 아예 불가능한지**를 여기서 본다. 이름을 지어내도 안 열린다."""
    events = _principal("narrator-events", ("picasso",))

    for asked in (EXPLANATION_TENANT, "default", "design_docs", "존재하지-않는-테넌트"):
        scope, _ = resolve_read_scope(events, asked)
        assert set(scope) <= {"picasso"}, f"{asked!r} 요청이 범위를 넓혔다"


# ── 이 배포 — 선언과 실물이 같은가 ────────────────────────────────────────────

@pytest.mark.skipif(not CONFIG.exists(), reason="이 배포에만 있는 파일")
def test_no_principal_outside_the_allow_list_can_read_the_explanations():
    """⭐ **`served_corpora` 가 못 하는 말을 여기서 한다.**

    그 검사는 「모든 서빙 표면이 닿는가」를 묻는다. 여기 필요한 것은 반대다 —
    **허용 목록 밖의 신원이 하나라도 닿으면 순환**이다. 범위를 넓히는 설정 변경은
    조용한데, 이 단언이 그 자리에서 운다.
    """
    auth = AuthConfig.from_dict(yaml.safe_load(CONFIG.read_text(encoding="utf-8")))

    reaching = {p["name"] for p in auth.principals
                if EXPLANATION_TENANT in (p.get("read_tenants") or [p.get("tenant")])}

    assert reaching <= MAY_READ_EXPLANATIONS, (
        f"설명 코퍼스를 읽을 수 있는 신원이 허용 목록 밖에 있다: "
        f"{sorted(reaching - MAY_READ_EXPLANATIONS)}"
    )


@pytest.mark.skipif(not CONFIG.exists(), reason="이 배포에만 있는 파일")
def test_the_event_identity_is_read_only():
    """⛔ **측정만 하는 층이 문서를 내릴 수 있으면 안 된다** (실측 2026-09-23).

    이 층은 그전까지 `local-dev` 를 빌려 썼고 그것은 `manage_documents` 를 들고 있다.
    제 신원을 주는 목적의 절반이 그것을 떼는 것이다.
    """
    auth = AuthConfig.from_dict(yaml.safe_load(CONFIG.read_text(encoding="utf-8")))
    events = next((p for p in auth.principals if p["name"] == "narrator-events"), None)

    assert events is not None, "이 배포에 사건 바퀴 신원이 없다"
    assert events.get("capabilities") == [], \
        f"측정 층이 권한을 들고 있다: {events.get('capabilities')}"
    assert events.get("read_tenants") == ["picasso"]


@pytest.mark.skipif(not CONFIG.exists(), reason="이 배포에만 있는 파일")
def test_the_explanation_identities_are_not_serving_surfaces():
    """⚠ **넣으면 그 검사가 빨개진다** — 그리고 그것은 결함이 아니다.

    `check_read_scope_per_surface.py` 는 「선언된 코퍼스마다 **모든** 서빙 표면이 닿는가」를
    본다. 이 신원들의 좁은 범위는 설계이므로 그 판정의 대상이 아니다.
    """
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    surfaces = set(cfg.get("auth", {}).get("serving_surfaces") or [])

    assert not (surfaces & {"narrator-events", "narrator-operator"}), \
        "설명 층 신원이 서빙 표면으로 선언됐다 — 커버리지 검사가 모든 코퍼스를 요구한다"
