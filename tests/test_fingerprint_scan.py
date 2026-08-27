"""지문 검사에 이가 있는가.

첫 판의 이 검사는 32자 16진을 **맥락 없이** 잡아 123건을 냈다 — k8s 평가 코퍼스의 UID 와
probe 픽스처의 콘텐츠 해시까지. 그 소음에 음성 대조군이 파묻혀서, 검사가 도는지조차 안 보였다.
많이 잡는 검사는 아무것도 안 잡는 검사와 같다.

그래서 여기서 네 가지를 다 측정한다. 셋은 **발화해야** 하고 하나는 **발화하면 안 된다.**
발화만 확인하는 검사는 이 리포가 반복해서 잡아낸 무효 대조군이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))       # 리포 관례 — tests/test_ledger_integrity.py 와 같다

from fingerprint_scan import scan, tracked_files  # noqa: E402


# 탐침 문자열은 **런타임에 조립한다.** 이 파일도 추적되므로, 지문을 문자 그대로 담으면 검사가
# 자기 대조군을 잡아 영원히 붉다(실제로 그렇게 됐고 CI 가 잡았다). SKIP 에 이 파일을 넣는 쪽이
# 쉬웠지만 그러면 진짜 지문이 숨을 자리가 하나 생긴다 — 검사를 무디게 하는 대신 탐침을 접는다.
_ORG = "PF" + "Play"
_UID = "9f8e7d6c-5b4a-4392-8170-6d5c4b3a2918"      # 합성. 어느 워크스페이스도 안 가리킨다


def _with(tmp_line: str, rel: str, monkeypatch):
    """추적 파일 목록에 임시 파일 하나를 얹어 scan() 을 돌린다 — 작업 트리를 안 건드린다."""
    import fingerprint_scan as fs

    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tmp_line + "\n", encoding="utf-8")
    monkeypatch.setattr(fs, "tracked_files", lambda: [rel])
    try:
        return fs.scan()
    finally:
        path.unlink()


def test_the_tree_is_clean_right_now():
    """이것이 통과가 아니면 나머지 대조군은 읽을 수 없다."""
    assert scan() == [], "추적 파일에 지문이 남아 있다"


def test_the_partner_organisation_name_fires(monkeypatch):
    found = _with(f"# {_ORG} note", "nexus/tests/_fp_probe.py", monkeypatch)
    assert any(_ORG.lower() in p for p in found)


def test_a_real_page_id_in_notion_context_fires(monkeypatch):
    """맥락은 같은 줄에서 온다."""
    found = _with(f'P = "notion page_id {_UID}"', "nexus/tests/_fp_probe.py", monkeypatch)
    assert any(_UID in p for p in found)


def test_a_page_id_fires_on_path_context_alone(monkeypatch):
    """파일 이름이 Notion 이면 그 안의 32자 ID 는 전부 의심한다 — 변수명이 무엇이든."""
    found = _with(f'ROOT = "{_UID}"', "nexus/tests/test_notion_fp_probe.py", monkeypatch)
    assert any(_UID in p for p in found)


def test_a_uuid_without_notion_context_does_not_fire(monkeypatch):
    """**발화하면 안 되는 쪽.** k8s 코퍼스의 UID 와 콘텐츠 해시가 여기 걸리면 123건이 나오고,
    그 소음 아래에서는 진짜 지문이 안 보인다."""
    found = _with(f'X = "{_UID}"  # a pod uid', "nexus/tests/_fp_probe.py", monkeypatch)
    assert found == [], f"맥락 없는 UUID 를 잡았다 — 검사가 소음이 된다: {found}"


def test_the_allow_list_carries_a_reason():
    """근거 없는 예외는 다음 사람이 지울 수 없고, 그러면 허용 목록이 곧 구멍이 된다."""
    src = (ROOT / "scripts" / "fingerprint_scan.py").read_text(encoding="utf-8")
    block = src.split("ALLOWED_IDS = {", 1)[1].split("}", 1)[0]
    entries = [ln for ln in block.splitlines() if ln.strip().startswith('"')]
    assert entries, "허용 목록이 비었다면 이 검사를 지워라"
    # 각 항목 바로 위(또는 그 위)에 주석이 있어야 한다
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    for i, ln in enumerate(lines):
        if ln.startswith('"'):
            assert any(lines[j].startswith("#") for j in range(i - 1, -1, -1)
                       if not lines[j].startswith('"')), f"근거 없는 허용 항목: {ln}"


def test_tracked_files_skips_the_scanner_itself():
    """패턴 문자열을 담은 파일이 스스로를 잡으면 검사는 영원히 붉다."""
    assert "scripts/fingerprint_scan.py" not in tracked_files()


# ── 공개될 텍스트: 커밋 메시지 · PR 제목/본문 ────────────────────────────────
#
# 파일은 절반이었다. 2026-08-07 에 같은 이름이 커밋 메시지 2건과 PR 본문 2건으로 나갔고,
# force-push 로 되돌려지지 않았다 — GitHub 은 PR 이 고정한 커밋을 그 뒤에도 SHA 로 열어준다.
# 그래서 이쪽은 **머지 전에** 막아야 하고, 막히는지 여기서 측정한다.


def test_a_commit_message_carrying_the_organisation_is_rejected(tmp_path):
    import fingerprint_scan as fs

    f = tmp_path / "commit-messages.txt"
    f.write_text(f"fix(x): something\n\n{_ORG} 정책 적재로 코퍼스가 늘었다\n", encoding="utf-8")
    assert fs.main(["--text", str(f)]) == 1


def test_a_pr_body_carrying_a_page_id_is_rejected(tmp_path):
    import fingerprint_scan as fs

    f = tmp_path / "pr-title-and-body.txt"
    f.write_text(f"title\n\nthe notion root_id {_UID} was never shared\n", encoding="utf-8")
    assert fs.main(["--text", str(f)]) == 1


def test_an_ordinary_commit_message_passes(tmp_path):
    """**발화하면 안 되는 쪽.** 커밋 메시지에 맥락 없는 UUID(파드 uid·콘텐츠 해시)를 붙이는 일은
    흔하다. 그걸 다 잡으면 아무도 이 검사를 안 켠다."""
    import fingerprint_scan as fs

    f = tmp_path / "commit-messages.txt"
    f.write_text(f"fix(embed): stop swallowing a refusal\n\nthe chunk uid was {_UID}\n",
                 encoding="utf-8")
    assert fs.main(["--text", str(f)]) == 0


def test_the_text_mode_does_not_silently_scan_nothing(tmp_path):
    """빈 범위를 통과로 읽으면 검사가 있는 척만 한다 — 얕은 클론에서 실제로 그렇게 된다."""
    import fingerprint_scan as fs

    f = tmp_path / "commit-messages.txt"
    f.write_text("", encoding="utf-8")
    assert fs.scan_streams([str(f)]) == []          # 빈 것은 빈 것이다
    # 그래서 CI 는 fetch-depth: 0 을 쓴다. 그 배선이 사라지면 이 주석이 근거다.
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 0" in ci, "얕은 클론이면 커밋 범위가 비고, 검사는 조용히 통과한다"


def test_the_pr_body_is_read_live_not_from_the_frozen_event():
    """`github.event.pull_request.body` 는 이벤트 시점에 얼어 있다.

    그것을 쓰면 재실행이 옛 본문을 재생해서, 본문을 고친 사람이 커밋을 하나 더 밀지 않고는 검사를
    통과할 수 없다. 이 PR 에서 실제로 그렇게 됐다. API 로 실행 시점에 읽어야 한다.
    """
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    step = ci.split("No fingerprint in this PR's commit messages", 1)[1].split("- name:", 1)[0]
    assert "gh pr view" in step, "본문을 API 로 읽지 않으면 얼어붙은 페이로드를 보게 된다"
    assert "github.event.pull_request.body" not in step
    assert "github.event.pull_request.title" not in step


def test_the_commit_msg_hook_calls_the_scanner():
    hook = ROOT / "scripts" / "hooks" / "commit-msg"
    assert hook.exists(), "훅이 없으면 task hooks 는 아무것도 설치하지 않는다"
    body = hook.read_text(encoding="utf-8")
    assert "fingerprint_scan.py --text" in body
    assert '"$1"' in body, "훅은 메시지 파일 경로를 받는다 — 인자를 안 쓰면 아무것도 안 본다"
