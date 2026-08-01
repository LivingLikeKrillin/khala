"""문서 생애주기 MCP 도구 — SPEC-nexus-document-lifecycle §4.6.

에이전트는 웹 UI 와 **같은 엔드포인트**를 쓴다. 그리고 사람이 확인 패널에서 읽는 문장을
에이전트도 응답에서 읽는다 — 파괴적 행위의 결과를 한쪽만 아는 일은 없다.

DB 불필요: _api_call 을 가로채 HTTP 계약만 고정한다.
"""

from __future__ import annotations

import pytest

from nexus.mcp import server as mcp_server

_TOOLS = ("nexus_documents_search", "nexus_document_hide",
          "nexus_document_restore", "nexus_unsupersede")


def test_the_four_lifecycle_tools_are_registered(mcp_tools):
    registered = set(mcp_tools)
    assert set(_TOOLS) <= registered, f"누락: {set(_TOOLS) - registered}"


def test_unsupersede_makes_reason_required_at_the_tool_boundary(mcp_tools):
    """사유 없는 되돌림은 서버가 400 으로 막지만, 에이전트는 그 전에 알아야 한다."""
    schema = mcp_tools["nexus_unsupersede"].input_schema
    assert "reason" in schema.get("required", []), schema


@pytest.fixture
def calls(monkeypatch):
    seen: list[tuple] = []
    reply: dict = {"success": True, "data": {}}

    async def fake(method, path, **kwargs):
        seen.append((method, path, kwargs.get("json"), kwargs.get("params")))
        return reply

    monkeypatch.setattr(mcp_server, "_api_call", fake)
    return seen, (lambda d: reply.update(d))


async def test_hide_hits_the_same_endpoint_as_the_web_view(calls):
    seen, set_reply = calls
    set_reply({"success": True, "data": {"rid": "doc_a", "result": "hidden"}})

    out = await mcp_server.nexus_document_hide(rid="doc_a")

    assert seen[0][0] == "post" and seen[0][1] == "/documents/doc_a/hide"
    # 사람이 확인 패널에서 읽는 문장과 같은 문장 — 무엇이 일어났는지 에이전트도 안다
    assert "검색에서 사라집니다" in out
    assert "nexus_document_restore" in out          # 되돌리기 손잡이


async def test_restore_reports_the_result_in_prose_not_a_raw_token(calls):
    seen, set_reply = calls
    set_reply({"success": True, "data": {"rid": "doc_a", "result": "restored"}})

    out = await mcp_server.nexus_document_restore(rid="doc_a")
    assert seen[0][1] == "/documents/doc_a/restore"
    assert "다시 검색에 나타납니다" in out


@pytest.mark.parametrize(
    ("tool", "kwargs", "code", "expected"),
    [
        ("nexus_document_restore", {"rid": "doc_a"}, "use_unsupersede", "nexus_unsupersede"),
        ("nexus_document_hide", {"rid": "doc_a"}, "already_superseded", "대체"),
        ("nexus_unsupersede", {"rid": "doc_a", "reason": " "}, "reason_required", "사유"),
    ],
)
async def test_machine_error_codes_are_translated_for_the_caller(calls, tool, kwargs, code, expected):
    """API 는 기계코드로 거절한다. 그걸 그대로 뱉으면 에이전트는 다음에 뭘 할지 모른다."""
    _, set_reply = calls
    set_reply({"success": False, "error": code})

    out = await getattr(mcp_server, tool)(**kwargs)
    assert expected in out


async def test_unsupersede_sends_the_reason_and_surfaces_a_broken_chain(calls):
    seen, set_reply = calls
    set_reply({"success": False, "error": "doc_v2 가 아직 superseded 상태다"})

    out = await mcp_server.nexus_unsupersede(rid="doc_v1", reason="오지정")

    assert seen[0][1] == "/documents/doc_v1/unsupersede"
    assert seen[0][2] == {"reason": "오지정"}
    assert "doc_v2" in out                          # 막는 문서를 이름으로 전달한다


async def test_documents_search_passes_filters_and_prints_rids(calls):
    """에이전트가 hide 할 rid 를 얻는 유일한 경로다 — rid 가 출력에 없으면 도구가 막힌다."""
    seen, set_reply = calls
    set_reply({"success": True, "data": {"total": 1, "documents": [
        {"rid": "doc_a", "title": "결제 정책", "status": "active",
         "origin": "notion", "origin_url": "https://www.notion.so/x", "chunk_count": 3},
    ]}})

    out = await mcp_server.nexus_documents_search(q="결제", status="active")

    assert seen[0][0] == "get" and seen[0][1] == "/documents"
    assert seen[0][3]["q"] == "결제" and seen[0][3]["status"] == "active"
    assert "doc_a" in out and "결제 정책" in out


async def test_supersede_hands_back_the_undo_handle(calls):
    """파괴적 행위의 응답은 그것을 되돌리는 방법을 함께 준다 — rid 없이는 취소할 수 없다."""
    seen, set_reply = calls
    set_reply({"success": True, "data": {
        "result": "superseded", "old_rid": "doc_v1", "new_rid": "doc_v2"}})

    out = await mcp_server.nexus_supersede(old_ref="specs/v1.md", new_ref="specs/v2.md")

    assert "nexus_unsupersede" in out and "doc_v1" in out
