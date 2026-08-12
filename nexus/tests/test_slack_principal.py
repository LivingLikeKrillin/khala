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
