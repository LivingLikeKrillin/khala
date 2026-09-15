"""앵커 검사에 이빨이 있는가 — **일부러 끊어서 확인한다.**

⛔ 이 검사기는 **초록만 보면 아무것도 증명하지 않는** 모양이다. 앵커가 전부 살아 있는 날에는
판정 논리를 통째로 지워도 초록이기 때문이다. 그래서 여기서는 양쪽을 다 본다 — 실물 매니페스트로
0을 내는 것과, 일부러 끊은 매니페스트로 1을 내는 것.

끊는 방법이 둘인 이유는 `check_doc_drift.py` 가 보는 것이 둘이기 때문이다. 문서 자체가 사라진
경우와, 문서는 있는데 그것이 가리키는 소스가 사라진 경우는 다른 사고다. 앞엣것만 잡으면
"문서는 그 자리에 있는데 서술 대상이 옮겨간" 흔한 쪽을 놓친다.

드리프트 폭은 성격이 다르다. 기본값은 보고만 하고, 상한을 줬을 때만 실패한다 — 그 분기에도
이빨이 있는지 따로 본다. 상한 분기가 죽어 있으면 `--max-commits` 는 **있으나 마나**이고,
그것은 없는 것과 구별되지 않는다.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_doc_drift  # noqa: E402


def _run(monkeypatch, manifest: pathlib.Path, *argv: str) -> int:
    monkeypatch.setattr(check_doc_drift, "MANIFEST", manifest)
    monkeypatch.setattr(sys, "argv", ["check_doc_drift.py", *argv])
    return check_doc_drift.main()


def _manifest(tmp_path: pathlib.Path, docs: object) -> pathlib.Path:
    path = tmp_path / "doc-anchors.yml"
    path.write_text(yaml.safe_dump({"docs": docs}, allow_unicode=True), encoding="utf-8")
    return path


def test_a_live_anchor_passes(tmp_path, monkeypatch, capsys):
    """대조군. 살아 있는 경로만 든 매니페스트는 통과해야 한다 — 이게 없으면 아래 두 개가
    '늘 빨간 검사기' 여도 똑같이 보인다."""
    m = _manifest(tmp_path, [{"doc": "README.md", "sources": ["scripts/check_doc_drift.py"]}])
    assert _run(monkeypatch, m) == 0
    assert "앵커 정상" in capsys.readouterr().out


def test_a_document_that_no_longer_exists_fails(tmp_path, monkeypatch, capsys):
    m = _manifest(tmp_path, [{"doc": "no/such/doc.md", "sources": ["README.md"]}])
    assert _run(monkeypatch, m) == 1
    assert "끊어진 앵커" in capsys.readouterr().out


def test_a_source_that_moved_out_from_under_a_live_document_fails(tmp_path, monkeypatch, capsys):
    """⛔ 문서가 제자리에 있다고 앵커가 성한 것이 아니다. 옮겨간 것은 **코드** 쪽이 더 흔하고,
    그 경우 문서는 멀쩡히 남아 낡은 것을 서술한다."""
    m = _manifest(tmp_path, [{"doc": "README.md", "sources": ["nexus/nexus/gone.py"]}])
    assert _run(monkeypatch, m) == 1
    out = capsys.readouterr().out
    assert "nexus/nexus/gone.py" in out


def test_one_dead_source_among_live_ones_still_fails(tmp_path, monkeypatch):
    """살아 있는 앵커가 같이 있으면 조용히 넘어가지 않는가. 넘어가면 앵커를 늘릴수록
    검사가 헐거워진다."""
    m = _manifest(tmp_path, [{
        "doc": "README.md",
        "sources": ["scripts/check_doc_drift.py", "nexus/nexus/gone.py"],
    }])
    assert _run(monkeypatch, m) == 1


def test_an_empty_manifest_is_a_configuration_error(tmp_path, monkeypatch):
    """⛔ 항목이 없는 매니페스트를 0으로 내면, 매니페스트를 통째로 비우는 것이 검사를 끄는
    가장 쉬운 방법이 된다. 그래서 0도 1도 아닌 2다."""
    assert _run(monkeypatch, _manifest(tmp_path, [])) == 2


def test_the_real_manifest_is_green(monkeypatch, capsys):
    """정본. CI 가 부르는 것과 같은 인자로 돈다."""
    assert _run(monkeypatch, check_doc_drift.MANIFEST) == 0


def test_the_real_manifest_declares_something(monkeypatch):
    """⛔ 위 검사는 **항목이 하나도 없어도** 초록일 수 있는 모양이었다 — 빈 매니페스트가 2를
    내므로 지금은 아니지만, 그 분기가 사라지면 조용히 그렇게 된다. 실물이 무엇을 지키고 있는지
    수로 한 번 더 못박는다."""
    entries = yaml.safe_load(check_doc_drift.MANIFEST.read_text(encoding="utf-8"))["docs"]
    assert len(entries) >= 10
    assert all(e.get("sources") for e in entries), "소스가 없는 항목은 아무것도 안 지킨다"


@pytest.mark.parametrize("ceiling,expected", [("-1", 1), ("100000", 0)])
def test_the_drift_ceiling_fires_in_both_directions(ceiling, expected):
    """상한 분기의 대조군 둘. 서브프로세스로 도는 이유는 이 분기가 `git rev-list` 를 쓰기
    때문이다 — 실물 이력 위에서 확인해야 뜻이 있다."""
    r = subprocess.run(
        [sys.executable, "scripts/check_doc_drift.py", "--max-commits", ceiling],
        cwd=str(ROOT), capture_output=True)
    assert r.returncode == expected, r.stdout.decode("utf-8", "replace")


def test_the_script_exits_zero_as_ci_calls_it():
    """CI 는 인자 없이 부른다. 그 호출이 실제로 0인지는 여기서만 확인된다."""
    r = subprocess.run([sys.executable, "scripts/check_doc_drift.py"],
                       cwd=str(ROOT), capture_output=True)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")
