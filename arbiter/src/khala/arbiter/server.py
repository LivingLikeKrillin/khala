from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import review
from .config import ArbiterConfig
from .critique import AnthropicCritic, critique
from .gate import Gate
from .ledger import Ledger
from .promote import promote_external as _promote_external
from .publish import publish


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_app(ledger: Ledger, gate: Gate, critic, config: ArbiterConfig) -> FastMCP:
    app = FastMCP("arbiter")

    @app.tool()
    def record(type: str, title: str, slug: str | None = None) -> str:
        return ledger.record(type, title, slug)

    @app.tool(name="critique")
    def critique_doc(artifact_id: str) -> list[dict]:
        return [i.to_dict() for i in critique(ledger, artifact_id, critic, now=_utc_now)]

    @app.tool()
    def approve(artifact_id: str, dispositions: list[dict], approver: str) -> dict:
        review.approve(ledger, artifact_id, dispositions, approver, now=_utc_now)
        return {"ok": True}

    @app.tool()
    def status(artifact_id: str | None = None) -> list[dict]:
        return ledger.status(artifact_id)

    @app.tool()
    def supersede(old_id: str, new_id: str) -> dict:
        ledger.supersede(old_id, new_id)
        return {"ok": True}

    @app.tool()
    def begin_implementation(spec_id: str) -> dict:
        gate.begin_implementation(spec_id, set_by="agent")
        return {"ok": True}

    @app.tool()
    def end_implementation() -> dict:
        gate.end_implementation()
        return {"ok": True}

    @app.tool()
    def check_gate(paths: list[str]) -> dict:
        return gate.check_gate(paths, ledger, config, tool_name="mcp:check_gate")

    @app.tool()
    def index() -> str:
        return str(ledger.index())

    @app.tool(name="publish")
    def publish_doc(artifact_id: str) -> dict:
        return publish(ledger, artifact_id, config)

    @app.tool()
    def promote_external(csf: dict, type: str) -> dict:
        return _promote_external(ledger, csf, type)

    @app.tool()
    def guide(type: str) -> dict:
        """타입 운용 가이드 조회 — {type, tier, guidance}. 미지 타입은 T3+메모."""
        from . import doctypes, guidelines
        return {
            "type": type,
            "tier": doctypes.tier_of(doctypes.normalize_kind(type)),
            "guidance": guidelines.guidance_for(type) or "메모: 생애주기 없음 — 인덱싱·검색만.",
        }

    return app


def main() -> None:
    root = Path(os.environ.get("ARBITER_ROOT", "."))
    docs = Path(os.environ.get("ARBITER_DOCS", str(root / "docs")))
    config = ArbiterConfig.load(root)
    ledger = Ledger(docs, now=_utc_now)
    gate = Gate(root, now=_utc_now)
    critic = AnthropicCritic()
    build_app(ledger, gate, critic, config).run()


if __name__ == "__main__":
    main()
