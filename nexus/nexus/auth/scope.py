"""effective_scope — the single 'narrow-only' clamp.

The ONLY producer of the scope that may reach ``hybrid_search`` / ``base_filter``. Raw
request-supplied ``tenant`` / ``classification_max`` must never flow downstream; they pass
through here first.

⚠ **2026-08-31 — 요청 tenant 를 무시하던 성질은 없어졌다** (SPEC-nexus-tenant-read-scope §2).
옛 주석은 "요청의 tenant 는 무시된다" 였고, 이제 목록 안의 값이면 **좁히는 데 쓴다**. 남는
보장은 더 약한 하나다 — **요청은 좁힐 수만 있고 넓힐 수 없다.** 범위의 상한은 설정이 정하고
요청은 그 안에서만 움직인다. (비평 3R I-009 가 "성질을 없애지 않는다" 는 문장이 거짓임을 잡았다.)

부작용 하나: 오늘 임의의·낡은 ``tenant`` 값을 보내도 무해하던 호출부는, 목록이 생기는 순간
**결과가 조용히 좁아진다.**
"""

from __future__ import annotations

from .clearance import floor_public, min_level
from .principal import Principal


#: 범위 밖 테넌트가 요청됐다. **새 표를 만들지 않는다** — 로그 한 줄과 계수기다
#: (SPEC §3.2). 요청값은 호출자 입력이므로 이름만 남기고 질의 원문은 남기지 않는다.
OUT_OF_SCOPE_EVENT = "tenant_out_of_scope"


def resolve_read_scope(
    principal: Principal, requested_tenant: str | None = None,
) -> tuple[tuple[str, ...], bool]:
    """읽기 범위와 **범위 밖 요청이었는지**.

    | 요청 | 범위 |
    |---|---|
    | 없음 | ``read_scope`` 전체 |
    | 목록 안 | 그 하나로 좁힌다 |
    | 목록 밖 | ``principal.tenant`` 하나 + 두 번째 값 ``True`` |

    ⛔ 목록 밖이어도 **오류를 내지 않는다** — 그 테넌트가 있는지도 흘리지 않기 위해서다.
    대신 호출부가 두 번째 값으로 기록을 남기고, 응답에는 해소된 범위가 실린다. 그게 없으면
    호출자는 코퍼스 X 를 묻고 Y 로 답을 받고도 아무 신호를 못 받는다 (비평 3R I-010).
    """
    scope = principal.read_scope
    if requested_tenant is None:
        return scope, False
    if requested_tenant in scope:
        return (requested_tenant,), False
    return (principal.tenant,), True


def effective_scope(
    principal: Principal,
    requested_tenant: str | None = None,
    requested_clearance: str | None = None,
) -> tuple[str, str]:
    """옛 계약 — ``(tenant, clearance)`` 하나씩.

    **쓰기·수명주기·관리 표면이 이것을 계속 쓴다.** 읽기 경로는
    :func:`effective_read_scope` 로 옮긴다. 둘을 한 함수로 두면 목록이 쓰기 경로로
    새고, 그 사고는 화면에 안 보인다 (SPEC §4 I-5).
    """
    if requested_clearance is None:
        clearance = principal.clearance
    else:
        clearance = min_level(principal.clearance, floor_public(requested_clearance))
    return principal.tenant, clearance


def effective_read_scope(
    principal: Principal,
    requested_tenant: str | None = None,
    requested_clearance: str | None = None,
) -> tuple[tuple[str, ...], str, bool]:
    """읽기용 ``(tenants, clearance, out_of_scope)``.

    등급 규칙은 :func:`effective_scope` 와 **같은 것을 쓴다** — 갈라 두면 한쪽만 고쳐진다.
    """
    tenants, out = resolve_read_scope(principal, requested_tenant)
    _, clearance = effective_scope(principal, None, requested_clearance)
    return tenants, clearance, out
