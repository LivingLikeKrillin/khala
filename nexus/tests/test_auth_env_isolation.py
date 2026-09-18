"""격리 목록이 **실제로 config.py 를 따라가는가.**

⛔ 이 파일이 없으면 `_auth_env.PRINCIPAL_ENV` 는 손으로 맞춘 사본이 되고, `config.py` 가
새 변수를 읽기 시작하는 날 조용히 낡는다. 그리고 그 낡음은 *다음 사람이 같은 자리에서
데일 때* 드러난다 — 이 리포가 이 병으로 두 번 데였다(#503, 그리고 그 뒤 네 파일).
"""

from __future__ import annotations

import importlib
import pathlib
import re

import pytest

from nexus.auth.config import AuthConfig
from tests._auth_env import (
    PRINCIPAL_ENV, PRINCIPAL_ENV_PREFIXES, clear_principal_env, fill_principal_env,
)

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
    """배포와 같은 모양을 일부러 만든다 — 모양의 정본은 `_auth_env.fill_principal_env`."""
    fill_principal_env(monkeypatch)


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


# ── 그 격리를 실제로 부르는 파일이 있는가 ───────────────────────────────────
#
# ⛔ **위의 검사들은 `clear_principal_env` 가 도는지만 본다.** 어느 파일이 그것을 *부르는지*
# 는 안 본다. 그 차이로 이 리포가 한 번 데였다: #508 은 목록과 위 검사들을 넣고 커밋 본문에
# "each file gets an autouse fixture" 라고 적었는데 **네 파일 중 아무것도 안 받았고**, 스위트는
# 초록이었다. 설정된 기계에서만 6건이 빨갛고 CI 는 맨 상자라 볼 수 없다.
#
# 그래서 여기서는 결과가 아니라 **선언**을 본다 — 파일이 그 표시를 달고 있는가.

#: `from_dict` 를 부르지만 격리를 안 다는 파일. **왜 안 다는지**를 같이 적는다.
_NOT_ISOLATED: dict[str, str] = {
    "test_auth_env_isolation.py":
        "이 파일이 격리 자체를 검사한다 — 대조군은 일부러 안 지운 상태여야 한다",
    "test_access_principal.py":
        "결과를 통째로 단언하지 않고 지정한 principal 만 본다 — 열 변수를 다 채운 환경에서 "
        "초록 확인(2026-09-18)",
    "test_auth_dev_token_guard.py": "위와 같음 (같은 실행에서 확인)",
}


def _modules_that_build_a_config() -> set[str]:
    """`AuthConfig.from_dict` 를 부르는 검사 파일 — 이름이 아니라 **본문**으로 찾는다.

    목록을 손으로 적으면 새 파일이 조용히 빠진다. 그 조용함이 #508 의 병이었다.
    """
    here = pathlib.Path(__file__).parent
    return {f.name for f in here.glob("test_*.py")
            if "AuthConfig.from_dict" in f.read_text(encoding="utf-8")}


def _declares_isolation(name: str) -> bool:
    """모듈이 그 표시를 달고 있는가.

    ⚠ `pytestmark` 는 하나만 달면 리스트가 아니라 `MarkDecorator` 하나다 — 그대로 순회하면
    조용히 아무것도 못 찾는다(이 검사를 처음 쓸 때 실제로 그랬고, 네 파일이 다 표시를 달고
    있는데도 없다고 나왔다). 그래서 둘 다 받아 `Mark` 로 맞춘다.
    """
    declared = getattr(importlib.import_module(f"tests.{name[:-3]}"), "pytestmark", [])
    if not isinstance(declared, (list, tuple)):
        declared = [declared]
    return any(getattr(m, "mark", m).name == "usefixtures"
               and "isolate_auth_env" in getattr(m, "mark", m).args
               for m in declared)


def test_every_file_that_builds_a_config_declares_the_isolation():
    """⛔ 표시가 사라지면 **맨 상자에서도** 여기서 깨진다 — 설정된 기계를 기다리지 않는다."""
    building = _modules_that_build_a_config()
    assert building, "`from_dict` 를 부르는 파일을 하나도 못 찾았다 — 대조가 죽은 것이다"

    missing = sorted(n for n in building - set(_NOT_ISOLATED) if not _declares_isolation(n))
    assert not missing, (
        f"`AuthConfig.from_dict` 를 부르는데 격리 선언이 없다: {missing} — 파일 맨 위에 "
        '`pytestmark = pytest.mark.usefixtures("isolate_auth_env")` 를 달거나, 안 다는 '
        "이유를 `_NOT_ISOLATED` 에 적어라")


def test_the_exemptions_are_still_about_files_that_exist():
    """⚠ 면제 목록도 낡는다. 사라진 파일 이름이 남아 있으면 무엇을 면제한 것인지 흐려진다."""
    stale = sorted(set(_NOT_ISOLATED) - _modules_that_build_a_config())
    assert not stale, f"`from_dict` 를 안 부르는데 면제 목록에 있다: {stale}"
