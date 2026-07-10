"""Arbiter CLI — 사람(그리고 에이전트)이 손으로 게이트를 돌린다.

지금까지 12개 도구가 전부 MCP 전용이라, 자기 승인 게이트를 돌리려면 khala.arbiter.ledger 에
대고 파이썬을 손으로 짜야 했다(2026-07-09, 그리고 이 대화에서 네 번 더). 거버넌스 코어를
사람이 못 돌리는 것은 거버넌스가 아니다.

CLI 는 MCP 서버와 **같은 함수**를 부른다 — record/critique/approve/status/check-gate. 표면만
얇게 씌운다. critic 은 주입 가능(테스트는 FakeCritic, 프로덕션은 AnthropicCritic).
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from khala.arbiter.cli import build_cli
from helpers import FakeCritic

runner = CliRunner()


@pytest.fixture
def app(docs_root):
    # root=docs_root(=docs), critic 주입. AnthropicCritic 이 API 를 때리지 않게.
    return build_cli(root=docs_root, docs=docs_root, critic=FakeCritic())


def _touch_body(docs_root):
    """accepted 처분은 본문 수정을 요구한다(해시 불변 거부). spec 에 한 줄 덧붙인다."""
    spec = next((docs_root / "specs").glob("*.md"))
    spec.write_text(spec.read_text(encoding="utf-8") + "\n수정.\n", encoding="utf-8")


def _run(app, *args):
    return runner.invoke(app, list(args))


def test_record_creates_a_spec_and_prints_its_id(app):
    r = _run(app, "record", "spec", "결제 정책 SPEC")
    assert r.exit_code == 0, r.output
    assert "SPEC-" in r.output


def test_status_lists_recorded_artifacts(app):
    _run(app, "record", "spec", "결제 정책")
    r = _run(app, "status")
    assert r.exit_code == 0
    assert "결제" in r.output or "SPEC-" in r.output


def test_critique_runs_the_critic_and_prints_issues(app):
    rec = _run(app, "record", "spec", "이벤트 아키텍처")
    aid = rec.output.strip().splitlines()[-1].strip()

    r = _run(app, "critique", aid)
    assert r.exit_code == 0, r.output
    assert "missing-invariant" in r.output      # FakeCritic 의 기본 이슈


def test_approve_takes_dispositions_from_a_file(app, docs_root, tmp_path):
    """approve 는 dispositions(리스트의 딕셔너리)를 받는다. CLI 에선 파일로 주는 게 정직하다."""
    rec = _run(app, "record", "spec", "락 개념")
    aid = rec.output.strip().splitlines()[-1].strip()
    _run(app, "critique", aid)

    disp = tmp_path / "disp.json"
    disp.write_text(json.dumps([
        {"issue_id": "I-001", "disposition": "accepted"},
    ]), encoding="utf-8")
    _touch_body(docs_root)     # accepted → 본문 수정 필요

    r = _run(app, "approve", aid, "--dispositions", str(disp), "--approver", "eisen")
    assert r.exit_code == 0, r.output

    st = _run(app, "status", aid)
    assert "approved" in st.output.lower()


def test_approve_without_a_reason_on_rejection_is_refused(app, tmp_path):
    """rejected/deferred 는 사유가 필수 — CLI 도 그 계약을 그대로 전한다."""
    rec = _run(app, "record", "spec", "인덱스 설계")
    aid = rec.output.strip().splitlines()[-1].strip()
    _run(app, "critique", aid)

    disp = tmp_path / "disp.json"
    disp.write_text(json.dumps([
        {"issue_id": "I-001", "disposition": "rejected"},   # 사유 없음
    ]), encoding="utf-8")

    r = _run(app, "approve", aid, "--dispositions", str(disp), "--approver", "eisen")
    assert r.exit_code != 0
    assert "reason" in r.output.lower() or "사유" in r.output


def test_check_gate_reports_protected_paths(app, tmp_path):
    r = _run(app, "check-gate", "specs/SPEC-x.md")
    assert r.exit_code == 0, r.output


def test_an_unknown_artifact_id_fails_cleanly_not_with_a_traceback(app):
    r = _run(app, "critique", "SPEC-does-not-exist")
    assert r.exit_code != 0
    assert "Traceback" not in r.output
