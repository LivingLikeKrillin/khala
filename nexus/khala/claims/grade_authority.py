"""등급별 권한 도출 (여집합) — gate 사실 + 등급 레벨 → "등급 G가 차단되는 액션".

이것이 Archon 자체 핵심(도출 레이어): OSS(tree-sitter)가 추출한 gate 후보 위에서
"창발적/여집합" 질문("CLUBBER가 뭘 하나")을 계산한다. CodeQL 불필요.

해석: 고정 임계 게이트 `if (actor.isBelowGrade(GradeType.X)) throw` = "액션에 ≥X 필요".
상대 게이트(동적 등급 비교 = '자기 등급 이상 금지')는 고정 임계 여집합에서 제외(별도 규칙).
"""

from __future__ import annotations

from khala.index.gate_source import GateFact


def grade_authority(gates: list[GateFact], levels: dict[str, int]) -> dict[str, dict]:
    """각 등급에 대해 고정-임계 게이트 중 통과 못 하는(차단) 액션 목록을 도출."""
    # 액션(class.method) → 요구 최고 레벨
    required: dict[str, int] = {}
    for g in gates:
        if g.kind == "fixed" and g.grade in levels:
            key = f"{g.class_name}.{g.method}"
            required[key] = max(required.get(key, 0), levels[g.grade])

    out: dict[str, dict] = {}
    for grade, lv in sorted(levels.items(), key=lambda x: -x[1]):
        blocked = sorted([action for action, req in required.items() if req > lv])
        out[grade] = {"level": lv, "blocked": blocked}
    return out
