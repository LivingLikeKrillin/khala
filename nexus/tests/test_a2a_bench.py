"""Transport-overhead measurement harness (SPEC §3.5 exit criterion 5).

Measures the A2A path (JSON-RPC over the ASGI app) against a direct in-process call to the
*same* answer service. Both share identical (stub) retrieval work, so the p50 difference
isolates A2A serialization + JSON-RPC transport + dispatch. This test asserts the harness
shape; the recorded number comes from a full N=100 run (see SPEC §14).
"""

from __future__ import annotations

import httpx
from fastapi import FastAPI
from httpx import ASGITransport

from nexus.a2a.bench import measure_transport_overhead
from nexus.a2a.config import A2AConfig
from nexus.a2a.server import mount_a2a
from nexus.auth.principal import hash_token
from nexus.llm.answer import AnswerResult

_TOKEN = "a2a-good-token"
_BASE = "http://nexus.test"
_PRINCIPAL = {"name": "ext", "token_sha256": hash_token(_TOKEN),
              "tenant": "acme", "clearance": "INTERNAL"}


def _stub(query: str, tenant: str, clearance: str) -> AnswerResult:
    return AnswerResult(
        answer=f"answer:{query}",
        evidence_snippets=[{"chunk_rid": "c1", "doc_title": "D", "section_path": "S",
                            "source_uri": "git://d.md", "text": "근거", "score": 0.9}],
        provenance=[{"doc_rid": "d", "source_uri": "git://d.md", "source_version": "v1"}],
        route_used="vector",
    )


def _app() -> FastAPI:
    app = FastAPI()
    mount_a2a(app, A2AConfig(enabled=True, base_url=_BASE, principals=[_PRINCIPAL]), answer_fn=_stub)
    return app


async def test_overhead_harness_reports_both_paths_and_a_p50_diff():
    app = _app()
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url=_BASE,
        headers={"Authorization": f"Bearer {_TOKEN}"},
    ) as hc:
        report = await measure_transport_overhead(
            hc, f"{_BASE}/a2a", "결제 토픽?", _stub, "acme", "INTERNAL", n=5,
        )

    assert report["n"] == 5
    for key in ("p50_a2a_ms", "p95_a2a_ms", "p50_direct_ms", "overhead_p50_ms"):
        assert isinstance(report[key], float)
    assert report["p50_a2a_ms"] >= 0.0
    # The A2A path includes everything the direct path does plus transport, so it is slower.
    assert report["p50_a2a_ms"] >= report["p50_direct_ms"]
