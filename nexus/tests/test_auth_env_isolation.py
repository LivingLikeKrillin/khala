"""격리 목록이 **실제로 config.py 를 따라가는가.**

⛔ 이 파일이 없으면 `_auth_env.PRINCIPAL_ENV` 는 손으로 맞춘 사본이 되고, `config.py` 가
새 변수를 읽기 시작하는 날 조용히 낡는다. 그리고 그 낡음은 *다음 사람이 같은 자리에서
데일 때* 드러난다 — 이 리포가 이 병으로 두 번 데였다(#503, 그리고 그 뒤 네 파일).
"""

from __future__ import annotations

import pathlib
import re

import pytest

from nexus.auth.config import AuthConfig
from tests._auth_env import PRINCIPAL_ENV, PRINCIPAL_ENV_PREFIXES, clear_principal_env

_CONFIG = pathlib.Path(AuthConfig.__module__.replace(".", "/") + ".py")
_SRC = (pathlib.Path(__file__).resolve().parents[1] / _CONFIG).read_text(encoding="utf-8")

#: 신원과 무관한 것. 여기 넣을 때는 **왜 무관한지**를 같이 적는다.
_NOT_ABOUT_IDENTITY: dict[str, str] = {}


def _env_names_config_reads() -> set[str]:
    exact = set(re.findall(r'os\.getenv\(\s*"(NEXUS_[A-Z0-9_]+)"', _SRC))
    prefixes = set(re.findall(r'startswith\(\s*"(NEXUS_[A-Z0-9_]+)"', _SRC))
    return {n for n in exact if not n.startswith(tuple(prefixes))} | prefixes


def test_the_list_covers_everything_the_config_reads():
    """⛔ 새 변수를 읽기 시작했는데 목록에 없으면 여기서 깨진다."""
    known = set(PRINCIPAL_ENV) | set(PRINCIPAL_ENV_PREFIXES) | set(_NOT_ABOUT_IDENTITY)
    missing = _env_names_config_reads() - known
    assert not missing, (
        f"config.py 가 읽는데 격리 목록에 없다: {sorted(missing)} — "
        "`_auth_env.PRINCIPAL_ENV` 에 더하거나, 신원과 무관하면 `_NOT_ABOUT_IDENTITY` 에 "
        "이유와 함께 적어라")


def test_the_list_has_no_names_the_config_stopped_reading():
    """반대 방향도 본다 — 안 읽는 이름이 남아 있으면 이 목록이 무엇을 지키는지 흐려진다."""
    stale = (set(PRINCIPAL_ENV) | set(PRINCIPAL_ENV_PREFIXES)) - _env_names_config_reads()
    assert not stale, f"config.py 가 더 이상 안 읽는다: {sorted(stale)}"


def test_the_prefix_sweep_is_not_a_no_op():
    """접두사 자리는 `os.environ` 전체를 훑어야 한다 — 이름을 미리 알 수 없기 때문이다."""
    assert "NEXUS_SLACK_CORPUS_" in PRINCIPAL_ENV_PREFIXES


# ── 실제로 격리가 되는가 ───────────────────────────────────────────────────

@pytest.fixture
def configured_like_a_deployment(monkeypatch):
    """배포와 같은 모양을 일부러 만든다 — 정확한 이름 하나와 접두사 하나."""
    for name in PRINCIPAL_ENV:
        monkeypatch.setenv(name, "1" if name.endswith(("ANONYMOUS", "DEV_TOKEN")) else "x" * 40)
    monkeypatch.setenv("NEXUS_SLACK_CORPUS_SOMETHING", "tok|some_tenant|INTERNAL")


def test_the_isolation_actually_empties_the_config(configured_like_a_deployment, monkeypatch):
    """⛔ 이 파일들의 모든 검사가 기대는 전제. 못 비우면 그 검사들은 통과해도 아무 말도
    안 한 것이다."""
    clear_principal_env(monkeypatch)
    cfg = AuthConfig.from_dict({})
    assert cfg.principals == [], f"신원이 남아 있다: {[p.get('name') for p in cfg.principals]}"
    assert cfg.mode == "enforced", "`NEXUS_ALLOW_ANONYMOUS` 가 남아 모드를 바꿨다"


def test_without_the_isolation_the_config_is_not_empty(configured_like_a_deployment):
    """⚠ **대조군.** 위 검사가 참이려면 이쪽이 거짓이어야 한다 — 안 지우면 신원이 생긴다는
    것을 확인해 두지 않으면, 격리가 아무 일도 안 하는데 통과하는 세상과 구별할 수 없다."""
    cfg = AuthConfig.from_dict({})
    assert cfg.principals, "지우지 않았는데도 비어 있다 — 이 검사가 무엇도 확인하지 못한다"
