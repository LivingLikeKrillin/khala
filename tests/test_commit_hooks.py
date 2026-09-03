"""커밋 훅 두 층 — 메시지와 파일 내용.

⛔ **왜 있나 (2026-09-03).** `commit-msg` 훅은 커밋 **메시지**의 지문을 막는다. 그 머리말이 이유를
적어 두었다: *"CI 가 머지 전에 잡아 주지만 그때는 이미 원격 브랜치에 올라가 있고, GitHub 은 PR 이
고정한 커밋을 그 뒤에도 SHA 로 계속 열어준다."* 같은 논리가 **파일 내용**에도 그대로 걸리는데
그 층은 없었고, 그 구멍으로 실제 Notion 페이지 ID 가 테스트 상수에 실려 공개 브랜치에 올라갔다.

⭐ 그날 로컬 검사는 **돌았고 실패했다.** 그런데도 커밋이 지나간 이유는 호출 형태다 —
`fingerprint_scan.py | tail -2` 로 부르면 파이프라인의 종료 코드는 `tail` 의 것이라 **항상 0**
이고, 뒤에 붙은 `&& git commit` 이 그대로 실행된다. 훅 안에서 같은 실수가 나면 훅이 있으나 마나
이므로, 파이프를 쓰지 않는다는 것 자체를 검사한다.
"""

from __future__ import annotations

from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "scripts" / "hooks"
SCAN = "fingerprint_scan.py"


def _line_calling_scan(name: str) -> str:
    hits = [ln for ln in (HOOKS / name).read_text(encoding="utf-8").splitlines()
            if SCAN in ln and not ln.lstrip().startswith("#")]
    assert len(hits) == 1, f"{name}: 지문 검사 호출이 {len(hits)}줄이다 — 한 줄이어야 한다"
    return hits[0]


def test_both_layers_exist():
    """메시지와 파일 내용, 둘 다여야 한다 — 한쪽만 있는 상태가 이 파일을 만들게 했다."""
    assert (HOOKS / "commit-msg").exists()
    assert (HOOKS / "pre-commit").exists()


def test_the_message_hook_scans_the_message():
    assert "--text" in _line_calling_scan("commit-msg")


def test_the_content_hook_scans_the_tree_not_the_message():
    """`--text` 를 주면 스테이지된 파일이 아니라 인자 문자열을 본다 — 층이 겹치고 구멍은 남는다."""
    assert "--text" not in _line_calling_scan("pre-commit")


def test_neither_hook_pipes_the_scan_away():
    """⭐ 이것이 그날의 실제 결함이다 — 파이프는 종료 코드를 `tail` 의 것으로 바꾼다."""
    for name in ("commit-msg", "pre-commit"):
        line = _line_calling_scan(name)
        assert "|" not in line.split("||")[0], (
            f"{name}: 검사 결과를 파이프로 넘긴다 — 종료 코드가 사라지고 훅이 통과한다")


def test_each_hook_exits_nonzero_when_the_scan_fails():
    """`|| { … exit 1 }` 가 없으면 실패해도 커밋이 지나간다."""
    for name in ("commit-msg", "pre-commit"):
        body = (HOOKS / name).read_text(encoding="utf-8")
        assert "exit 1" in body, f"{name}: 실패 경로에서 커밋을 안 멈춘다"


def test_each_hook_says_why_it_stopped():
    """멈추기만 하고 이유를 안 적으면 다음 사람이 --no-verify 로 넘어간다."""
    for name in ("commit-msg", "pre-commit"):
        body = (HOOKS / name).read_text(encoding="utf-8")
        assert "public" in body and "커밋을 멈춘다" in body


def test_the_hooks_record_that_bypass_is_allowed():
    """훅은 실수를 막는 층이지 사람을 막는 층이 아니다 — 강제하는 곳은 CI 다."""
    for name in ("commit-msg", "pre-commit"):
        assert "--no-verify" in (HOOKS / name).read_text(encoding="utf-8")
