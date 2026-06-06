import datetime

from mutqa.ledger import Ledger, is_silenced
from mutqa.models import Survivor

# 정렬 우선순위: 무는 real-gap이 최상단, 침묵된 것(동치/저가치/유예된 real-gap)은 하단.
_ORDER = {"real-gap": 0, "unknown": 1, "low-value": 2, "equivalent": 3, "waived": 4}


def _row(survivor: Survivor, ledger: Ledger, today: datetime.date):
    """survivor -> (label, rationale, silenced, sort_bucket)."""
    waiver = ledger.waivers.get(survivor.key)
    if waiver is None:
        return ("unknown", "(triage 안 됨)", False, "unknown")
    verdict = waiver["verdict"]
    rationale = waiver.get("rationale", "")
    silenced = is_silenced(waiver, today)
    if verdict == "real-gap" and silenced:
        return ("real-gap (waived)", rationale, True, "waived")
    return (verdict, rationale, silenced, verdict)


def build_report(survivors: list[Survivor], ledger: Ledger, today: datetime.date) -> str:
    """survivor + 원장 -> 사람이 읽는 어드바이저리 마크다운.

    headline = 무는 real-gap 수(침묵된 real-gap·동치 노이즈 제외). 침묵된 항목도
    누락하지 않고 하단에 강등 표시한다.
    """
    rows = [(s, *_row(s, ledger, today)) for s in survivors]
    rows.sort(key=lambda r: _ORDER.get(r[4], 1))

    biting = sum(1 for _, label, _, silenced, _ in rows if label == "real-gap" and not silenced)
    lines = [
        "# mutqa 어드바이저리 리포트",
        "",
        f"**unwaived real-gap: {biting}** · survivor 총 {len(survivors)}",
        "",
    ]
    for s, label, rationale, _silenced, _bucket in rows:
        lines.append(f"- `{s.module}:{s.lineno}` [{label}] {s.operator}")
        lines.append(f"    - {rationale}")
    return "\n".join(lines)
