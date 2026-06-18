"""ingest_governed_doc — the A2A write skill (Phase 3, SPEC §5.2/§5.4).

Maps a governed-doc ingest **outcome** to an A2A artifact. The skill wraps Nexus's existing
ingest pipeline; this module is the protocol boundary (extraction + result mapping) and is
pure/unit-testable. The document **body is never echoed back** — only a provenance summary.
Server classifies and quarantines (Nexus principle #3) — the caller never sets classification.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from a2a.compat.v0_3.types import Artifact, DataPart, TaskState, TextPart

# Fields a governed-doc payload MUST carry to be ingestable.
_REQUIRED = ("id", "title", "status", "content_hash", "body")

QUARANTINE_REASON = "거버넌스 문서가 격리되었습니다 — 인덱싱 불가 (quarantined; not indexed)"


@dataclass
class IngestOutcome:
    """Result of running the ingest pipeline on a governed doc (no body retained)."""

    resource_rid: str
    classification: str
    chunks_indexed: int
    quarantined: bool
    approved_hash: str
    idempotent_hit: bool
    error: str | None = None


def extract_governed_doc(params: dict) -> dict | None:
    """Pull the governed-doc payload from the JSON-RPC message's data part.

    Returns the doc dict only if a data part carries every required field; else ``None``.
    """
    message = (params or {}).get("message") or {}
    for part in message.get("parts", []):
        if part.get("kind") == "data" and isinstance(part.get("data"), dict):
            data = part["data"]
            if all(data.get(k) for k in _REQUIRED):
                return data
    return None


def build_ingest_artifact(
    outcome: IngestOutcome,
    doc: dict,
    tenant: str,
) -> tuple[dict, str, str | None]:
    """Map an ingest outcome to ``(artifact_json, task_state, reason)``.

    Quarantine or error ⇒ ``failed`` + reason; otherwise ``completed``. The data part is a
    provenance summary only — the document body is never included.
    """
    data = {
        "doc_id": doc.get("id", ""),
        "tenant": tenant,
        "resource_rid": outcome.resource_rid,
        "classification": outcome.classification,
        "chunks_indexed": outcome.chunks_indexed,
        "quarantined": outcome.quarantined,
        "approved_hash": outcome.approved_hash,
        "idempotent_hit": outcome.idempotent_hit,
    }

    failed = outcome.quarantined or outcome.error is not None
    summary = (
        QUARANTINE_REASON if outcome.quarantined
        else (outcome.error or "")
    ) if failed else f"ingested {doc.get('id', '')} → {outcome.resource_rid}"

    artifact = Artifact(
        artifact_id=uuid.uuid4().hex,
        name="ingest_result",
        parts=[TextPart(text=summary), DataPart(data=data)],
    )
    artifact_json = artifact.model_dump(mode="json", by_alias=True, exclude_none=True)

    if failed:
        return artifact_json, TaskState.failed.value, summary
    return artifact_json, TaskState.completed.value, None
