from __future__ import annotations

import json
import urllib.request
from typing import Protocol

from .artifacts import Artifact


class NexusSink(Protocol):
    def ingest(self, payload: dict) -> dict: ...


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


def publish(ledger, artifact_id, config, sink: NexusSink | None = None) -> dict:
    if config.nexus is None:
        return {"published": False, "reason": "nexus not configured"}
    art = Artifact.load(ledger._resolve(artifact_id))
    if sink is None:
        sink = NexusHttpSink(config.nexus["url"])
    payload = {
        "id": art.id,
        "title": art.meta.get("title", ""),
        "status": str(art.status),
        "approved_by": art.meta.get("approved_by"),
        "body": art.body,
        "source": str(art.path),
    }
    try:
        sink.ingest(payload)
    except Exception as exc:  # noqa: BLE001 - optional sink; return a structured signal
        return {"published": False, "reason": str(exc)}
    return {"published": True, "reason": "ok"}
