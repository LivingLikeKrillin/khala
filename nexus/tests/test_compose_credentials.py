"""자격증명은 **베이스 compose 한 곳에서만** 앱에 주입된다.

왜 이 테스트가 있나: `NOTION_TOKEN` 주입이 `docker-compose.override.yml`(개발 전용)에만
있었다. prod 오버레이는 그 사실을 알 길이 없어 조용히 빠졌고, `.env` 에 토큰이 있어도
컨테이너에는 들어가지 않아 동기화가 503 으로 막혔을 것이다. `ANTHROPIC_API_KEY` 는 베이스에
있었다 — 같은 종류의 값 둘이 다른 파일에 살고 있었던 것이 병이다.

그래서 불변식: 앱이 쓰는 모든 시크릿은 베이스에서 선언되고, 오버레이는 **다시 선언하지 않는다.**
오버레이는 얹고 빼는 것이므로, 거기 적힌 자격증명은 그 오버레이를 안 얹는 배포에서 사라진다.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_APP = "nexus-app"

#: 앱이 `os.getenv` 로 읽는 자격증명. 새로 추가하면 여기에도 적는다 — 베이스에 넣게 만드는 목록.
#:
#: `NEXUS_DEV_TOKEN` 은 **일부러 빠져 있다.** 그건 오버레이가 존재해야만 있어야 하는 값이다
#: (무인증 `/auth/dev-token` 이 INTERNAL 코퍼스를 연다). 베이스로 옮기면 prod 가 상속한다.
SECRETS = ("NOTION_TOKEN", "ANTHROPIC_API_KEY")


class _ComposeLoader(yaml.SafeLoader):
    """compose 오버레이는 `!reset` / `!override` 같은 자체 태그를 쓴다 — SafeLoader 는 거기서 죽는다.

    (`docker-compose.prod.yml` 이 실제로 그렇다. 모르는 태그를 만나면 값만 취한다.)
    """


_ComposeLoader.add_multi_constructor(
    "!", lambda loader, suffix, node: (
        loader.construct_mapping(node) if isinstance(node, yaml.MappingNode)
        else loader.construct_sequence(node) if isinstance(node, yaml.SequenceNode)
        else loader.construct_scalar(node)
    ),
)


def _env_of(compose_file: str) -> dict:
    doc = yaml.load((_ROOT / compose_file).read_text(encoding="utf-8"), _ComposeLoader)  # noqa: S506
    return (doc.get("services", {}).get(_APP, {}) or {}).get("environment", {}) or {}


def test_the_compose_loader_reads_compose_tags_but_not_python_ones():
    """`!reset`/`!override` 는 읽되, `!!python/...` 은 여전히 거부한다 (SafeLoader 상속).

    `!!x` 는 `tag:yaml.org,2002:x` 로 해석되어 `!` 접두 핸들러에 걸리지 않는다.
    """
    assert yaml.load("ports: !reset []", _ComposeLoader) == {"ports": []}  # noqa: S506
    assert yaml.load("volumes: !override [a]", _ComposeLoader) == {"volumes": ["a"]}  # noqa: S506

    for payload in ("x: !!python/object/apply:os.system ['echo pwned']", "x: !!python/name:os.system"):
        with pytest.raises(yaml.YAMLError):
            yaml.load(payload, _ComposeLoader)  # noqa: S506


def test_every_secret_is_injected_by_the_base_compose():
    env = _env_of("docker-compose.yml")
    missing = [s for s in SECRETS if s not in env]
    assert not missing, (
        f"베이스 compose 가 주입하지 않는 시크릿: {missing}. "
        f"오버레이에만 두면 그 오버레이를 안 얹는 배포에서 조용히 사라진다."
    )


def test_secrets_are_optional_so_a_fresh_clone_still_boots():
    """`${VAR:?}` 로 강제하면 토큰 없이 검색만 하려는 사람이 부팅조차 못 한다."""
    env = _env_of("docker-compose.yml")
    for s in SECRETS:
        assert env[s] == f"${{{s}:-}}", f"{s} 는 기본값 빈 문자열이어야 한다: {env[s]!r}"


def test_overlays_do_not_redeclare_secrets():
    """오버레이가 같은 값을 다시 적으면 두 곳이 갈라진다 — 갈라진 결과가 이 버그였다."""
    for overlay in ("docker-compose.override.yml", "docker-compose.prod.yml"):
        if not (_ROOT / overlay).exists():
            continue
        dupes = [s for s in SECRETS if s in _env_of(overlay)]
        assert not dupes, f"{overlay} 가 시크릿을 재선언한다: {dupes} (베이스에만 두라)"


def test_the_dev_token_stays_in_the_dev_overlay():
    """역방향 가드: NEXUS_DEV_TOKEN 을 베이스로 올리면 prod 가 무인증 온램프를 상속한다."""
    assert "NEXUS_DEV_TOKEN" not in _env_of("docker-compose.yml")
    assert "NEXUS_DEV_TOKEN" in _env_of("docker-compose.override.yml")
