"""캘리브레이션 답변 조립 — 결정론 값은 단정, soft/모름은 정직히 표기.

신뢰성 = 캘리브레이션: 시스템은 결코 거짓말하지 않는다.
모르면 확신하지 않고, 코드 변경(드리프트)이 있으면 드러낸다.
"""

from __future__ import annotations

from khala.claims.value_query import ValueAnswer


def format_value_answer(concept: str, answers: list[ValueAnswer]) -> str:
    if not answers:
        return f"'{concept}'에 등록된 값 claim이 없습니다. (모름 — 추측하지 않음)"
    # 해결된(값 있는) 답이 하나라도 있으면 그것만 보여 신뢰를 지킨다.
    # 전부 미해결(소스 못 찾음 등)일 때만 정직하게 그대로 표기.
    resolved = [a for a in answers if a.value is not None]
    shown = resolved if resolved else answers
    lines: list[str] = []
    for a in shown:
        if a.value is not None and a.confidence == "high" and a.fresh:
            base = (
                f"- {a.statement}: **현재 {a.value}** "
                f"(확실: 코드 상수 `{a.source}`, 조회 시점 기준)"
            )
            if a.drifted:
                base += f" ⚠️ {a.note}"
            lines.append(base)
        elif a.value is None:
            lines.append(f"- {a.statement}: 값 확인 실패 — {a.note}. (확신 없음)")
        else:
            lines.append(
                f"- {a.statement}: {a.value} "
                f"(신뢰 {a.confidence}, {'fresh' if a.fresh else 'stale'})"
            )
    return "\n".join(lines)
