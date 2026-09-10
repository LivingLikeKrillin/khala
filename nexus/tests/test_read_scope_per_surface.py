"""`check_read_scope_per_surface` 의 판정 규칙 — 순수 함수라 DB 없이 돈다.

⚠ **이 파일의 존재 이유는 하나의 케이스다.** 2026-09-03 의 실제 배포 모양을 그대로 넣고
검사가 **붉어지는지** 본다. 처음 설계(코퍼스 단위)는 그 모양에서 초록이었다 — 검사를 만들 때
자기가 잡으려는 사건을 넣어 보지 않으면 안 잡는 검사가 통과한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_read_scope_per_surface import (  # noqa: E402
    read_scopes, served_corpora, serving_surfaces, verdict,
)

from nexus.auth import AuthConfig  # noqa: E402

#: 활성 청크가 있는 테넌트들 — 라이브 실측(2026-09-10)과 같은 모양.
_ACTIVE = {"default": 614, "design_docs": 1582, "ko_eval_packa": 1897}
#: 음성 대조군이 통과한 상태. 튜플의 셋째가 0 이면 술어가 걸렀다는 뜻이다.
_OK_NEG = ("local-dev", "ko_eval_packa", 0)


def _reach(scopes, active=_ACTIVE):
    """범위 안이면 그 테넌트의 활성 청크 수, 밖이면 0 — 술어가 옳게 도는 세상."""
    return {(s, t): (active.get(t, 0) if t in sc else 0)
            for s, sc in scopes.items()
            for t in set(sc) | set(active)}


# ── 선언 읽기 ────────────────────────────────────────────────────────────────

def test_served_corpora_는_선언만_읽는다():
    assert served_corpora({"index": {"served_corpora": ["default", "design_docs"]}}) == {
        "default", "design_docs"}
    assert served_corpora({"index": {}}) == set()
    assert served_corpora(None) == set()


def test_serving_surfaces_는_선언만_읽는다():
    assert serving_surfaces({"auth": {"serving_surfaces": ["local-dev"]}}) == {"local-dev"}
    assert serving_surfaces({}) == set()


def test_read_scopes_는_앱과_같은_경로에서_범위를_받는다():
    """`read_tenants` 가 없으면 `tenant` 하나. 있으면 그 목록. `Principal.read_scope` 의 계약."""
    auth = AuthConfig.from_dict({"auth": {"principals": [
        {"name": "narrow", "tenant": "default"},
        {"name": "wide", "tenant": "default", "read_tenants": ["default", "design_docs"],
         "clearance_equivalence_verified": "2026-08-31"},
    ]}})
    assert read_scopes(auth) == {
        "narrow": ("default",), "wide": ("default", "design_docs")}


# ── 판정 불가 (수를 못 믿는 경우를 먼저 거른다) ──────────────────────────────

def test_표면이_없으면_판정하지_않는다():
    v = verdict(scopes={}, serving={"local-dev"}, served={"default"},
                active=_ACTIVE, reach={}, negative=_OK_NEG)
    assert v["usable"] is False


def test_서빙_코퍼스_선언이_없으면_판정하지_않는다():
    scopes = {"local-dev": ("default",)}
    v = verdict(scopes=scopes, serving={"local-dev"}, served=set(),
                active=_ACTIVE, reach=_reach(scopes), negative=_OK_NEG)
    assert v["usable"] is False
    assert "served_corpora" in v["why"]


def test_서빙_표면_선언이_없으면_판정하지_않는다():
    scopes = {"local-dev": ("default",)}
    v = verdict(scopes=scopes, serving=set(), served={"default"},
                active=_ACTIVE, reach=_reach(scopes), negative=_OK_NEG)
    assert v["usable"] is False
    assert "serving_surfaces" in v["why"]


def test_선언된_서빙_표면이_이_배포에_하나도_없으면_판정하지_않는다():
    """로컬 상자에 슬랙 토큰이 없는 것은 결함이 아니다. 다 없으면 셀 것이 없다."""
    scopes = {"ko-eval": ("ko_eval_packa",)}
    v = verdict(scopes=scopes, serving={"local-dev", "slack-bot"}, served={"default"},
                active=_ACTIVE, reach=_reach(scopes), negative=_OK_NEG)
    assert v["usable"] is False
    assert "하나도 없다" in v["why"]


def test_활성_청크가_아무_데도_없으면_판정하지_않는다():
    scopes = {"local-dev": ("default",)}
    v = verdict(scopes=scopes, serving={"local-dev"}, served={"default"},
                active={"default": 0}, reach={("local-dev", "default"): 0},
                negative=_OK_NEG)
    assert v["usable"] is False
    assert "빈 코퍼스" in v["why"]


def test_음성_대조군이_없으면_판정하지_않는다():
    scopes = {"local-dev": ("default",)}
    v = verdict(scopes=scopes, serving={"local-dev"}, served={"default"},
                active=_ACTIVE, reach=_reach(scopes), negative=None)
    assert v["usable"] is False
    assert "음성 대조군" in v["why"]


def test_음성_대조군이_새면_판정하지_않는다():
    """술어가 범위 밖을 안 거르면 위의 모든 수가 아무 말도 못 한다."""
    scopes = {"local-dev": ("default",)}
    v = verdict(scopes=scopes, serving={"local-dev"}, served={"default"},
                active=_ACTIVE, reach=_reach(scopes),
                negative=("local-dev", "ko_eval_packa", 1897))
    assert v["usable"] is False
    assert "샌다" in v["why"]


def test_양성_대조군이_안_서면_판정하지_않는다():
    """범위는 있는데 술어가 어디서도 0 을 낸다 — 셋 다 0 이면 비교가 죽은 것이다."""
    scopes = {"local-dev": ("default",)}
    v = verdict(scopes=scopes, serving={"local-dev"}, served={"default"},
                active=_ACTIVE, reach={("local-dev", "default"): 0}, negative=_OK_NEG)
    assert v["usable"] is False
    assert "양성 대조군" in v["why"]


# ── 결함 ─────────────────────────────────────────────────────────────────────

def test_2026_09_03_의_실제_모양에서_붉어진다():
    """⭐ **이 검사가 존재하는 이유.**

    컷오버 뒤의 실제 배포: 슬랙은 두 코퍼스를 읽고 웹·CLI 는 `default` 하나만 읽는다.
    `design_docs` 는 **고아가 아니다** — 슬랙이 닿는다. 그래서 코퍼스 단위로 세면 초록이고,
    그 초록이 설계 문서 122건을 사람 표면에서 한 달 넘게 안 보이게 두었다.
    """
    scopes = {"local-dev": ("default",),
              "slack-bot": ("default", "design_docs")}
    v = verdict(scopes=scopes, serving={"local-dev", "slack-bot"},
                served={"default", "design_docs"}, active=_ACTIVE,
                reach=_reach(scopes), negative=_OK_NEG)
    assert v["usable"] is True
    assert v["missing"] == [("local-dev", "design_docs")]


def test_배선_뒤의_모양에서_초록이다():
    """#424 가 `NEXUS_DEV_READ_TENANTS` 를 준 뒤의 상태 — 두 표면이 두 코퍼스에 다 닿는다."""
    scopes = {"local-dev": ("default", "design_docs"),
              "slack-bot": ("default", "design_docs")}
    v = verdict(scopes=scopes, serving={"local-dev", "slack-bot"},
                served={"default", "design_docs"}, active=_ACTIVE,
                reach=_reach(scopes), negative=_OK_NEG)
    assert v["usable"] is True
    assert v["missing"] == []
    assert v["empty_scope"] == []


def test_범위가_빈_코퍼스를_가리키면_붉어진다():
    """설정은 맞고 뒤에 아무것도 없는 상태. 문자열만 대조하는 검사는 이것을 못 본다."""
    scopes = {"local-dev": ("default", "design_docs")}
    active = {"default": 614, "design_docs": 0, "ko_eval_packa": 1897}
    v = verdict(scopes=scopes, serving={"local-dev"}, served={"default"},
                active=active, reach=_reach(scopes, active), negative=_OK_NEG)
    assert v["usable"] is True
    assert v["empty_scope"] == [("local-dev", "design_docs")]


def test_평가_principal_의_좁은_범위는_결함이_아니다():
    """서빙으로 선언되지 않은 표면은 세지 않는다 — 안 그러면 검사가 매번 붉고 곧 꺼진다."""
    scopes = {"local-dev": ("default", "design_docs"),
              "ko-eval": ("ko_eval_packa",)}
    v = verdict(scopes=scopes, serving={"local-dev"},
                served={"default", "design_docs"}, active=_ACTIVE,
                reach=_reach(scopes), negative=_OK_NEG)
    assert v["usable"] is True
    assert v["missing"] == []
