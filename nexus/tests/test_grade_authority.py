from nexus.claims.grade_authority import grade_authority
from nexus.index.gate_source import GateFact


def test_blocks_below_threshold():
    gates = [GateFact("S", "kick", "isBelowGrade", "MANAGER", "fixed", "throw_guard")]
    levels = {"BOSS": 3, "MANAGER": 2, "MEMBER": 1}
    cap = grade_authority(gates, levels)
    assert cap["MEMBER"]["blocked"] == ["S.kick"]  # level 1 < 2 → 차단
    assert cap["MANAGER"]["blocked"] == []  # level 2 == 2 → 통과
    assert cap["BOSS"]["blocked"] == []


def test_filter_gate_not_counted_as_action_block():
    # 스트림 필터(가시성)는 액션 차단이 아니므로 여집합에서 제외
    gates = [GateFact("S", "managers", "isEqualOrHigherThan", "MANAGER", "fixed", "filter")]
    levels = {"BOSS": 3, "MANAGER": 2, "MEMBER": 1}
    cap = grade_authority(gates, levels)
    assert cap["MEMBER"]["blocked"] == []


def test_relative_gate_excluded_from_fixed_complement():
    gates = [GateFact("S", "promote", "isEqualOrHigherThan", None, "relative")]
    levels = {"BOSS": 3, "MEMBER": 1}
    cap = grade_authority(gates, levels)
    assert cap["MEMBER"]["blocked"] == []  # 상대 게이트는 고정 임계 여집합에서 제외
