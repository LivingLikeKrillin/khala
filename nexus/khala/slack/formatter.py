"""Slack Block Kit 포매터.

Khala 응답을 Slack 메시지로 변환한다.
Slack 메시지 본문은 4000자 제한이므로 필요 시 잘라낸다.
"""

from __future__ import annotations

SLACK_TEXT_LIMIT = 3800  # 마진 포함


def format_answer(answer_data: dict) -> list[dict]:
    """KhalaResponse.data를 Slack Block Kit blocks로 변환.

    Args:
        answer_data: /search/answer 응답의 data 필드

    Returns:
        Slack Block Kit blocks 리스트
    """
    blocks: list[dict] = []

    # 답변 본문
    answer_text = answer_data.get("answer", "")
    if len(answer_text) > SLACK_TEXT_LIMIT:
        answer_text = answer_text[:SLACK_TEXT_LIMIT] + "\n\n_(답변이 길어 일부 생략되었습니다)_"

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": answer_text},
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
            "elements": [{"type": "mrkdwn", "text": "\n".join(evidence_lines)}],
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
                "elements": [{"type": "mrkdwn", "text": "\n".join(graph_lines)}],
            })

    # 출처 링크 (Provenance)
    provenance = answer_data.get("provenance", [])
    if provenance:
        prov_lines = [f"`{p.get('source_uri', p.get('doc_rid', ''))}`" for p in provenance[:3]]
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "출처: " + " | ".join(prov_lines)}],
        })

    # 라우팅/타이밍 정보
    route = answer_data.get("route_used", "")
    timing = answer_data.get("timing_ms", {})
    total_ms = timing.get("total_ms", "?")
    if route:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"_경로: {route} | {total_ms}ms_"}],
        })

    return blocks


def format_error(error_msg: str) -> list[dict]:
    """에러 메시지를 Slack Block Kit으로."""
    return [{
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"⚠️ *오류*: {error_msg}"},
    }]
