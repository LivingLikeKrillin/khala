from __future__ import annotations

import json
import urllib.request
from typing import Protocol

from .artifacts import Artifact


class KhalaSink(Protocol):
    def ingest(self, payload: dict) -> dict: ...


class KhalaHttpSink:
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


def publish(ledger, artifact_id, config, sink: KhalaSink | None = None) -> dict:
    if config.khala is None:
        return {"published": False, "reason": "khala not configured"}
    art = Artifact.load(ledger._resolve(artifact_id))
    if sink is None:
        sink = KhalaHttpSink(config.khala["url"])
    payload = {
        "id": art.id,
        "title": art.meta.get("title", ""),
        "status": str(art.status),
        "approved_by": art.meta.get("approved_by"),
        "body": art.body,
        "source": str(art.path),
    }
    sink.ingest(payload)
    return {"published": True, "reason": "ok"}
