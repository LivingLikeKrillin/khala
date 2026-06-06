from mutqa.models import Survivor, Verdict
from mutqa.report import build_report


def _surv(line, op="op"):
    return Survivor(module="src/pkg/a.py", lineno=line, operator=op, mutation_diff=f"diff@{line}")


def test_report_counts_real_gaps_in_headline():
    survivors = [_surv(10), _surv(20)]
    verdicts = [
        Verdict(survivors[0].key, "real-gap", "행위검증 없음"),
        Verdict(survivors[1].key, "equivalent", "관측 차이 없음"),
    ]
    md = build_report(survivors, verdicts)
    assert "real-gap: 1" in md
    assert "src/pkg/a.py:10" in md
    assert "행위검증 없음" in md


def test_equivalent_is_demoted_not_dropped():
    survivors = [_surv(10)]
    verdicts = [Verdict(survivors[0].key, "equivalent", "동치")]
    md = build_report(survivors, verdicts)
    assert "real-gap: 0" in md
    assert "동치" in md  # 접혀도 내용은 남는다


def test_missing_verdict_treated_as_unknown():
    survivors = [_surv(10)]
    md = build_report(survivors, verdicts=[])
    assert "unknown" in md.lower()  # verdict 없는 survivor도 누락되지 않음


def test_empty_survivors_reports_zero_gaps():
    md = build_report([], [])
    assert "real-gap: 0" in md
    assert "survivor 총 0" in md
