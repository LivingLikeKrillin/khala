"""MCP 답변 텍스트에 붙는 줄들 — `mcp` 패키지 없이 도는 순수 함수.

`server.py` 는 `mcp` 가 있어야 import 되므로, 텍스트를 만드는 부분은 여기로 빼서 호스트에서도
검사한다. HTTP 응답의 `code_values`(코드 현재 값 + 소유자 판정)를 사람이 읽는 줄로 옮긴다.
한 표면만 빠뜨리면 그 표면의 소비자만 판정을 못 본다 — 에이전트가 타는 표면이 바로 이것이다.
"""

from __future__ import annotations


def code_values_lines(data: dict) -> list[str]:
    rows = (data or {}).get("code_values") or []
    if not rows:
        return []
    lines = ["\n--- 코드 값 ---"]
    for r in rows:
        value = r.get("value") or "(코드에서 읽지 못함)"
        where = f" ({r['source']})" if r.get("source") else ""
        drift = " · 심은 뒤 코드가 바뀜" if r.get("drifted") else ""
        lines.append(f"- {r.get('statement', '')}: {value}{where}{drift}")
        if r.get("ruled_by") and r.get("ruled_on"):
            decided = r["ruled_value"] if r.get("ruled_value") is not None else "값 미정"
            src = f" — 정본: {r['ruled_source']}" if r.get("ruled_source") else ""
            note = f" — {r['ruling_note']}" if r.get("ruling_note") else ""
            lines.append(f"  판정: {decided}{src} ({r['ruled_by']}, {r['ruled_on']}){note}")
            if r.get("ruling_conflict"):
                lines.append(f"  ⚠ 코드의 현재 값 {r.get('value')} 은(는) 판정과 어긋남 (판정 {decided})")
    return lines
