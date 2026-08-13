"""Slack Block Kit 포매터.

Nexus 응답을 Slack 메시지로 변환한다.

**상한은 3000자다.** 이 파일은 오랫동안 "메시지 본문 4000자" 를 근거로 3800 에서 잘랐는데,
4000 은 메시지의 `text` 필드 상한이고 여기서 만드는 것은 **블록**이다. Slack 은 section 블록의
`text.text` 와 context 요소의 `text` 에 각각 3000자를 건다. 즉 자르기가 상한보다 크게 잘랐고,
단위 테스트는 `< 4100` 을 단언해 그것을 통과시켰다. 2026-08-13 첫 실사용 질문에서 그대로 죽었다:

    invalid_blocks … must be less than 3001 characters [json-pointer:/blocks/0/text/text]

그래서 자르기는 **블록을 만드는 모든 자리**를 지난다(`_clip`). 답변에만 걸어 두면 긴 문서 제목
하나가 같은 방식으로 다시 죽인다.
"""

from __future__ import annotations

#: Slack 이 블록 텍스트에 거는 하드 상한. 넘기면 메시지 전체가 `invalid_blocks` 로 거절된다.
SLACK_BLOCK_TEXT_LIMIT = 3000
#: 잘림 표시를 **포함해** 상한을 넘지 않도록 본문에 허용하는 길이.
_ELLIPSIS = "\n\n_(길어서 일부 생략되었습니다)_"
SLACK_TEXT_LIMIT = SLACK_BLOCK_TEXT_LIMIT - len(_ELLIPSIS)


def _clip(text: str) -> str:
    """블록에 넣기 전 마지막 관문. 상한 이하면 그대로, 넘으면 표시를 붙여 자른다.

    표시를 붙인 **뒤의** 길이가 상한 이하여야 한다 — 예전 코드는 3800 까지 자른 다음 안내
    문구를 덧붙여 결과가 3830 이었다. 자른 뒤에 늘리면 자른 의미가 없다.
    """
    if len(text) <= SLACK_BLOCK_TEXT_LIMIT:
        return text
    return text[:SLACK_TEXT_LIMIT] + _ELLIPSIS


def format_answer(answer_data: dict) -> list[dict]:
    """NexusResponse.data를 Slack Block Kit blocks로 변환.

    Args:
        answer_data: /search/answer 응답의 data 필드

    Returns:
        Slack Block Kit blocks 리스트
    """
    blocks: list[dict] = []

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": _clip(answer_data.get("answer", ""))},
    })

    # 구분선
    blocks.append({"type": "divider"})

    # 근거 (Evidence Snippets)
    snippets = answer_data.get("evidence_snippets", [])
    if snippets:
        evidence_lines = []
        for i, s in enumerate(snippets[:5], 1):  # 최대 5개
            title = s.get("doc_title", "(제목 없음)")
            path = s.get("section_path", "")
            score = s.get("score", 0)
            evidence_lines.append(f"*[{i}]* {title} > {path}  _(score: {score:.2f})_")

        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": _clip("\n".join(evidence_lines))}],
        })

    # 그래프 관계 (간략)
    graph = answer_data.get("graph_findings")
    if graph:
        graph_lines = []
        for e in (graph.get("designed_edges") or [])[:3]:
            from_name = e.get("from", e.get("from_name", "?"))
            to_name = e.get("to", e.get("to_name", "?"))
            etype = e.get("type", e.get("edge_type", ""))
            graph_lines.append(f"📄 {from_name} →{etype}→ {to_name}")
        for o in (graph.get("observed_edges") or [])[:3]:
            from_name = o.get("from", o.get("from_name", "?"))
            to_name = o.get("to", o.get("to_name", "?"))
            calls = o.get("call_count", o.get("calls", 0))
            graph_lines.append(f"👁 {from_name} → {to_name} ({calls} calls)")
        if graph_lines:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": _clip("\n".join(graph_lines))}],
            })

    # 출처 링크 (Provenance)
    provenance = answer_data.get("provenance", [])
    if provenance:
        prov_lines = [f"`{p.get('source_uri', p.get('doc_rid', ''))}`" for p in provenance[:3]]
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": _clip("출처: " + " | ".join(prov_lines))}],
        })

    # 라우팅/타이밍 정보
    route = answer_data.get("route_used", "")
    timing = answer_data.get("timing_ms", {})
    total_ms = timing.get("total_ms", "?")
    if route:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": _clip(f"_경로: {route} | {total_ms}ms_")}],
        })

    return blocks


def format_error(error_msg: str) -> list[dict]:
    """에러 메시지를 Slack Block Kit으로."""
    return [{
        "type": "section",
        "text": {"type": "mrkdwn", "text": _clip(f"⚠️ *오류*: {error_msg}")},
    }]
