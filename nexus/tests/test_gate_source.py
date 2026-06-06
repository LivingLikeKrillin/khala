from pathlib import Path

from khala.index.gate_source import extract_gates, extract_grade_levels

FIX = Path(__file__).parent / "fixtures" / "grade"


def test_extract_grade_levels():
    levels = extract_grade_levels(FIX, "GradeType")
    assert levels == {"BOSS": 3, "MANAGER": 2, "MEMBER": 1}


def test_extract_fixed_gate():
    gates = extract_gates(FIX)
    fixed = [g for g in gates if g.kind == "fixed"]
    assert any(
        g.method == "kick" and g.grade == "MANAGER" and g.check == "isBelowGrade"
        for g in fixed
    )


def test_extract_relative_gate():
    gates = extract_gates(FIX)
    assert any(
        g.method == "promote" and g.check == "isEqualOrHigherThan" and g.kind == "relative"
        for g in gates
    )


def test_ungated_method_absent():
    gates = extract_gates(FIX)
    assert all(g.method != "join" for g in gates)
