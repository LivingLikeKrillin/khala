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


def test_a_blocked_run_still_writes_the_material_it_blocked_on(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(run, "REPORT", tmp_path / "report.json")
    s = score_answer("b", "100 곡 [출처: 아무도 판정 안 한 문서]",
                     [_cite("아무도 판정 안 한 문서")], {"정답 문서"}, [["100"]],
                     known_titles=TENANT_TITLES)
    a = _summary(s)
    run._write_report(SimpleNamespace(tag="t"), {"revision": 9}, SimpleNamespace(model="m"),
                      a, [{"qid": "b"}], partial=True)

    written = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert written["partial"] is True
    assert written["summary"]["adjudication_candidates"] == {"b": ["아무도 판정 안 한 문서"]}
    assert written["queries"] == [{"qid": "b"}]


def test_a_complete_run_is_not_marked_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(run, "REPORT", tmp_path / "report.json")
    s = score_answer("a", "100 곡 [출처: 정답 문서]", [_cite("정답 문서")], {"정답 문서"},
                     [["100"]], known_titles=TENANT_TITLES)
    run._write_report(SimpleNamespace(tag="t"), {"revision": 9}, SimpleNamespace(model="m"),
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
