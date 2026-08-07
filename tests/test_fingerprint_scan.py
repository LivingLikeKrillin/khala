"""지문 검사에 이가 있는가.

첫 판의 이 검사는 32자 16진을 **맥락 없이** 잡아 123건을 냈다 — k8s 평가 코퍼스의 UID 와
probe 픽스처의 콘텐츠 해시까지. 그 소음에 음성 대조군이 파묻혀서, 검사가 도는지조차 안 보였다.
많이 잡는 검사는 아무것도 안 잡는 검사와 같다.

그래서 여기서 네 가지를 다 잰다. 셋은 **발화해야** 하고 하나는 **발화하면 안 된다.**
발화만 확인하는 검사는 이 리포가 반복해서 잡아낸 무효 대조군이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))       # 리포 관례 — tests/test_ledger_integrity.py 와 같다

from fingerprint_scan import scan, tracked_files  # noqa: E402


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
    found = _with("# PFPlay note", "nexus/tests/_fp_probe.py", monkeypatch)
    assert any("pfplay" in p for p in found)


def test_a_real_page_id_in_notion_context_fires(monkeypatch):
    """맥락은 같은 줄에서 온다."""
    found = _with('P = "notion page_id d6c68901-4ec5-4385-b1ef-2d783738da6c"',
                  "nexus/tests/_fp_probe.py", monkeypatch)
    assert any("d6c68901" in p for p in found)


def test_a_page_id_fires_on_path_context_alone(monkeypatch):
    """파일 이름이 Notion 이면 그 안의 32자 ID 는 전부 의심한다 — 변수명이 무엇이든."""
    found = _with('ROOT = "d6c68901-4ec5-4385-b1ef-2d783738da6c"',
                  "nexus/tests/test_notion_fp_probe.py", monkeypatch)
    assert any("d6c68901" in p for p in found)


def test_a_uuid_without_notion_context_does_not_fire(monkeypatch):
    """**발화하면 안 되는 쪽.** k8s 코퍼스의 UID 와 콘텐츠 해시가 여기 걸리면 123건이 나오고,
    그 소음 아래에서는 진짜 지문이 안 보인다."""
    found = _with('X = "d6c68901-4ec5-4385-b1ef-2d783738da6c"  # a pod uid',
                  "nexus/tests/_fp_probe.py", monkeypatch)
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
