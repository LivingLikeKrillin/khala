"""슬랙 봇 신원 — 봇이 보내는 토큰과 서버가 아는 토큰이 어긋날 수 없어야 한다.

compose 주석은 봇의 bearer 를 "gen-token 으로 발급한 읽기 전용 principal" 이라 적어 두었는데,
그 principal 을 만드는 코드도 config 항목도 없었다. 봇을 띄웠다면 401 루프였다.

그래서 **하나의 env 변수**에서 양쪽이 파생된다: 봇은 토큰을 보내고, 서버는 같은 변수의 해시로
principal 을 만든다. 어긋남이 표현 불가능한 것이 이 설계의 요점이고, 아래 검사는 그 요점을 건다.
"""

from __future__ import annotations

from nexus.auth.config import AuthConfig
from nexus.auth.principal import hash_token

CFG = {"auth": {"mode": "enforced", "principals": []}}


def _load(monkeypatch, **env):
    for k in ("NEXUS_DEV_TOKEN", "NEXUS_SLACK_TOKEN", "NEXUS_SLACK_CLEARANCE",
              "NEXUS_SLACK_TENANT"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return AuthConfig.from_dict(CFG)


def _slack(cfg):
    return next((p for p in cfg.principals if p["name"] == "slack-bot"), None)


def test_no_slack_token_means_no_slack_surface(monkeypatch):
    """기본은 슬랙 표면 없음 — 토큰이 없으면 principal 도 없다."""
    assert _slack(_load(monkeypatch)) is None


def test_the_bots_token_is_the_servers_principal(monkeypatch):
    """봇이 보내는 그 토큰의 해시여야 한다. 다른 값이면 401 이고, 그 401 은 원인이 안 보인다."""
    cfg = _load(monkeypatch, NEXUS_SLACK_TOKEN="a-real-looking-token-value")
    p = _slack(cfg)
    assert p is not None
    assert p["token_sha256"] == hash_token("a-real-looking-token-value")


def test_the_bot_is_read_only(monkeypatch):
    """워크스페이스 전원에게 열리는 표면이 문서를 내리거나 소스를 고칠 수 있으면 안 된다."""
    p = _slack(_load(monkeypatch, NEXUS_SLACK_TOKEN="t"))
    assert p["capabilities"] == []


def test_the_clearance_floor_is_public_by_default(monkeypatch):
    """슬랙은 워크스페이스 전원이다 — 신뢰 바닥이 기본값이어야 한다."""
    assert _slack(_load(monkeypatch, NEXUS_SLACK_TOKEN="t"))["clearance"] == "PUBLIC"


def test_the_clearance_can_be_raised_deliberately(monkeypatch):
    p = _slack(_load(monkeypatch, NEXUS_SLACK_TOKEN="t", NEXUS_SLACK_CLEARANCE="INTERNAL"))
    assert p["clearance"] == "INTERNAL"


def test_the_slack_identity_is_not_the_operator_identity(monkeypatch):
    """`local-dev` 는 운영자 신원이고 `/auth/dev-token` 이 누구에게나 내준다 — 봇과 같은 신원을
    쓰면 보존 허용목록이 '슬랙 사용자' 가 아니라 '접근 가능한 전원' 을 가리키게 된다."""
    cfg = _load(monkeypatch, NEXUS_SLACK_TOKEN="bot-token", NEXUS_DEV_TOKEN="dev-token-long-enough")
    names = {p["name"] for p in cfg.principals}
    assert {"slack-bot", "local-dev"} <= names
    bot = _slack(cfg)
    dev = next(p for p in cfg.principals if p["name"] == "local-dev")
    assert bot["token_sha256"] != dev["token_sha256"]
    assert bot["capabilities"] == [] and dev["capabilities"]


# ── 두 번째 코퍼스 (2026-08-18) ──────────────────────────────────────────────
#
# **테넌트는 토큰이 정한다.** `auth/scope.py` 는 요청의 tenant 를 무시한다(테넌트 격리이자
# 존재 유출 방지). 그래서 봇이 다른 코퍼스에 물으려면 문자열이 아니라 그 테넌트에 묶인 토큰이
# 필요하고, 채널마다 코퍼스를 나누는 일은 결국 **토큰을 나누는 일**이다.


def _principal(cfg, name):
    return next((p for p in cfg.principals if p["name"] == name), None)


def test_a_second_corpus_becomes_its_own_principal(monkeypatch):
    monkeypatch.setenv("NEXUS_SLACK_CORPUS_DESIGN", "design-token|design_docs|INTERNAL")
    cfg = _load(monkeypatch, NEXUS_SLACK_TOKEN="base-token-value-long-enough")

    p = _principal(cfg, "slack-design")
    assert p is not None
    assert p["tenant"] == "design_docs"
    assert p["clearance"] == "INTERNAL"
    assert p["token_sha256"] == hash_token("design-token")
    assert p["capabilities"] == []      # 워크스페이스 전원에게 열리는 표면은 읽기 전용이다


def test_the_second_corpus_inherits_the_bot_clearance_when_unset(monkeypatch):
    monkeypatch.setenv("NEXUS_SLACK_CORPUS_DESIGN", "design-token|design_docs")
    cfg = _load(monkeypatch, NEXUS_SLACK_TOKEN="base-token-value-long-enough",
                NEXUS_SLACK_CLEARANCE="INTERNAL")

    assert _principal(cfg, "slack-design")["clearance"] == "INTERNAL"


def test_a_malformed_corpus_entry_is_skipped_not_fatal(monkeypatch):
    """오타 하나가 배포 전체를 못 뜨게 하면 안 된다 — 그 코퍼스만 건너뛴다."""
    monkeypatch.setenv("NEXUS_SLACK_CORPUS_BROKEN", "token-without-a-tenant")
    monkeypatch.setenv("NEXUS_SLACK_CORPUS_DESIGN", "design-token|design_docs")
    cfg = _load(monkeypatch, NEXUS_SLACK_TOKEN="base-token-value-long-enough")

    assert _principal(cfg, "slack-broken") is None
    assert _principal(cfg, "slack-design") is not None


def test_no_corpus_env_leaves_todays_principals_untouched(monkeypatch):
    cfg = _load(monkeypatch, NEXUS_SLACK_TOKEN="base-token-value-long-enough")

    assert [p["name"] for p in cfg.principals] == ["slack-bot"]
