from __future__ import annotations

from khala.arbiter import doctypes


def test_known_type_resolves_tier_and_lifecycle():
    assert doctypes.tier_of("ADR") == "T1"
    assert doctypes.lifecycle_of("ADR") == "governed"
    assert doctypes.tier_of("PRD") == "T2"
    assert doctypes.lifecycle_of("PRD") == "tracked"
    assert doctypes.tier_of("NOTE") == "T3"
    assert doctypes.lifecycle_of("NOTE") == "memo"


def test_unknown_type_falls_back_to_default_tier():
    assert doctypes.tier_of("WHATEVER") == "T3"
    assert doctypes.lifecycle_of("WHATEVER") == "memo"


def test_tier_lifecycle_invariant_holds_for_all_registry_types():
    # 1:1 불변식: 모든 등록 타입의 lifecycle 은 tier 에서 유도된 값과 일치.
    reg = doctypes.load_registry()
    for name, dt in reg.items():
        assert doctypes.lifecycle_of(name) == doctypes.LIFECYCLE_BY_TIER[dt.tier]


def test_normalize_kind_resolves_legacy_csf_tokens():
    assert doctypes.normalize_kind("SPEC") == "DESIGN"   # 레거시→정본
    assert doctypes.normalize_kind("FLOW") == "NOTE"
    assert doctypes.normalize_kind("ADR") == "ADR"        # 이미 정본이면 그대로
    assert doctypes.normalize_kind("MYSTERY") == "MYSTERY"  # 미지는 그대로(이후 tier_of 가 T3)


def test_arbiter_type_and_promotability():
    assert doctypes.arbiter_type_of("ADR") == "adr"
    assert doctypes.arbiter_type_of("DESIGN") == "spec"
    assert doctypes.arbiter_type_of("RFC") == "spec"
    assert doctypes.arbiter_type_of("PRD") is None      # T2 는 승격 불가
    assert doctypes.is_promotable("ADR") is True
    assert doctypes.is_promotable("PRD") is False
    assert doctypes.is_promotable("NOTE") is False
