"""읽기 범위 목록 — 기제만 (SPEC-nexus-tenant-read-scope, U1).

⛔ **이 SPEC 은 비평 3라운드에서 43건을 받았고 범위를 두 번 잘랐다.** 여기 있는 검사들은
그 라운드들이 잡은 자리에 하나씩 대응한다. 특히 **원소 둘 이상은 기동에서 막힌다** — 기제는
목록을 해소할 수 있게 만들어지지만, 조각별 clearance 판정이 없는 상태로 두 코퍼스를 열면
한 테넌트 어휘의 등급이 다른 테넌트 기준으로 해석된다 (3R I-002).
"""

from __future__ import annotations

import pytest

from nexus.auth.config import AuthConfig
from nexus.auth.principal import Principal
from nexus.auth.scope import effective_read_scope, effective_scope, resolve_read_scope
from nexus.search.scope_sql import normalize_scope, tenant_predicate


def _p(**kw):
    base = dict(name="x", tenant="default", clearance="INTERNAL")
    base.update(kw)
    return Principal(**base)


# ── 해소 규칙 (§3.2) ─────────────────────────────────────────────────────────

def test_no_list_behaves_exactly_like_today():
    """⛔ 회귀 없음의 뿌리 — 목록을 안 준 principal 은 오늘과 같은 하나를 본다."""
    assert resolve_read_scope(_p()) == (("default",), False)


def test_no_requested_tenant_gives_the_whole_scope():
    p = _p(read_tenants=("default", "design_docs"))
    assert resolve_read_scope(p) == (("default", "design_docs"), False)


def test_a_requested_tenant_inside_the_scope_narrows():
    p = _p(read_tenants=("default", "design_docs"))
    assert resolve_read_scope(p, "design_docs") == (("design_docs",), False)


def test_a_request_can_never_widen():
    """⛔ §2 에 남은 유일한 보장. 목록 밖 값은 범위를 넓히지 못한다."""
    p = _p(read_tenants=("default",))
    scope, out = resolve_read_scope(p, "design_docs")
    assert scope == ("default",)
    assert out is True


def test_out_of_scope_is_not_an_error():
    """존재 여부를 흘리지 않는다 — 오류가 아니라 조용한 축소 + 기록이다."""
    resolve_read_scope(_p(), "nonexistent")          # 예외가 아니어야 한다


def test_the_caller_can_tell_it_was_out_of_scope():
    """⛔ 3R I-010. 신호가 없으면 코퍼스 X 를 묻고 Y 로 답을 받고도 모른다."""
    _, out = resolve_read_scope(_p(), "somewhere-else")
    assert out is True


# ── 쓰기는 목록을 안 쓴다 (§4 I-5) ────────────────────────────────────────────

def test_writes_resolve_to_the_declared_tenant_never_a_list_element():
    """⛔ 3R I-001. 목록이 생기면 tenants[0] 로 고치는 것이 자연스럽고, 그것이
    ["design_docs", "default"] 인 principal 을 **엉뚱한 테넌트에 적재**시킨다."""
    p = _p(tenant="default", read_tenants=("default", "design_docs"))
    tenant, _ = effective_scope(p, requested_tenant="design_docs")
    assert tenant == "default"


def test_the_read_helper_keeps_the_same_clearance_rule():
    """등급 규칙을 갈라 두면 한쪽만 고쳐진다."""
    p = _p(clearance="INTERNAL")
    _, c_write = effective_scope(p, None, "PUBLIC")
    _, c_read, _ = effective_read_scope(p, None, "PUBLIC")
    assert c_write == c_read == "PUBLIC"


# ── SQL 술어 (§1.2) ──────────────────────────────────────────────────────────

def test_a_single_tenant_keeps_the_scalar_predicate():
    """⛔ 3R I-012. `= ANY($n)` 은 계획이 달라질 수 있다 — 목록 미설정 principal 의
    지연이 바뀌면 그것은 회귀다. 원소 하나면 오늘과 같은 술어를 낸다."""
    sql, val = tenant_predicate("c.tenant", 2, "default")
    assert sql == "c.tenant = $2"
    assert val == "default"


def test_multiple_tenants_use_any():
    sql, val = tenant_predicate("c.tenant", 2, ("a", "b"))
    assert sql == "c.tenant = ANY($2)"
    assert val == ["a", "b"]


def test_an_empty_scope_is_refused_rather_than_queried():
    """범위 없는 조회는 격리를 깬다 — 조용히 전부 보는 것보다 터지는 게 낫다."""
    with pytest.raises(ValueError):
        tenant_predicate("c.tenant", 1, ())


def test_a_plain_string_normalises():
    assert normalize_scope("a") == ("a",)
    assert normalize_scope(["a", "b"]) == ("a", "b")


# ── 기동 검사 (§3.1) ─────────────────────────────────────────────────────────

def _boot(read_tenants, tenant="default"):
    # `from_dict` 는 **전체 설정**을 받는다 (`auth` 키로 감싼다) — 이 자리를 처음에 틀렸다.
    cfg = AuthConfig.from_dict({"auth": {
        "mode": "permissive",
        "principals": [{"name": "p", "tenant": tenant, "clearance": "INTERNAL",
                        "read_tenants": read_tenants}],
    }})
    cfg.validate_startup()


def test_boot_refuses_a_tenant_outside_its_own_read_list():
    """⛔ 1R I-001. 요청이 아니라 **설정이** 범위를 넓히는 자리."""
    with pytest.raises(RuntimeError, match="read_tenants"):
        _boot(["design_docs"], tenant="default")


def test_boot_refuses_duplicates_and_blanks():
    """⛔ 2R I-015. 조용한 오설정."""
    with pytest.raises(RuntimeError):
        _boot(["default", "default"])
    with pytest.raises(RuntimeError):
        _boot(["default", "  "])


def test_boot_refuses_more_than_one_tenant_in_u1():
    """⛔ **U1 의 안전장치** (3R I-002). 이것이 없으면 설정 한 줄로 등급 경계를 넘는다."""
    with pytest.raises(RuntimeError, match="clearance|등급"):
        _boot(["default", "design_docs"])


def test_boot_accepts_a_single_element_list():
    _boot(["default"])


def test_boot_accepts_no_list_at_all():
    """대조군 — 오늘의 설정이 그대로 통과해야 한다."""
    AuthConfig.from_dict({"auth": {"mode": "permissive", "principals": [
        {"name": "p", "tenant": "default", "clearance": "INTERNAL"}]}}).validate_startup()


def test_boot_does_not_ask_the_database_whether_the_tenant_exists():
    """⛔ 3R I-003. 기동을 DB **내용**에 의존시키면 비어 있는 신규 테넌트나 재적재 중
    재시작이 서비스를 죽인다. 오타는 범위 밖 요청 기록으로 잡는다."""
    _boot(["default"], tenant="default")          # DB 없이 통과해야 한다
