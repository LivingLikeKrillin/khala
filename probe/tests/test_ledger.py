import datetime

from khala.probe.ledger import absorb, biting, dump_ledger, is_silenced, load_ledger, new_survivors
from khala.probe.models import Survivor, Verdict

TODAY = datetime.date(2026, 6, 10)


def _surv(line, op="op"):
    return Survivor(module="review.py", lineno=line, operator=op, mutation_diff="")


def test_new_survivors_excludes_keys_already_in_ledger():
    ledger = load_ledger(
        """
        waivers:
          - key: "review.py:10:op"
            verdict: equivalent
            rationale: "no observable diff"
            recorded: 2026-06-06
        """
    )
    survivors = [_surv(10), _surv(20)]
    fresh = new_survivors(survivors, ledger)
    assert [s.lineno for s in fresh] == [20]  # 10 known, 20 new


def test_equivalent_waiver_is_silenced_forever():
    waiver = {"key": "k", "verdict": "equivalent", "rationale": "no diff"}
    assert is_silenced(waiver, TODAY) is True


def test_low_value_waiver_is_silenced_forever():
    waiver = {"key": "k", "verdict": "low-value", "rationale": "log string"}
    assert is_silenced(waiver, TODAY) is True


def test_active_real_gap_waiver_is_silenced_until_expiry():
    waiver = {"key": "k", "verdict": "real-gap", "waived_until": datetime.date(2026, 6, 20)}
    assert is_silenced(waiver, TODAY) is True  # today 6/10 <= 6/20


def test_expired_real_gap_waiver_resurfaces():
    waiver = {"key": "k", "verdict": "real-gap", "waived_until": datetime.date(2026, 6, 5)}
    assert is_silenced(waiver, TODAY) is False  # today 6/10 > 6/5 -> bites again


def test_real_gap_without_waived_until_is_not_silenced():
    waiver = {"key": "k", "verdict": "real-gap", "rationale": "known gap, not deferred"}
    assert is_silenced(waiver, TODAY) is False  # real-gap must be explicitly waived to silence


def test_absorb_records_new_verdicts_with_recorded_date():
    ledger = load_ledger("")
    verdicts = [Verdict("review.py:10:op", "equivalent", "no observable diff")]
    updated = absorb(ledger, verdicts, TODAY)
    w = updated.waivers["review.py:10:op"]
    assert w["verdict"] == "equivalent"
    assert w["rationale"] == "no observable diff"
    assert w["recorded"] == TODAY


def test_absorb_preserves_existing_waivers():
    ledger = load_ledger(
        """
        waivers:
          - key: "review.py:99:op"
            verdict: real-gap
            waived_until: 2026-07-01
            rationale: "deferred by hand"
        """
    )
    updated = absorb(ledger, [Verdict("review.py:10:op", "equivalent", "x")], TODAY)
    # new verdict added, hand-set deferral untouched
    assert updated.waivers["review.py:10:op"]["verdict"] == "equivalent"
    assert updated.waivers["review.py:99:op"]["waived_until"] == datetime.date(2026, 7, 1)


def test_absorb_does_not_mutate_input_ledger():
    ledger = load_ledger("")
    absorb(ledger, [Verdict("review.py:10:op", "equivalent", "x")], TODAY)
    assert ledger.waivers == {}  # original unchanged


def test_dump_then_load_roundtrips():
    ledger = absorb(load_ledger(""), [Verdict("review.py:10:op", "equivalent", "no diff")], TODAY)
    reloaded = load_ledger(dump_ledger(ledger))
    w = reloaded.waivers["review.py:10:op"]
    assert w["verdict"] == "equivalent"
    assert w["rationale"] == "no diff"
    assert w["recorded"] == TODAY  # date survives the round-trip


def test_dump_uses_waivers_top_level_key():
    text = dump_ledger(load_ledger(""))
    assert "waivers:" in text  # spec §5 형식


def test_biting_returns_only_unsilenced_real_gaps():
    survivors = [_surv(10), _surv(20), _surv(30), _surv(40)]
    ledger = load_ledger(
        """
        waivers:
          - key: "review.py:10:op"
            verdict: real-gap
            rationale: "live gap"
          - key: "review.py:20:op"
            verdict: equivalent
            rationale: "no diff"
          - key: "review.py:30:op"
            verdict: real-gap
            waived_until: 2026-06-20
            rationale: "deferred"
          - key: "review.py:40:op"
            verdict: real-gap
            waived_until: 2026-06-05
            rationale: "expired -> bites again"
        """
    )
    biters = biting(survivors, ledger, TODAY)  # TODAY = 6/10
    assert sorted(s.lineno for s in biters) == [10, 40]


def test_biting_ignores_survivors_absent_from_ledger():
    # un-triaged survivors have no stored verdict -> not counted as biting yet
    survivors = [_surv(10)]
    biters = biting(survivors, load_ledger(""), TODAY)
    assert biters == []
