"""MCP supersede 스모크 — 등록/개명 확인 (스펙 §6, DB 불필요·순수 메타데이터 검증).

nexus_supersede 도구가 등록되어 있고, 파라미터가 old_ref/new_ref(개명 후)이며
옛 이름(old_rid/new_rid)이 남아있지 않은지만 확인한다.
"""

def test_supersede_tool_registered(mcp_tools):
    """nexus_supersede 도구가 MCP 서버에 등록되어 있는지."""
    assert "nexus_supersede" in mcp_tools, f"등록된 도구: {sorted(mcp_tools)}"


def test_supersede_tool_uses_ref_params_not_rid(mcp_tools):
    """파라미터가 old_ref/new_ref(개명 후)이고 old_rid/new_rid 는 없는지."""
    props = mcp_tools["nexus_supersede"].input_schema.get("properties", {})
    assert "old_ref" in props
    assert "new_ref" in props
    assert "old_rid" not in props
    assert "new_rid" not in props
