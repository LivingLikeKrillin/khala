"""Transport-overhead harness (SPEC exit criterion 5).

Compares the A2A JSON-RPC path against a direct in-process call to the same answer service.
Both run identical retrieval work, so ``overhead_p50 = p50(a2a) - p50(direct)`` isolates A2A
serialization + JSON-RPC transport + ASGI dispatch + policy. Intended to run against a stub
answer service (pure transport) or, with a live stack, the real grounded-answer path.
"""

from __future__ import annotations

import inspect
import time
import uuid
from collections.abc import Awaitable, Callable

import httpx

from nexus.a2a.mapping import build_grounded_artifact
from nexus.llm.answer import AnswerResult

AnswerFn = Callable[[str, str, str], AnswerResult | Awaitable[AnswerResult]]


def _percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile of a non-empty list (pct in [0, 100])."""
    ordered = sorted(values)
    if not ordered:
        return 0.0
    rank = max(1, min(len(ordered), round(pct / 100.0 * len(ordered))))
    return float(ordered[rank - 1])


def _rpc_payload(query: str) -> dict:
    return {
        "jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "message/send",
        "params": {"message": {
            "role": "user", "messageId": uuid.uuid4().hex, "kind": "message",
            "parts": [{"kind": "text", "text": query}],
        }},
    }


async def _call_answer(answer_fn: AnswerFn, query: str, tenant: str, clearance: str) -> AnswerResult:
    result = answer_fn(query, tenant, clearance)
    if inspect.isawaitable(result):
        result = await result
    return result


async def measure_transport_overhead(
    httpx_client: httpx.AsyncClient,
    rpc_url: str,
    query: str,
    answer_fn: AnswerFn,
    tenant: str,
    clearance: str,
    n: int = 100,
) -> dict:
    """Run ``n`` A2A round-trips and ``n`` direct calls; return p50/p95 + the p50 overhead.

    The A2A path is a full JSON-RPC ``message/send`` over ``httpx_client`` (which may be an
    in-process ASGI transport). The direct path calls ``answer_fn`` and maps the result —
    the same work the server does, minus the transport.
    """
    a2a_ms: list[float] = []
    direct_ms: list[float] = []

    for _ in range(n):
        start = time.perf_counter()
        resp = await httpx_client.post(rpc_url, json=_rpc_payload(query))
        resp.raise_for_status()
        a2a_ms.append((time.perf_counter() - start) * 1000.0)

    for _ in range(n):
        start = time.perf_counter()
        result = await _call_answer(answer_fn, query, tenant, clearance)
        build_grounded_artifact(result, tenant, clearance)
        direct_ms.append((time.perf_counter() - start) * 1000.0)

    p50_a2a = _percentile(a2a_ms, 50)
    p50_direct = _percentile(direct_ms, 50)
    return {
        "n": n,
        "p50_a2a_ms": p50_a2a,
        "p95_a2a_ms": _percentile(a2a_ms, 95),
        "p50_direct_ms": p50_direct,
        "overhead_p50_ms": p50_a2a - p50_direct,
    }
