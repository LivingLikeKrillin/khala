import datetime

from mutqa.ledger import load_ledger
from mutqa.models import Survivor
from mutqa.report import build_report

TODAY = datetime.date(2026, 6, 10)


def _surv(line, op="op"):
    return Survivor(module="src/pkg/a.py", lineno=line, operator=op, mutation_diff=f"diff@{line}")


def _ledger(*entries):
    """entries = (key, verdict, extra-yaml-lines...) -> Ledger via YAML."""
    lines = ["waivers:"]
    for key, verdict, *extra in entries:
        lines.append(f'  - key: "{key}"')
        lines.append(f"    verdict: {verdict}")
        lines.append('    rationale: "r"')
        lines.extend(f"    {e}" for e in extra)
    return load_ledger("\n".join(lines))


def test_headline_counts_only_biting_real_gaps():
    survivors = [_surv(10), _surv(20)]
    ledger = _ledger(
        (survivors[0].key, "real-gap"),                              # bites
        (survivors[1].key, "real-gap", "waived_until: 2026-06-20"),  # silenced
    )
    md = build_report(survivors, ledger, TODAY)
    assert "real-gap: 1" in md          # only the un-waived one counts
    assert "src/pkg/a.py:10" in md
    assert "src/pkg/a.py:20" in md      # waived one still listed, not dropped


def test_equivalent_is_demoted_not_dropped():
    survivors = [_surv(10)]
    ledger = _ledger((survivors[0].key, "equivalent"))
    md = build_report(survivors, ledger, TODAY)
    assert "real-gap: 0" in md
    assert "equivalent" in md
    assert "src/pkg/a.py:10" in md


def test_silenced_real_gap_marked_waived():
    survivors = [_surv(10)]
    ledger = _ledger((survivors[0].key, "real-gap", "waived_until: 2026-06-20"))
    md = build_report(survivors, ledger, TODAY)
    assert "real-gap: 0" in md          # silenced -> not in headline
    assert "waived" in md.lower()       # but visibly marked as deferred


def test_untriaged_survivor_is_unknown():
    survivors = [_surv(10)]
    md = build_report(survivors, load_ledger(""), TODAY)
    assert "unknown" in md.lower()
    assert "real-gap: 0" in md


def test_empty_survivors_reports_zero_gaps():
    md = build_report([], load_ledger(""), TODAY)
    assert "real-gap: 0" in md
    assert "survivor 총 0" in md


def test_biting_real_gap_sorted_above_silenced():
    survivors = [_surv(10), _surv(20)]
    ledger = _ledger(
        (survivors[0].key, "equivalent"),     # silenced noise
        (survivors[1].key, "real-gap"),       # bites -> must be on top
    )
    md = build_report(survivors, ledger, TODAY)
    assert md.index("src/pkg/a.py:20") < md.index("src/pkg/a.py:10")
