from specledger.server import build_app
from specledger.ledger import Ledger
from specledger.gate import Gate
from specledger.config import SpecledgerConfig
from helpers import FakeCritic


def test_build_app_registers_tools(tmp_path):
    import asyncio
    led = Ledger(tmp_path / "docs", now=lambda: "t")
    gate = Gate(tmp_path, now=lambda: "t")
    app = build_app(led, gate, FakeCritic(), SpecledgerConfig())
    tools = asyncio.run(app.list_tools())  # public FastMCP API -> list[Tool]
    names = {t.name for t in tools}
    assert {"record", "critique", "approve", "status", "check_gate", "index",
            "supersede", "begin_implementation", "end_implementation", "publish",
            "promote_external", "guide"} == names
