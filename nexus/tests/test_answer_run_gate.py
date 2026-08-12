"""총점을 언제 내면 안 되는가 — `scripts/ko_eval_answer_run` 의 관문
(SPEC-nexus-answer-quality-ruler §3.2).

**관문이 숫자 뒤에 있으면 숫자를 보고 자를 고치게 된다.** 그래서 판단은 총점 출력 이전이고,
막힌 실행도 리포트는 쓴다 — 판정할 재료가 그 리포트 안에 있기 때문이다. 파일이 `partial` 로
막혔다는 사실을 말하고, 사람의 기억이 그 자리를 대신하지 않는다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import ko_eval_answer_run as run  # noqa: E402
from scripts.ko_eval_answer_quality import aggregate, score_answer  # noqa: E402

TENANT_TITLES = {"정답 문서", "아무도 판정 안 한 문서"}


def _cite(title):
    return {"title": title, "verified": True}


def _summary(*scores):
    return aggregate(list(scores))


def test_a_clean_run_has_nothing_blocking_it():
    s = score_answer("a", "100 곡 [출처: 정답 문서]", [_cite("정답 문서")], {"정답 문서"},
                     [["100"]], known_titles=TENANT_TITLES)
    assert run.gate_reasons(_summary(s)) == []


def test_an_unadjudicated_citation_blocks_the_grade():
    s = score_answer("b", "100 곡 [출처: 아무도 판정 안 한 문서]",
                     [_cite("아무도 판정 안 한 문서")], {"정답 문서"}, [["100"]],
                     known_titles=TENANT_TITLES)
    reasons = run.gate_reasons(_summary(s))
    assert reasons and "b" in reasons[0]


def _args(tmp_path):
    """실행 인자 — 리포트 경로가 여기 실려 온다(전역 상수였을 때 회차가 서로를 덮었다)."""
    return SimpleNamespace(tag="t", tenant="default", report=tmp_path / "report.json")


def test_a_blocked_run_still_writes_the_material_it_blocked_on(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "LOCAL_DIR", tmp_path)
    s = score_answer("b", "100 곡 [출처: 아무도 판정 안 한 문서]",
                     [_cite("아무도 판정 안 한 문서")], {"정답 문서"}, [["100"]],
                     known_titles=TENANT_TITLES)
    a = _summary(s)
    run._write_report(_args(tmp_path), {"revision": 9}, SimpleNamespace(model="m"),
                      a, [{"qid": "b"}], partial=True)

    written = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert written["partial"] is True
    assert written["summary"]["adjudication_candidates"] == {"b": ["아무도 판정 안 한 문서"]}
    assert written["queries"] == [{"qid": "b"}]


def test_a_complete_run_is_not_marked_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "LOCAL_DIR", tmp_path)
    s = score_answer("a", "100 곡 [출처: 정답 문서]", [_cite("정답 문서")], {"정답 문서"},
                     [["100"]], known_titles=TENANT_TITLES)
    run._write_report(_args(tmp_path), {"revision": 9}, SimpleNamespace(model="m"),
                      _summary(s), [{"qid": "a"}], partial=False)
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["partial"] is False


def test_an_expired_label_blocks_the_grade_too():
    """만료된 라벨은 사라진 텍스트에 대한 주장이다 — 그 위에서 나온 총점은 결과가 아니다."""
    s = score_answer("a", "100 곡 [출처: 정답 문서]", [_cite("정답 문서")], {"정답 문서"},
                     [["100"]], known_titles=TENANT_TITLES)
    reasons = run.gate_reasons(_summary(s), ["pb-part-01", "pb-space-05"])
    assert reasons and "만료된 라벨 2건" in reasons[0]


def test_the_two_reasons_are_reported_separately():
    s = score_answer("b", "100 곡 [출처: 아무도 판정 안 한 문서]",
                     [_cite("아무도 판정 안 한 문서")], {"정답 문서"}, [["100"]],
                     known_titles=TENANT_TITLES)
    assert len(run.gate_reasons(_summary(s), ["pb-part-01"])) == 2


# ── 실행별 산출물 경로 ────────────────────────────────────────────────────────
#
# 리포트가 고정 경로 하나였을 때, 충분성 런의 격자(파라메트릭 2건이 **어느 질의였는지**)가 40초
# 뒤 다음 런에 덮여 복구 불가능해졌다. 누적 로그는 요약과 `ok` 맵만 담아 되살릴 수도 없었다.

def test_the_report_path_carries_the_tag_and_the_run_log_does_not():
    """리포트는 회차마다 갈라져야 하고, 누적 로그는 **한 파일이어야** 잡음 폭이 읽힌다."""
    r1, runs1 = run.resolve_paths(run.DEFAULT_LABELS, "rev6-r1")
    r2, runs2 = run.resolve_paths(run.DEFAULT_LABELS, "rev6-r2")
    assert r1 != r2, "두 회차가 같은 파일에 쓰면 앞 회차의 판정 재료가 사라진다"
    assert runs1 == runs2, "회차 간 변동은 한 파일에 모여야 폭이 된다"
    assert "rev6-r1" in r1.name and "rev6-r1" not in runs1.name


def test_a_different_label_set_writes_to_different_files():
    """라벨셋이 다르면 산출물이 자동으로 갈라진다 — 두 코퍼스의 수가 한 파일에서 섞이면 안 된다."""
    from pathlib import Path

    b_report, b_runs = run.resolve_paths(run.DEFAULT_LABELS, "r1")
    a_report, a_runs = run.resolve_paths(Path("somewhere/packa-labels.yaml"), "r1")
    assert b_report.name.startswith("packb-") and a_report.name.startswith("packa-")
    assert b_runs != a_runs


def test_an_untagged_run_still_has_a_path():
    report, _ = run.resolve_paths(run.DEFAULT_LABELS, "")
    assert report.name == "packb-answer-quality.json"
