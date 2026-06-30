from khala.arbiter.server import build_app
from khala.arbiter.ledger import Ledger
from khala.arbiter.gate import Gate
from khala.arbiter.config import ArbiterConfig
from helpers import FakeCritic


def test_build_app_registers_tools(tmp_path):
    import asyncio
    led = Ledger(tmp_path / "docs", now=lambda: "t")
    gate = Gate(tmp_path, now=lambda: "t")
    app = build_app(led, gate, FakeCritic(), ArbiterConfig())
    tools = asyncio.run(app.list_tools())  # public FastMCP API -> list[Tool]
    names = {t.name for t in tools}
    assert {"record", "critique", "approve", "status", "check_gate", "index",
            "supersede", "begin_implementation", "end_implementation", "publish",
            "promote_external", "guide"} == names
