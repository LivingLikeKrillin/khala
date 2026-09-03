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

def _boot(read_tenants, tenant="default", verified=None):
    # `from_dict` 는 **전체 설정**을 받는다 (`auth` 키로 감싼다) — 이 자리를 처음에 틀렸다.
    cfg = AuthConfig.from_dict({"auth": {
        "mode": "permissive",
        "principals": [dict({"name": "p", "tenant": tenant, "clearance": "INTERNAL",
                             "read_tenants": read_tenants},
                            **({"clearance_equivalence_verified": verified} if verified else {}))],
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


def test_boot_refuses_more_than_one_tenant_without_a_clearance_declaration():
    """⛔ **자물쇠** (3R I-002). 선언 없이는 설정 한 줄로 등급 경계를 넘는다."""
    with pytest.raises(RuntimeError, match="clearance_equivalence_verified"):
        _boot(["default", "design_docs"])


def test_a_recorded_clearance_comparison_opens_it():
    """선언이 있으면 열린다 — **자물쇠를 없앤 게 아니라 사람의 확인에 걸었다**
    (SPEC-nexus-design-corpus-cutover §4.3). 상한을 그냥 올리면 앞으로 어느 쌍에든
    검사가 사라진다."""
    _boot(["default", "design_docs"], verified="2026-08-31")


def test_a_blank_declaration_does_not_count():
    """⛔ 대조군. 빈 문자열로 검사를 통과하면 선언이 장식이 된다."""
    with pytest.raises(RuntimeError):
        _boot(["default", "design_docs"], verified="   ")


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


# ── 배포 배선 (SPEC-nexus-design-corpus-cutover §4.3) ────────────────────────

def _slack_cfg(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("NEXUS_SLACK_TOKEN", "t" * 40)
    from nexus.auth.config import AuthConfig
    return AuthConfig.from_dict({"auth": {"mode": "permissive", "principals": []}})


def test_the_slack_principal_gets_no_scope_by_default(monkeypatch):
    """⛔ 대조군. 환경변수를 안 주면 오늘과 같다 — 배선했다고 열리면 안 된다."""
    cfg = _slack_cfg(monkeypatch)
    bot = next(p for p in cfg.principals if p["name"] == "slack-bot")
    assert "read_tenants" not in bot


def test_a_declared_scope_reaches_the_principal(monkeypatch):
    cfg = _slack_cfg(monkeypatch, NEXUS_SLACK_READ_TENANTS="default, design_docs",
                     NEXUS_SLACK_CLEARANCE_VERIFIED="2026-08-31")
    bot = next(p for p in cfg.principals if p["name"] == "slack-bot")
    assert bot["read_tenants"] == ["default", "design_docs"]
    cfg.validate_startup()          # 선언이 있으므로 기동한다


def test_two_tenants_without_the_declaration_refuse_to_boot(monkeypatch):
    """⛔ **자물쇠가 배포 경로에서도 물린다.** 단위 검사만 통과하고 실제 배선에서 안 걸리면
    그 검사는 아무것도 안 지킨 것이다 — 이 리포가 반복해서 데인 모양이다."""
    cfg = _slack_cfg(monkeypatch, NEXUS_SLACK_READ_TENANTS="default,design_docs")
    with pytest.raises(RuntimeError, match="clearance_equivalence_verified"):
        cfg.validate_startup()


# ── 요청 계약 (§3.2) — 기본값은 요청이 아니다 ────────────────────────────────

def test_an_omitted_tenant_is_not_the_same_as_a_requested_one():
    """⛔ **컷오버를 조용히 무효로 만든 자리** (실측 2026-08-31).

    `AnswerRequest.tenant` 의 기본값이 `"default"` 라, 봇이 **보내지 않아도** 모델이 채워
    넣는다. 그것을 "요청했다" 로 읽으면 §3.2 의 *"안 주면 범위 전체"* 가 영원히 발화하지
    않고, 범위 목록을 붙여도 언제나 하나로 좁혀진다 — 자물쇠를 열고 설정을 넣고 재기동까지
    했는데 답변이 안 바뀌어서야 드러났다.
    """
    from nexus.api import AnswerRequest

    omitted = AnswerRequest(query="q")
    given = AnswerRequest(query="q", tenant="default")

    assert omitted.tenant == given.tenant == "default"      # 값은 같다
    assert "tenant" not in omitted.model_fields_set          # 그러나 요청은 다르다
    assert "tenant" in given.model_fields_set


def test_the_scope_opens_only_when_the_tenant_was_omitted():
    """값이 같아도 해소가 갈려야 한다 — 그 구별이 이 계약의 전부다."""
    p = _p(read_tenants=("default", "design_docs"))
    assert resolve_read_scope(p, None)[0] == ("default", "design_docs")
    assert resolve_read_scope(p, "default")[0] == ("default",)


# ── 개발 토큰 신원의 읽기 범위 (2026-09-03) ─────────────────────────────────
#
# ⛔ **왜 필요한가 (실측 2026-09-03).** 컷오버는 `slack-bot` **하나에만** 정본을 읽을 권한을
# 줬다(승인 SPEC 의 결정 문장 그대로, 범위 밖 선언 없음). 그런데 웹·CLI 는 `local-dev` 를 타고
# 그 principal 의 읽기 범위는 `default` 하나다 — 그래서 설계 문서 **122건**이 사람이 쓰는
# 표면에서 한 번도 근거로 안 나왔다(전체 질의 1,116건 중 `design_docs` 가 범위에 든 것 1건,
# 근거로 온 것 **0건**). 컷오버가 `default` 에서 사본을 내렸으므로, 그 표면들은 **잃기만 했다**.
#
# 슬랙 쪽과 **같은 자물쇠**를 쓴다. 상한을 올리는 것이 아니라 사람의 선언에 거는 것이고,
# 그 선언은 principal 마다 따로다 — 한 principal 의 확인이 다른 principal 을 열면 그 선언은
# 무엇을 확인한 것인지 말할 수 없게 된다.


def _dev_cfg(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("NEXUS_DEV_TOKEN", "d" * 40)
    from nexus.auth.config import AuthConfig
    return AuthConfig.from_dict({"auth": {"mode": "permissive", "principals": []}})


def test_the_dev_principal_gets_no_scope_by_default(monkeypatch):
    """⛔ 대조군. 환경변수를 안 주면 오늘과 같다 — **배선했다고 열리면 안 된다.**"""
    cfg = _dev_cfg(monkeypatch)
    dev = next(p for p in cfg.principals if p["name"] == "local-dev")
    assert "read_tenants" not in dev


def test_a_declared_scope_reaches_the_dev_principal(monkeypatch):
    cfg = _dev_cfg(monkeypatch, NEXUS_DEV_READ_TENANTS="default, design_docs",
                   NEXUS_DEV_CLEARANCE_VERIFIED="2026-08-31")
    dev = next(p for p in cfg.principals if p["name"] == "local-dev")
    assert dev["read_tenants"] == ["default", "design_docs"]
    cfg.validate_startup()


def test_two_tenants_without_the_declaration_refuse_to_boot_here_too(monkeypatch):
    """⛔ **자물쇠는 principal 마다 물린다.** 슬랙에만 걸리면 다음 신원이 그것을 우회한다."""
    import pytest

    cfg = _dev_cfg(monkeypatch, NEXUS_DEV_READ_TENANTS="default,design_docs")
    with pytest.raises(RuntimeError, match="clearance_equivalence_verified"):
        cfg.validate_startup()


def test_the_slack_declaration_does_not_open_the_dev_principal(monkeypatch):
    """⛔ 선언은 **그 principal 의 것**이다. 다른 신원의 확인을 빌려 쓰면, 그 선언이 무엇을
    확인한 것인지 말할 수 없게 된다 — 자물쇠가 이름만 남는다."""
    import pytest

    cfg = _dev_cfg(monkeypatch, NEXUS_DEV_READ_TENANTS="default,design_docs",
                   NEXUS_SLACK_CLEARANCE_VERIFIED="2026-08-31")
    with pytest.raises(RuntimeError, match="clearance_equivalence_verified"):
        cfg.validate_startup()


def test_a_single_tenant_needs_no_declaration(monkeypatch):
    """좁히는 쪽은 막지 않는다 — 자물쇠가 잠그는 것은 **넓히는** 것뿐이다."""
    cfg = _dev_cfg(monkeypatch, NEXUS_DEV_READ_TENANTS="default")
    cfg.validate_startup()
