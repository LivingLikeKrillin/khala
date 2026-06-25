"""타입별 운용 가이드라인 (S2). 딥리서치(2026-06-25) 근거.

각 축-A 타입을 어떻게 저작·관리·운용할지 요지+근거. promote 반환과 MCP guide 도구가
소비한다(inert 문서 아님). 타입 정규화는 doctypes.normalize_kind 재사용(레거시 SPEC→DESIGN).
"""

from __future__ import annotations

from . import doctypes

# 모든 타입 공통 — doc-rot 최강 치료제(SWE at Google ch10).
_CROSS_CUTTING = "공통: owner 명시 · 소스컨트롤 · 이슈 추적 · 정기 staleness 점검(docs-as-code)."

# 축-A 타입 → 운용 요지(근거). 간결(읽히게).
GUIDANCE = {
    "ADR": (
        "불변+supersede: accepted 후 수정 금지 — 변경은 새 ADR로 대체(old→superseded). "
        "5섹션(Title/Status/Context/Decision/Consequences). 상태: proposed→accepted→"
        "deprecated/superseded. (arc42 §9, Nygard, AWS)"
    ),
    "RFC": (
        "계층적 게이트: substantial 변경만 정식 승인 — 버그픽스·리팩터는 게이트 없음. "
        "active→complete(구현 후)→inactive. 승인≠구현 보장. (Rust RFC 0002)"
    ),
    "DESIGN": (
        "단일 목적 + 승인 게이트: 한 문서 한 목적, 구현 근거이므로 리뷰·승인 후 발효, "
        "변경은 supersede. (SWE at Google ch10)"
    ),
    "PRD": (
        "추적·제자리 개정: 버전+owner로 추적, SPEC이 파생되므로 변경 시 하위 stale 점검(drift). "
        "승인 게이트 없음."
    ),
    "RUNBOOK": (
        "운영 절차(how-to-operate): 코드/인프라 변경과 함께 갱신, 정기 staleness 재확인 필수. "
        "(doc-rot 최대 피해 영역, Aghajani ICSE'19)"
    ),
    "POSTMORTEM": (
        "고정 내용(사건/영향/완화/근본원인/후속) + 리뷰 필수(미리뷰=없는 것), "
        "비난 없는(blameless). 승인 게이트 없음. (Google SRE)"
    ),
    "NOTE": "메모: 생애주기 없음 — 인덱싱·검색만. 정본이 되면 promote로 격상.",
}


def guidance_for(type_name: str) -> str | None:
    """축-A 타입(또는 레거시 토큰) → 운용 가이드 + 공통 푸터. 미등록 None."""
    g = GUIDANCE.get(doctypes.normalize_kind(type_name))
    return f"{g}\n{_CROSS_CUTTING}" if g else None
