from khala.claims.grade_authority import grade_authority
from khala.index.gate_source import GateFact


def test_blocks_below_threshold():
    gates = [GateFact("S", "kick", "isBelowGrade", "MANAGER", "fixed")]
    levels = {"BOSS": 3, "MANAGER": 2, "MEMBER": 1}
    cap = grade_authority(gates, levels)
    assert cap["MEMBER"]["blocked"] == ["S.kick"]  # level 1 < 2 → 차단
    assert cap["MANAGER"]["blocked"] == []  # level 2 == 2 → 통과
    assert cap["BOSS"]["blocked"] == []


def test_relative_gate_excluded_from_fixed_complement():
    gates = [GateFact("S", "promote", "isEqualOrHigherThan", None, "relative")]
    levels = {"BOSS": 3, "MEMBER": 1}
    cap = grade_authority(gates, levels)
    assert cap["MEMBER"]["blocked"] == []  # 상대 게이트는 고정 임계 여집합에서 제외
