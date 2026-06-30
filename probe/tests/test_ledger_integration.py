"""M2 수용 테스트 — 실 Arbiter survivor로 원장 라운드트립을 dogfood.

운영 1회전(2026-06-07)이 17 survivor 중 3건을 equivalent로 판정했다. 원장이 그 3건을
흡수하면 재실행 시 재심의 대상(new_survivors)이 14건으로 줄고, real-gap 14건이 무는지를
실데이터로 고정한다. M1의 cr_dump_arbiter.jsonl 픽스처를 그대로 오라클로 쓴다.
"""

import datetime

from khala.probe.extract import extract_survivors
from khala.probe.ledger import absorb, biting, dump_ledger, load_ledger, new_survivors
from khala.probe.models import Verdict

TODAY = datetime.date(2026, 6, 10)

# 운영 1회전에서 Critic이 equivalent로 강등한 3건(결정론 증거 근거).
EQUIVALENTS = [
    Verdict("src/khala/arbiter/review.py:33:core/ReplaceComparisonOperator_Eq_LtE", "equivalent",
            "disp가 _VALID 3값으로 제약 -> <=가 ==와 동일"),
    Verdict("src/khala/arbiter/review.py:47:core/ReplaceComparisonOperator_Is_Eq", "equivalent",
            "art.type은 항상 enum 싱글톤 -> is/== 일치"),
    Verdict("src/khala/arbiter/review.py:47:core/ReplaceComparisonOperator_Is_LtE", "equivalent",
            "현 2멤버 도메인에서 <= 가 is ADR과 동일"),
]


def _arbiter_survivors(fixtures_dir):
    return extract_survivors((fixtures_dir / "cr_dump_arbiter.jsonl").read_text(encoding="utf-8"))


def test_absorbing_equivalents_shrinks_retriage_set(fixtures_dir):
    survivors = _arbiter_survivors(fixtures_dir)
    assert len(survivors) == 17  # PoC/M1 기준

    empty = load_ledger("")
    assert len(new_survivors(survivors, empty)) == 17  # 첫 실행: 전량 재심의

    ledger = absorb(empty, EQUIVALENTS, TODAY)
    fresh = new_survivors(survivors, ledger)
    assert len(fresh) == 14  # 재실행: equivalent 3건은 더 이상 재심의 안 함
    assert all("Eq_LtE" not in s.operator or s.lineno != 33 for s in fresh)


def test_equivalents_persist_across_dump_reload(fixtures_dir):
    survivors = _arbiter_survivors(fixtures_dir)
    ledger = absorb(load_ledger(""), EQUIVALENTS, TODAY)
    reloaded = load_ledger(dump_ledger(ledger))  # 파일에 썼다 다시 읽어도
    assert len(new_survivors(survivors, reloaded)) == 14


def test_real_gaps_bite_after_full_triage(fixtures_dir):
    survivors = _arbiter_survivors(fixtures_dir)
    # 전량 triage 결과를 원장에 흡수: equivalent 3 + real-gap 14
    real_gap_keys = [s.key for s in survivors
                     if s.key not in {v.survivor_key for v in EQUIVALENTS}]
    verdicts = EQUIVALENTS + [Verdict(k, "real-gap", "행위검증 공백") for k in real_gap_keys]
    ledger = absorb(load_ledger(""), verdicts, TODAY)

    biters = biting(survivors, ledger, TODAY)
    assert len(biters) == 14  # equivalent 3건 제외한 real-gap만 문다
    assert new_survivors(survivors, ledger) == []  # 전부 기록됨 -> 재심의 0
