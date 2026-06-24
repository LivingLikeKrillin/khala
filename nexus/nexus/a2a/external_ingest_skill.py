"""ingest_external_spec — A2A inbound skill for *ungoverned* external specs (서브프로젝트 A).

외부 도구(Manifest/Notion/Cursor/...)가 CSF(canonical spec format) 문서를 예치한다. governed
경로와 달리 approved_hash provenance가 없다 — 신뢰 앵커는 소스 콘텐츠 자체(source_hash)다. 문서는
**메모**로 인덱싱되며(label "external_spec") specledger 거버넌스 lifecycle에 들어가지 않는다.
거버넌스 SPEC/ADR로의 승격은 별도의 인간 행위(specledger.promote_external)다. 이 모듈은 순수
프로토콜 경계(추출 + 검증 + 결과 매핑)이며, DB/인덱스 작업은 ingest_fn으로 주입된다(서버 와이어링).
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from a2a.compat.v0_3.types import Artifact, DataPart, TaskState, TextPart

# CSF 최상위 필수 필드.
_REQUIRED = ("id", "kind", "title", "body")
# provenance 블록 필수 필드.
_REQUIRED_PROV = ("source_tool", "source_id", "source_hash")

# id 를 파일시스템 basename 으로 매핑할 때 식별자를 무너뜨리는 문자(경로 구분자/널). 플랫폼 독립으로
# 둘 다 막아, production rid(safe_id basename)가 id 와 1:1 로 유지되게 한다(아래 validate 참조).
_UNSAFE_ID_CHARS = ("/", "\\", "\x00")

# 외부 출처 표식 — classification 레벨이 아니라 CRM label (classification<=clearance 필터 보호).
EXTERNAL_LABEL = "external_spec"

QUARANTINE_REASON = "외부 spec 이 격리되었습니다 — 인덱싱 불가 (quarantined; not indexed)"


@dataclass
class ExternalIngestOutcome:
    """외부 CSF를 ingest 한 결과 (body 미보존)."""

    resource_rid: str
    labels: list[str]
    chunks_indexed: int
    idempotent_hit: bool
    source_hash: str
    quarantined: bool = False
    error: str | None = None


def compute_source_hash(body: str) -> str:
    """정규화된 body에 대한 결정적 콘텐츠 해시."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def extract_external_spec(params: dict) -> dict | None:
    """JSON-RPC 메시지의 data part에서 CSF 페이로드를 꺼낸다.

    모든 필수 CSF 필드(provenance 포함)를 가진 data part가 있을 때만 doc dict 반환, 아니면 None.
    hash/id 형식 검증은 하지 않는다 — 그건 validate_external_spec 책임.
    """
    message = (params or {}).get("message") or {}
    for part in message.get("parts", []):
        if part.get("kind") == "data" and isinstance(part.get("data"), dict):
            data = part["data"]
            prov = data.get("provenance")
            if (
                all(data.get(k) for k in _REQUIRED)
                and isinstance(prov, dict)
                and all(prov.get(k) for k in _REQUIRED_PROV)
            ):
                return data
    return None


def validate_external_spec(doc: dict) -> str | None:
    """서버측 CSF 검증. 오류 문자열 반환, 유효하면 None.

    - id 는 ext-<source_tool>-<source_id> 와 정확히 일치해야 한다.
    - id 는 경로 구분자/널을 포함하지 않아야 한다(rid basename 축약 시 식별자 충돌 방지).
    - provenance.source_hash 는 sha256(body) 와 일치해야 한다.
    """
    prov = doc.get("provenance") or {}
    expected_id = f"ext-{prov.get('source_tool')}-{prov.get('source_id')}"
    if doc.get("id") != expected_id:
        return f"id must be {expected_id!r}"
    if any(c in expected_id for c in _UNSAFE_ID_CHARS):
        return "source_tool/source_id must not contain path separators"
    if compute_source_hash(str(doc.get("body", ""))) != prov.get("source_hash"):
        return "source_hash does not match body"
    return None


def build_external_ingest_artifact(
    outcome: ExternalIngestOutcome,
    doc: dict,
    tenant: str,
) -> tuple[dict, str, str | None]:
    """외부-ingest 결과를 (artifact_json, task_state, reason) 으로 매핑. body는 절대 echo 안 함."""
    data = {
        "doc_id": doc.get("id", ""),
        "tenant": tenant,
        "resource_rid": outcome.resource_rid,
        "labels": outcome.labels,
        "chunks_indexed": outcome.chunks_indexed,
        "idempotent_hit": outcome.idempotent_hit,
        "source_hash": outcome.source_hash,
        "quarantined": outcome.quarantined,
    }
    failed = outcome.quarantined or outcome.error is not None
    summary = (
        QUARANTINE_REASON if outcome.quarantined
        else (outcome.error or "")
    ) if failed else f"ingested {doc.get('id', '')} → {outcome.resource_rid}"
    artifact = Artifact(
        artifact_id=uuid.uuid4().hex,
        name="external_ingest_result",
        parts=[TextPart(text=summary), DataPart(data=data)],
    )
    artifact_json = artifact.model_dump(mode="json", by_alias=True, exclude_none=True)
    if failed:
        return artifact_json, TaskState.failed.value, summary
    return artifact_json, TaskState.completed.value, None
