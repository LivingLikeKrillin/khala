"""MCP Server 도구 정의 테스트 — API 호출 없이 tool 메타데이터 검증."""

from khala.mcp.server import mcp


class TestMCPToolRegistration:
    """MCP 서버에 등록된 도구 검증."""

    def test_server_name(self):
        assert mcp.name == "Khala"

    def test_tools_registered(self):
        """필수 도구 6개가 등록되어 있는지."""
        tool_names = set(mcp._tool_manager._tools.keys())
        expected = {
            "khala_search",
            "khala_answer",
            "khala_graph",
            "khala_suggest",
            "khala_diff",
            "khala_status",
        }
        assert expected.issubset(tool_names), f"Missing: {expected - tool_names}"

    def test_search_tool_schema(self):
        """khala_search 도구의 파라미터 스키마 검증."""
        tool = mcp._tool_manager._tools["khala_search"]
        schema = tool.parameters
        props = schema.get("properties", {})
        assert "query" in props
        assert "top_k" in props
        assert "tenant" in props

    def test_answer_tool_schema(self):
        tool = mcp._tool_manager._tools["khala_answer"]
        schema = tool.parameters
        props = schema.get("properties", {})
        assert "query" in props

    def test_graph_tool_schema(self):
        tool = mcp._tool_manager._tools["khala_graph"]
        schema = tool.parameters
        props = schema.get("properties", {})
        assert "entity" in props
        assert "hops" in props

    def test_suggest_tool_schema(self):
        tool = mcp._tool_manager._tools["khala_suggest"]
        schema = tool.parameters
        props = schema.get("properties", {})
        assert "query" in props

    def test_diff_tool_schema(self):
        tool = mcp._tool_manager._tools["khala_diff"]
        schema = tool.parameters
        props = schema.get("properties", {})
        assert "tenant" in props

    def test_status_tool_has_no_required_params(self):
        tool = mcp._tool_manager._tools["khala_status"]
        schema = tool.parameters
        required = schema.get("required", [])
        assert len(required) == 0

    def test_tool_descriptions_in_korean(self):
        """도구 설명이 한국어로 작성되어 있는지."""
        for name, tool in mcp._tool_manager._tools.items():
            desc = tool.description or ""
            # 최소한 한글이 포함되어야 함
            has_korean = any("\uac00" <= c <= "\ud7a3" for c in desc)
            assert has_korean, f"{name} 도구의 설명에 한국어가 없습니다"


class TestAPICallWrapper:
    """_api_call 헬퍼 함수 시그니처 검증."""

    def test_api_call_is_async(self):
        from khala.mcp.server import _api_call
        import inspect
        assert inspect.iscoroutinefunction(_api_call)

    def test_api_url_from_env(self):
        from khala.mcp.server import KHALA_API_URL
        assert KHALA_API_URL  # 기본값이라도 설정됨
