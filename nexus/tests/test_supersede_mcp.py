"""MCP supersede 스모크 — 등록/개명 확인 (스펙 §6, DB 불필요·순수 메타데이터 검증).

nexus_supersede 도구가 등록되어 있고, 파라미터가 old_ref/new_ref(개명 후)이며
옛 이름(old_rid/new_rid)이 남아있지 않은지만 확인한다.
"""

from nexus.mcp.server import mcp


def test_supersede_tool_registered():
    """nexus_supersede 도구가 MCP 서버에 등록되어 있는지."""
    tool_names = set(mcp._tool_manager._tools.keys())
    assert "nexus_supersede" in tool_names, f"등록된 도구: {sorted(tool_names)}"


def test_supersede_tool_uses_ref_params_not_rid():
    """파라미터가 old_ref/new_ref(개명 후)이고 old_rid/new_rid 는 없는지."""
    tool = mcp._tool_manager._tools["nexus_supersede"]
    props = tool.parameters.get("properties", {})
    assert "old_ref" in props
    assert "new_ref" in props
    assert "old_rid" not in props
    assert "new_rid" not in props
