"""Publish an approved governance doc to Nexus (SPEC §5.3, Phase 3).

Two transports implement the same ``NexusSink`` Protocol:

* ``NexusHttpSink`` — the bespoke point-to-point HTTP POST (default, unchanged).
* ``A2ANexusSink`` — a thin A2A JSON-RPC client (urllib, no SDK): discover Nexus's agent card,
  confirm the ``ingest_governed_doc`` write skill, ``message/send`` the governed-doc DataPart
  with a write token, and surface a denied/failed task as a raised error so ``publish()``'s
  existing ``try/except`` maps it to the graceful ``{published: False, reason}`` contract.

``publish()`` selects the transport by flag (``config.nexus["transport"] == "a2a"`` or
``SPECLEDGER_NEXUS_TRANSPORT=a2a``); default HTTP — flag off ⇒ zero change (SPEC §6.1).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Protocol

from .artifacts import Artifact

# Nexus's A2A surface (mirrors nexus/nexus/a2a/server.py + card.py).
INGEST_SKILL = "ingest_governed_doc"
_CARD_PATH = "/.well-known/agent-card.json"
_RPC_PATH = "/a2a"


class NexusSink(Protocol):
    def ingest(self, payload: dict) -> dict: ...


class A2APublishError(RuntimeError):
    """A2A publish was denied or the ingest task failed; carries the human reason."""


class NexusHttpSink:
    def __init__(self, url: str):
        self._url = url

    def ingest(self, payload: dict) -> dict:
        req = urllib.request.Request(
            self._url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:  # noqa: S310 - configured URL
            return {"status": resp.status}


class _UrllibTransport:
    """Default A2A transport: timeout-bounded urllib JSON GET/POST.

    Returns ``(status_code, parsed_json)``; JSON-RPC errors arrive as non-2xx with a JSON
    body (Nexus returns e.g. 403 + ``{"error": ...}``), so the body is read even on HTTPError.
    """

    def __init__(self, timeout: float = 10.0):
        self._timeout = timeout

    def get_json(self, url: str) -> tuple[int, dict]:
        req = urllib.request.Request(url, method="GET")
        return self._do(req)

    def post_json(self, url: str, headers: dict, body: dict) -> tuple[int, dict]:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        return self._do(req)

    def _do(self, req: urllib.request.Request) -> tuple[int, dict]:
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
                return resp.status, _safe_json(resp.read())
        except urllib.error.HTTPError as exc:  # JSON-RPC error bodies ride non-2xx
            return exc.code, _safe_json(exc.read())


def _safe_json(raw: bytes) -> dict:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _task_reason(result: dict) -> str:
    """Pull the human reason text from a failed task's status message."""
    message = (result.get("status") or {}).get("message") or {}
    texts = [p.get("text", "") for p in message.get("parts", []) if p.get("text")]
    return " ".join(texts).strip()


class A2ANexusSink:
    """Thin A2A JSON-RPC client implementing the ``NexusSink`` Protocol (SPEC §5.3).

    The agent card is discovered once and cached per instance. A non-``completed`` task,
    a JSON-RPC error (e.g. capability denial), or a discovery failure all raise
    ``A2APublishError`` — ``publish()`` turns that into ``{published: False, reason}``.
    """

    def __init__(self, base_url: str, token: str | None = None, *, transport=None):
        self._base = base_url.rstrip("/")
        self._token = token
        self._transport = transport or _UrllibTransport()
        self._card: dict | None = None

    def ingest(self, payload: dict) -> dict:
        card = self._discover_card()
        skills = {s.get("id") for s in card.get("skills", []) if isinstance(s, dict)}
        if INGEST_SKILL not in skills:
            raise A2APublishError(
                f"Nexus 카드에 {INGEST_SKILL} skill 없음 (card lacks the ingest skill)"
            )

        rpc_url = card.get("url") or f"{self._base}{_RPC_PATH}"
        status, body = self._transport.post_json(
            rpc_url, self._auth_headers(), self._build_request(payload)
        )

        if body.get("error"):
            err = body["error"]
            raise A2APublishError(
                f"거부됨 (denied): {err.get('code')} {err.get('message', '')}".strip()
            )
        result = body.get("result")
        if not isinstance(result, dict):
            raise A2APublishError(f"빈 응답 (empty A2A result, HTTP {status})")

        state = (result.get("status") or {}).get("state")
        if state != "completed":
            reason = _task_reason(result) or str(state)
            raise A2APublishError(f"ingest 실패 (task {state}): {reason}")
        return {"task_state": state}

    def _discover_card(self) -> dict:
        if self._card is not None:
            return self._card
        status, body = self._transport.get_json(f"{self._base}{_CARD_PATH}")
        if status != 200 or not body.get("skills"):
            raise A2APublishError(f"카드 발견 실패 (card discovery failed, HTTP {status})")
        self._card = body
        return body

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def _build_request(self, payload: dict) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "messageId": f"specledger-{payload.get('id', 'doc')}",
                    "kind": "message",
                    "metadata": {"skill_id": INGEST_SKILL},
                    "parts": [{"kind": "data", "data": payload}],
                }
            },
        }


def _select_sink(config) -> NexusSink:
    """Pick the transport by flag; default HTTP (SPEC §5.3/§6.1)."""
    nexus = config.nexus or {}
    transport = (
        os.environ.get("SPECLEDGER_NEXUS_TRANSPORT") or nexus.get("transport") or "http"
    ).lower()
    if transport == "a2a":
        base = nexus.get("base_url") or nexus.get("url")
        token = os.environ.get("SPECLEDGER_NEXUS_TOKEN") or nexus.get("token")
        return A2ANexusSink(base, token=token)
    return NexusHttpSink(nexus["url"])


def publish(ledger, artifact_id, config, sink: NexusSink | None = None) -> dict:
    if config.nexus is None:
        return {"published": False, "reason": "nexus not configured"}
    art = Artifact.load(ledger._resolve(artifact_id))
    if sink is None:
        sink = _select_sink(config)
    payload = {
        "id": art.id,
        "title": art.meta.get("title", ""),
        "status": str(art.status),
        "approved_by": art.meta.get("approved_by"),
        # Provenance (SPEC §5.4): the approval stamp's content_hash rides as approved_hash.
        "content_hash": art.meta.get("content_hash") or art.recompute_hash(),
        "body": art.body,
        "source": str(art.path),
    }
    try:
        sink.ingest(payload)
    except Exception as exc:  # noqa: BLE001 - optional sink; return a structured signal
        return {"published": False, "reason": str(exc)}
    return {"published": True, "reason": "ok"}
