"""브리지가 `claude` 를 **리포 밖에서** 돌린다.

⛔ **왜 생겼나 (실측 2026-09-20).** 이 모듈 머리말은 `--setting-sources ""` 가
*"프로젝트/유저 세팅·훅·스킬·CLAUDE.md 미로드"* 라고 적어 뒀다. 그런데 **CLAUDE.md 는
막히지 않는다.** 같은 argv 로 작업 디렉터리만 바꿔 대조했다:

    리포 안에서   "이 저장소에서 specledger 의 새 이름은?"  →  "Arbiter"
    중립 디렉터리                     같은 질문            →  "모른다"

    리포 안에서   "당신은 무엇인가?"  →  "khala/nexus 저장소에서 … 작업 중인 세션"
    중립 디렉터리        같은 질문     →  "터미널에서 작업을 돕는 AI 에이전트"

⚠ **이것이 측정을 움직인다.** 이 리포의 `CLAUDE.md` 는 *"grounded answers only · 추측 금지"* ·
*"System decides, LLM narrates"* 를 적는다. 그 문장을 들고 도는 모델은 우리가 **재려는 바로
그 축**에서 더 잘한다. 유료 키로 도는 배포에는 그 맥락이 없다.

⭐ 호출 사이에 **누적되는 것은 없다**(같은 날 실측: 한 호출에 심은 낱말을 다음 호출이
모른다고 답한다). 이 파일이 막는 것은 누적이 아니라 **상수 주입**이다.
"""

from __future__ import annotations

import os
import pathlib

from nexus.tools import claude_llm_bridge as bridge

REPO = pathlib.Path(bridge.__file__).resolve().parents[3]


def test_the_neutral_directory_is_not_inside_the_repo():
    """⛔ 이 한 줄이 이 파일의 전부다."""
    cwd = pathlib.Path(bridge.neutral_cwd()).resolve()
    assert REPO not in cwd.parents and cwd != REPO, \
        f"브리지가 리포 안({cwd})에서 돈다 — 프로젝트 맥락이 모든 답변에 실린다"


def test_it_exists_and_is_a_directory():
    cwd = pathlib.Path(bridge.neutral_cwd())
    assert cwd.is_dir(), "만들어지지 않았다 — `subprocess` 가 곧바로 터진다"


def test_it_is_empty_of_project_markers():
    """⚠ 빈 자리여야 한다. `CLAUDE.md` 나 `.git` 이 있으면 다시 프로젝트가 된다."""
    cwd = pathlib.Path(bridge.neutral_cwd())
    for marker in ("CLAUDE.md", ".git", "pyproject.toml", ".claude"):
        assert not (cwd / marker).exists(), f"중립이어야 할 자리에 {marker} 가 있다"


def test_the_runner_passes_a_cwd_at_all(monkeypatch):
    """⛔ **함수가 옳은 것과 부르는 쪽이 넘기는 것은 다른 사실이다.**

    `neutral_cwd()` 만 검사하면, 그것을 아무도 안 넘겨도 초록이다 — 이 리포는 그 구분에서
    이미 이틀짜리 침묵을 겪었다(`section_fill`).
    """
    seen: dict = {}

    class _P:
        returncode, stdout, stderr = 0, "ok", ""

    def fake_run(argv, **kw):
        seen.update(kw)
        return _P()

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    bridge._subprocess_runner(["claude"], "프롬프트", 5.0)

    assert "cwd" in seen, "`cwd` 를 안 넘긴다 — 띄운 셸의 위치를 물려받는다"
    got = pathlib.Path(seen["cwd"]).resolve()
    assert REPO not in got.parents and got != REPO, f"넘긴 자리가 리포 안이다: {got}"


def test_the_fallback_never_lands_in_the_repo(monkeypatch):
    """만들기에 실패해도 리포로 물러서지 않는다 — 물러선 자리가 맥락을 주면 무의미하다."""
    def boom(*a, **k):
        raise OSError("디스크 가득")

    monkeypatch.setattr(os, "makedirs", boom)
    got = pathlib.Path(bridge.neutral_cwd()).resolve()
    assert REPO not in got.parents and got != REPO
