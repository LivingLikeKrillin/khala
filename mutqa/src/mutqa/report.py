from mutqa.models import Survivor, Verdict

_ORDER = {"real-gap": 0, "unknown": 1, "low-value": 2, "equivalent": 3}


def build_report(survivors: list[Survivor], verdicts: list[Verdict]) -> str:
    by_key = {v.survivor_key: v for v in verdicts}
    rows = []
    for s in survivors:
        v = by_key.get(s.key)
        rows.append((s, v.verdict if v else "unknown", v.rationale if v else "(triage 안 됨)"))
    rows.sort(key=lambda r: _ORDER.get(r[1], 1))

    real_gaps = sum(1 for _, verdict, _ in rows if verdict == "real-gap")
    lines = [
        "# mutqa 어드바이저리 리포트",
        "",
        f"**unwaived real-gap: {real_gaps}** · survivor 총 {len(survivors)}",
        "",
    ]
    for s, verdict, rationale in rows:
        lines.append(f"- `{s.module}:{s.lineno}` [{verdict}] {s.operator}")
        lines.append(f"    - {rationale}")
    return "\n".join(lines)
