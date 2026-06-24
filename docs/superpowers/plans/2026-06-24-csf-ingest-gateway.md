# CSF + Ingest Gateway Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 외부 spec 저작 도구가 만든 spec을 khala가 "기억"으로 흡수(Nexus 인덱싱)하고 사람이 선택적으로 거버넌스로 "승격"(specledger DRAFT)할 수 있는 인바운드 입구(서브프로젝트 A)를 연다.

**Architecture:** 기존 Nexus A2A write-skill 패턴(`ingest_governed_doc`)을 미러한 형제 스킬 `ingest_external_spec`을 추가한다(메모 경로, 새 capability `ingest_external`, 순수 추가). 외부 출처 표식은 classification 레벨이 아니라 CRM `labels`에 `external_spec`로 단다. 승격은 specledger의 새 MCP 도구 `promote_external`로, CSF를 **인라인**으로 받아(Nexus read client 불필요) `record()`로 DRAFT를 만들고 provenance를 frontmatter에 보존한다. 검증은 기존 `tests/test_a2a_e2e_specledger_to_nexus.py`를 미러한 in-memory 스토어 E2E로 한다.

**Tech Stack:** Python 3.11+, FastAPI, a2a-sdk(compat v0_3 types), pytest, asyncpg. 설계 근거: `docs/superpowers/specs/2026-06-24-csf-ingest-gateway-design.md`.

**기존 패턴 참조(반드시 읽고 미러):**
- `nexus/nexus/a2a/ingest_skill.py` — `IngestOutcome` + `extract_governed_doc` + `build_ingest_artifact` (순수 프로토콜 경계)
- `nexus/nexus/a2a/server.py:161-191` — governed 스킬 라우팅 분기(capability 게이트 + audit + 매핑)
- `nexus/nexus/a2a/server.py:281-334` — `_default_ingest_fn` (inline body → transient-file 브리지)
- `nexus/nexus/a2a/card.py:68-79` — governed 스킬 카드 광고
- `specledger/src/specledger/ledger.py:27-42` — `record()` (spec→DRAFT, adr→PROPOSED)
- `specledger/src/specledger/server.py:24-67` — MCP 도구 등록 패턴
- `tests/test_a2a_e2e_specledger_to_nexus.py` — E2E 미러 대상(in-memory `_NexusStore`, capability 거부, idempotency)

---

## File Structure

| 파일 | 책임 | Create/Modify |
|---|---|---|
| `nexus/nexus/a2a/external_ingest_skill.py` | CSF 추출·검증·결과 매핑(순수 경계) + `ExternalIngestOutcome` | **Create** |
| `nexus/nexus/a2a/server.py` | `ingest_external_spec` 라우팅 분기 + `external_ingest_fn` 주입 + `_default_external_ingest_fn` DB 브리지 | Modify |
| `nexus/nexus/a2a/card.py` | 카드에 `ingest_external_spec` 스킬 광고 | Modify |
| `nexus/tests/test_a2a_external_ingest.py` | 순수 경계 + 서버 분기 단위/통합 테스트 | **Create** |
| `specledger/src/specledger/promote.py` | CSF(인라인) → DRAFT 승격(provenance 보존) | **Create** |
| `specledger/src/specledger/server.py` | `promote_external` MCP 도구 등록 | Modify |
| `specledger/tests/test_promote.py` | 승격 단위 테스트 | **Create** |
| `tests/test_a2a_e2e_external_spec.py` | 크로스툴 E2E(예치→idempotency→거부→검증→승격) | **Create** |

---

## Chunk 1: Nexus 외부-ingest 프로토콜 경계 (순수 함수)

`ingest_skill.py`를 미러한 순수 모듈. DB·네트워크 없음, 단위 테스트만으로 완결.

### Task 1: `ExternalIngestOutcome` + 추출 + 검증

**Files:**
- Create: `nexus/nexus/a2a/external_ingest_skill.py`
- Test: `nexus/tests/test_a2a_external_ingest.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# nexus/tests/test_a2a_external_ingest.py
from __future__ import annotations

import pytest

pytest.importorskip("a2a.compat.v0_3.types")

from nexus.a2a.external_ingest_skill import (  # noqa: E402
    EXTERNAL_LABEL,
    ExternalIngestOutcome,
    build_external_ingest_artifact,
    compute_source_hash,
    extract_external_spec,
    validate_external_spec,
)


def _csf(body="# Title\n\n본문", source_tool="manifest", source_id="p-1", title="Payment PRD"):
    return {
        "id": f"ext-{source_tool}-{source_id}",
        "kind": "PRD",
        "title": title,
        "provenance": {
            "source_tool": source_tool,
            "source_id": source_id,
            "source_url": "https://manifest.app/p-1",
            "source_hash": compute_source_hash(body),
        },
        "body": body,
    }


def _params(csf):
    return {"message": {"parts": [{"kind": "data", "data": csf}]}}


def test_extract_returns_doc_when_all_required_present():
    csf = _csf()
    assert extract_external_spec(_params(csf)) == csf


def test_extract_returns_none_when_provenance_missing():
    csf = _csf()
    del csf["provenance"]["source_hash"]
    assert extract_external_spec(_params(csf)) is None


def test_validate_accepts_well_formed_csf():
    assert validate_external_spec(_csf()) is None


def test_validate_rejects_id_not_matching_provenance():
    csf = _csf()
    csf["id"] = "ext-wrong-id"
    assert "id must be" in validate_external_spec(csf)


def test_validate_rejects_source_hash_mismatch():
    csf = _csf()
    csf["body"] = "tampered body"  # hash no longer matches
    assert "source_hash" in validate_external_spec(csf)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd nexus && python -m pytest tests/test_a2a_external_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nexus.a2a.external_ingest_skill'`

- [ ] **Step 3: 최소 구현 작성**

```python
# nexus/nexus/a2a/external_ingest_skill.py
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

# 외부 출처 표식 — classification 레벨이 아니라 CRM label (classification<=clearance 필터 보호).
EXTERNAL_LABEL = "external_spec"


@dataclass
class ExternalIngestOutcome:
    """외부 CSF를 ingest 한 결과 (body 미보존)."""

    resource_rid: str
    labels: list[str]
    chunks_indexed: int
    idempotent_hit: bool
    source_hash: str
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
    - provenance.source_hash 는 sha256(body) 와 일치해야 한다.
    """
    prov = doc.get("provenance") or {}
    expected_id = f"ext-{prov.get('source_tool')}-{prov.get('source_id')}"
    if doc.get("id") != expected_id:
        return f"id must be {expected_id!r}"
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
    }
    failed = outcome.error is not None
    summary = (
        outcome.error if failed else f"ingested {doc.get('id', '')} → {outcome.resource_rid}"
    )
    artifact = Artifact(
        artifact_id=uuid.uuid4().hex,
        name="external_ingest_result",
        parts=[TextPart(text=summary), DataPart(data=data)],
    )
    artifact_json = artifact.model_dump(mode="json", by_alias=True, exclude_none=True)
    if failed:
        return artifact_json, TaskState.failed.value, summary
    return artifact_json, TaskState.completed.value, None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd nexus && python -m pytest tests/test_a2a_external_ingest.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: 커밋**

```bash
git add nexus/nexus/a2a/external_ingest_skill.py nexus/tests/test_a2a_external_ingest.py
git commit -m "feat(nexus): CSF extract/validate + ExternalIngestOutcome (외부 ingest 경계)"
```

### Task 2: `build_external_ingest_artifact` 매핑 테스트

**Files:**
- Test: `nexus/tests/test_a2a_external_ingest.py` (append)

- [ ] **Step 1: 실패하는 테스트 추가**

```python
def test_build_artifact_completed_carries_labels_and_never_echoes_body():
    csf = _csf(body="비밀 본문")
    outcome = ExternalIngestOutcome(
        resource_rid="doc_x", labels=[EXTERNAL_LABEL], chunks_indexed=3,
        idempotent_hit=False, source_hash=csf["provenance"]["source_hash"],
    )
    artifact_json, state, reason = build_external_ingest_artifact(outcome, csf, "acme")
    assert state == "completed"
    assert reason is None
    # data part 에 label/provenance 요약이 있고, body는 어디에도 없다
    blob = repr(artifact_json)
    assert EXTERNAL_LABEL in blob
    assert "비밀 본문" not in blob


def test_build_artifact_failed_on_error():
    outcome = ExternalIngestOutcome(
        resource_rid="", labels=[], chunks_indexed=0, idempotent_hit=False,
        source_hash="h", error="boom",
    )
    _aj, state, reason = build_external_ingest_artifact(outcome, _csf(), "acme")
    assert state == "failed"
    assert reason == "boom"
```

- [ ] **Step 2: 실패 확인** — Run: `cd nexus && python -m pytest tests/test_a2a_external_ingest.py -k build_artifact -v` → 이미 구현되어 PASS일 수 있음. PASS면 Step 3 생략. (Task 1에서 함수를 이미 작성했으므로 green이면 정상; red면 매핑 함수 수정.)

- [ ] **Step 3: 커밋**

```bash
git add nexus/tests/test_a2a_external_ingest.py
git commit -m "test(nexus): external ingest artifact mapping (labels carried, body never echoed)"
```

---

## Chunk 2: Nexus 서버 라우팅 + 카드 + DB 브리지

`server.py`의 governed 분기(`server.py:161-191`)와 `_default_ingest_fn`(`server.py:281-334`)을 미러한다.

### Task 3: `ingest_external_spec` 라우팅 분기 (capability 게이트 + audit)

**Files:**
- Modify: `nexus/nexus/a2a/server.py`
- Test: `nexus/tests/test_a2a_external_ingest.py` (append — TestClient 통합)

- [ ] **Step 1: 실패하는 통합 테스트 추가**

```python
from fastapi import FastAPI  # noqa: E402  (테스트 파일 상단으로 옮겨도 됨)
from fastapi.testclient import TestClient  # noqa: E402

from nexus.a2a.config import A2AConfig  # noqa: E402
from nexus.a2a.server import mount_a2a  # noqa: E402
from nexus.auth.principal import hash_token  # noqa: E402

_WRITE = "ext-writer-token"
_READ = "read-token"
_PRINCIPALS = [
    {"name": "reader", "token_sha256": hash_token(_READ),
     "tenant": "acme", "clearance": "INTERNAL"},
    {"name": "depositor", "token_sha256": hash_token(_WRITE),
     "tenant": "acme", "clearance": "INTERNAL", "capabilities": ["ingest_external"]},
]


class _ExtStore:
    """in-memory stand-in for Nexus ingest+index, wired as external_ingest_fn."""

    def __init__(self):
        self.docs: dict[tuple[str, str], dict] = {}
        self.ingests = 0
        self.hits = 0

    def ingest_fn(self, doc: dict, tenant: str) -> ExternalIngestOutcome:
        self.ingests += 1
        shash = doc["provenance"]["source_hash"]
        key = (tenant, doc["id"])
        prior = self.docs.get(key)
        hit = prior is not None and prior["source_hash"] == shash
        if hit:
            self.hits += 1
        self.docs[key] = {"source_hash": shash, "body": doc["body"]}
        return ExternalIngestOutcome(
            resource_rid=f"doc_{doc['id']}", labels=[EXTERNAL_LABEL],
            chunks_indexed=0 if hit else 2, idempotent_hit=hit, source_hash=shash,
        )


def _app(ext_fn) -> FastAPI:
    app = FastAPI()
    mount_a2a(
        app,
        A2AConfig(enabled=True, base_url="http://nexus.test", principals=_PRINCIPALS),
        answer_fn=lambda q, t, c: None,
        external_ingest_fn=ext_fn,
    )
    return app


def _send(client, token, csf):
    body = {
        "jsonrpc": "2.0", "id": "1", "method": "message/send",
        "params": {"message": {
            "metadata": {"skill_id": "ingest_external_spec"},
            "parts": [{"kind": "data", "data": csf}],
        }},
    }
    return client.post("/a2a", headers={"Authorization": f"Bearer {token}"}, json=body)


def test_deposit_with_capability_ingests_and_labels():
    store = _ExtStore()
    client = TestClient(_app(store.ingest_fn))
    r = _send(client, _WRITE, _csf())
    assert r.status_code == 200
    task = r.json()["result"]
    assert task["status"]["state"] == "completed"
    assert ("acme", "ext-manifest-p-1") in store.docs


def test_read_only_token_denied_and_never_ingests():
    store = _ExtStore()
    client = TestClient(_app(store.ingest_fn))
    r = _send(client, _READ, _csf())
    assert r.json()["error"]["code"] == -32003  # forbidden
    assert store.ingests == 0


def test_idempotent_redeposit_recognised():
    store = _ExtStore()
    client = TestClient(_app(store.ingest_fn))
    _send(client, _WRITE, _csf())
    _send(client, _WRITE, _csf())
    assert len(store.docs) == 1
    assert store.hits == 1


def test_changed_body_reindexes():
    store = _ExtStore()
    client = TestClient(_app(store.ingest_fn))
    _send(client, _WRITE, _csf(body="v1"))
    _send(client, _WRITE, _csf(body="v2"))  # same id, new source_hash
    assert store.hits == 0


def test_invalid_csf_source_hash_rejected_before_ingest():
    store = _ExtStore()
    client = TestClient(_app(store.ingest_fn))
    bad = _csf()
    bad["body"] = "tampered"  # source_hash no longer matches body
    r = _send(client, _WRITE, bad)
    assert r.json()["error"]["code"] == -32602  # invalid params
    assert store.ingests == 0
```

- [ ] **Step 2: 실패 확인**

Run: `cd nexus && python -m pytest tests/test_a2a_external_ingest.py -k "deposit or denied or idempotent or changed or invalid_csf" -v`
Expected: FAIL — `mount_a2a() got an unexpected keyword argument 'external_ingest_fn'`

- [ ] **Step 3: `server.py` 수정**

3a. Import + 타입 + 상수 추가 (`server.py` 상단, 기존 ingest_skill import 옆):

```python
from nexus.a2a.external_ingest_skill import (
    ExternalIngestOutcome,
    build_external_ingest_artifact,
    compute_source_hash,
    extract_external_spec,
    validate_external_spec,
)
```

`IngestFn` 타입 정의 아래에 추가:

```python
# ExternalIngestFn: (csf, tenant) -> ExternalIngestOutcome (sync or async).
ExternalIngestFn = Callable[[dict, str], "ExternalIngestOutcome | Awaitable[ExternalIngestOutcome]"]
```

`_INGEST_CAPABILITY` 상수 아래에 추가:

```python
_EXT_INGEST_SKILL = "ingest_external_spec"
_EXT_INGEST_CAPABILITY = "ingest_external"
```

3b. `mount_a2a` 시그니처에 파라미터 추가 + 기본 해석:

```python
def mount_a2a(
    app: FastAPI,
    cfg: A2AConfig,
    answer_fn: AnswerFn | None = None,
    ingest_fn: IngestFn | None = None,
    external_ingest_fn: ExternalIngestFn | None = None,
) -> None:
```

`resolved_ingest_fn = ...` 아래에:

```python
    resolved_external_ingest_fn = external_ingest_fn or _default_external_ingest_fn
```

3c. governed 분기(`if skill == _INGEST_SKILL:` 블록, `server.py:191`의 `return` 직후) 다음에 외부 분기 추가:

```python
        # ── 외부 spec 메모 경로 (서브프로젝트 A): ungoverned, 별도 capability. ──
        if skill == _EXT_INGEST_SKILL:
            if not principal.has(_EXT_INGEST_CAPABILITY):
                await record_audit(skill=_EXT_INGEST_SKILL, query="", principal=principal.name,
                           tenant=principal.tenant, clearance=principal.clearance,
                           denied=True, reason="forbidden_no_capability",
                           latency_ms=elapsed_ms())
                return _rpc_error(req_id, _FORBIDDEN,
                                  "forbidden: ingest_external capability required", status=403)

            doc = extract_external_spec(params)
            if doc is None:
                await record_audit(skill=_EXT_INGEST_SKILL, query="", principal=principal.name,
                           tenant=principal.tenant, clearance=principal.clearance,
                           denied=True, reason="invalid_doc", latency_ms=elapsed_ms())
                return _rpc_error(req_id, _INVALID_PARAMS, "invalid external-spec payload")

            verr = validate_external_spec(doc)
            if verr is not None:
                await record_audit(skill=_EXT_INGEST_SKILL, query=str(doc.get("id", "")),
                           principal=principal.name, tenant=principal.tenant,
                           clearance=principal.clearance, denied=True,
                           reason="invalid_csf", latency_ms=elapsed_ms())
                return _rpc_error(req_id, _INVALID_PARAMS, f"invalid CSF: {verr}")

            tenant, _clearance = effective_scope(principal)  # ingest is tenant-bound
            outcome = resolved_external_ingest_fn(doc, tenant)
            if isinstance(outcome, Awaitable):
                outcome = await outcome

            artifact_json, state, reason = build_external_ingest_artifact(outcome, doc, tenant)
            task = _wrap_task(artifact_json, state, reason)
            await record_audit(
                skill=_EXT_INGEST_SKILL, query=str(doc.get("id", "")), principal=principal.name,
                tenant=tenant, clearance=principal.clearance,
                evidence_count=outcome.chunks_indexed, task_state=state,
                denied=False, reason=reason, latency_ms=elapsed_ms(),
            )
            return {"jsonrpc": "2.0", "id": req_id, "result": task}
```

3d. `_default_ingest_fn` 아래에 외부 DB 브리지 추가 (governed 브리지 미러; approved_hash 없음, ingest 후 label UPDATE):

```python
async def _default_external_ingest_fn(doc: dict, tenant: str) -> ExternalIngestOutcome:
    """Production 외부-ingest 경로: inline CSF body를 기존 파일 기반 파이프라인으로 브리지.

    governed 경로(_default_ingest_fn)와 동일하게 transient-file로 ingest 하되, approved_hash
    provenance는 없다. 결정적 id → 안정적 canonical URI 매핑으로 idempotency 가 성립한다
    (run_ingest force=False 의 (tenant, source_uri, content_hash) dedup). ingest 후 documents
    row 에 external_spec label 을 단다(classification 레벨이 아니라 CRM label).
    """
    import tempfile
    from pathlib import Path

    from nexus import db
    from nexus.ingest.pipeline import run_ingest
    from nexus.rid import doc_rid

    body = str(doc.get("body", ""))
    source_hash = compute_source_hash(body)
    fname = f"{doc.get('id', 'ext-doc')}.md"
    rid = doc_rid(f"{tenant}:{fname}")  # collector canonical_uri 와 일치(안정적)

    with tempfile.TemporaryDirectory() as td:
        (Path(td) / fname).write_text(body, encoding="utf-8")
        result = await run_ingest(td, force=False, tenant=tenant)

    idempotent = result.total_files == 0
    if not idempotent:
        # external_spec label 부여 (중복 추가 방지). classification 컬럼은 건드리지 않음.
        await db.execute(
            "UPDATE documents SET labels = array_append(labels, $3) "
            "WHERE rid = $1 AND tenant = $2 AND NOT ($3 = ANY(labels))",
            rid, tenant, EXTERNAL_LABEL,
        )

    return ExternalIngestOutcome(
        resource_rid=rid,
        labels=[EXTERNAL_LABEL],
        chunks_indexed=0 if idempotent else result.bm25_indexed,
        idempotent_hit=idempotent,
        source_hash=source_hash,
    )
```

> 주의: `_default_external_ingest_fn`은 governed `_default_ingest_fn`과 같은 위상의 production 와이어링이라 단위 테스트에서 in-memory 스토어로 대체된다(기존 E2E 철학과 동일 — RAG 인덱싱 자체는 nexus DB 스위트가 커버). `documents.labels`가 `text[]`인지 `init.sql`에서 확인할 것(CRM `NexusResource.labels: list[str]`).

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd nexus && python -m pytest tests/test_a2a_external_ingest.py -v`
Expected: PASS (전체)

- [ ] **Step 5: 커밋**

```bash
git add nexus/nexus/a2a/server.py nexus/tests/test_a2a_external_ingest.py
git commit -m "feat(nexus): ingest_external_spec A2A skill (capability-gated 메모 경로 + DB 브리지)"
```

### Task 4: 카드에 `ingest_external_spec` 광고

**Files:**
- Modify: `nexus/nexus/a2a/card.py`
- Test: `nexus/tests/test_a2a_external_ingest.py` (append)

- [ ] **Step 1: 실패하는 테스트 추가**

```python
from nexus.a2a.card import build_agent_card  # noqa: E402


def test_card_advertises_external_ingest_skill():
    card = build_agent_card(
        A2AConfig(enabled=True, base_url="http://nexus.test", principals=[])
    )
    ids = {s["id"] for s in card["skills"]}
    assert "ingest_external_spec" in ids
    assert "ingest_governed_doc" in ids  # 기존 것 회귀 없음
```

- [ ] **Step 2: 실패 확인** — Run: `cd nexus && python -m pytest tests/test_a2a_external_ingest.py -k card -v` → FAIL (skill 없음)

- [ ] **Step 3: `card.py` 수정**

`_INGEST_SKILL_ID` 아래에 추가:

```python
_EXT_INGEST_SKILL_ID = "ingest_external_spec"
```

`ingest_skill = AgentSkill(...)` 정의 다음에 추가:

```python
    # 외부 spec 메모 경로 (서브프로젝트 A): ungoverned 인덱싱. 'ingest_external' capability 필요.
    external_ingest_skill = AgentSkill(
        id=_EXT_INGEST_SKILL_ID,
        name="Ingest an external spec (memory)",
        description=(
            "Index an external tool's spec/PRD (CSF) into Nexus as ungoverned memory with "
            "source provenance. Requires the 'ingest_external' capability; promotion to a "
            "governed SPEC/ADR is a separate human action."
        ),
        tags=["write", "external", "ingest", "provenance", "memory"],
        examples=["{ id: ext-<tool>-<id>, kind, title, provenance{...}, body }"],
        input_modes=["application/json"],
        output_modes=["application/json"],
    )
```

`skills=[skill, ingest_skill]` → `skills=[skill, ingest_skill, external_ingest_skill]`

- [ ] **Step 4: 통과 확인** — Run: `cd nexus && python -m pytest tests/test_a2a_external_ingest.py -k card -v` → PASS

- [ ] **Step 5: 커밋**

```bash
git add nexus/nexus/a2a/card.py nexus/tests/test_a2a_external_ingest.py
git commit -m "feat(nexus): advertise ingest_external_spec on agent card"
```

---

## Chunk 3: specledger `promote_external`

CSF를 인라인으로 받아 DRAFT를 만들고 provenance를 보존한다. Nexus read client 불필요.

### Task 5: `promote_external` 승격 함수

**Files:**
- Create: `specledger/src/specledger/promote.py`
- Test: `specledger/tests/test_promote.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# specledger/tests/test_promote.py
from __future__ import annotations

import hashlib

import pytest

from specledger.artifacts import Artifact
from specledger.ledger import Ledger
from specledger.promote import PromoteError, promote_external


def _csf(body="# Payment\n\n결제 서비스 명세", tool="manifest", sid="p-1", title="Payment PRD"):
    return {
        "id": f"ext-{tool}-{sid}",
        "kind": "PRD",
        "title": title,
        "provenance": {
            "source_tool": tool,
            "source_id": sid,
            "source_url": "https://manifest.app/p-1",
            "source_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        },
        "body": body,
    }


def _led(tmp_path):
    return Ledger(tmp_path, now=lambda: "2026-06-24T00:00:00Z")


def test_promote_creates_draft_spec_with_body(tmp_path):
    led = _led(tmp_path)
    csf = _csf()
    out = promote_external(led, csf, "SPEC")

    assert out["status"] == "DRAFT"
    assert out["provenance_carried"] is True
    art = Artifact.load(led._resolve(out["artifact_id"]))
    assert "결제 서비스 명세" in art.body


def test_promote_preserves_provenance_in_frontmatter(tmp_path):
    led = _led(tmp_path)
    csf = _csf()
    out = promote_external(led, csf, "SPEC")
    art = Artifact.load(led._resolve(out["artifact_id"]))

    assert art.meta["source_tool"] == "manifest"
    assert art.meta["source_url"] == "https://manifest.app/p-1"
    assert art.meta["source_hash"] == csf["provenance"]["source_hash"]
    # drift breadcrumb: 승격 시점의 source_hash 를 기록 (§6)
    assert art.meta["promoted_from_source_hash"] == csf["provenance"]["source_hash"]


def test_promote_rejects_unknown_type(tmp_path):
    with pytest.raises(PromoteError):
        promote_external(_led(tmp_path), _csf(), "PRD")  # PRD 는 specledger 어휘가 아님


def test_promote_rejects_csf_missing_provenance(tmp_path):
    csf = _csf()
    del csf["provenance"]["source_hash"]
    with pytest.raises(PromoteError):
        promote_external(_led(tmp_path), csf, "SPEC")
```

- [ ] **Step 2: 실패 확인**

Run: `cd specledger && python -m pytest tests/test_promote.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'specledger.promote'`

- [ ] **Step 3: 최소 구현 작성**

```python
# specledger/src/specledger/promote.py
"""promote_external — 외부 CSF 문서를 specledger 거버넌스 DRAFT 로 끌어올린다 (서브프로젝트 A).

인바운드 기본값은 "메모"다 — 외부 spec 은 Nexus 에 ungoverned 로 산다. 승격은 명시적, 인간이
트리거하는 단계로, CSF 문서를 **인라인**으로 받아(specledger 는 Nexus read client 가 없다)
DRAFT SPEC/ADR 로 record 하고, provenance 를 frontmatter 에 보존한다(거버넌스 사본이 출처를
기억하고, promoted_from_source_hash 로 이후 소스 drift 를 감지할 수 있게). 이후 기존
critique→approve 흐름이 그대로 적용된다.
"""

from __future__ import annotations

from .artifacts import Artifact
from .ledger import Ledger

# CSF kind 의 열린 enum → specledger 어휘로 강제 매핑.
_KIND_TO_TYPE = {"SPEC": "spec", "ADR": "adr"}
_REQUIRED = ("id", "kind", "title", "body")
_REQUIRED_PROV = ("source_tool", "source_id", "source_hash")


class PromoteError(ValueError):
    """CSF 가 승격 불가(필드 누락 / 매핑 불가 type)일 때."""


def promote_external(ledger: Ledger, csf: dict, type: str) -> dict:
    """CSF(인라인) → specledger DRAFT. provenance 를 frontmatter 에 보존.

    Args:
        ledger: 대상 Ledger.
        csf: canonical spec format 문서(frontmatter dict + body).
        type: "SPEC" | "ADR" — CSF 의 열린 kind 를 specledger 어휘로 매핑.

    Returns:
        {artifact_id, status, provenance_carried}
    """
    if type not in _KIND_TO_TYPE:
        raise PromoteError(f"type must be SPEC or ADR, got {type!r}")
    if not all(csf.get(k) for k in _REQUIRED):
        raise PromoteError("CSF missing required fields")
    prov = csf.get("provenance") or {}
    if not all(prov.get(k) for k in _REQUIRED_PROV):
        raise PromoteError("CSF missing required provenance")

    aid = ledger.record(_KIND_TO_TYPE[type], str(csf["title"]))
    art = Artifact.load(ledger._resolve(aid))
    art.body = str(csf["body"])
    art.meta["source_tool"] = prov["source_tool"]
    art.meta["source_url"] = prov.get("source_url", "")
    art.meta["source_hash"] = prov["source_hash"]
    # drift breadcrumb (§6): 승격된 정본이 어느 source_hash 에서 왔는지 기억.
    art.meta["promoted_from_source_hash"] = prov["source_hash"]
    art.save()
    # Status StrEnum 은 소문자("draft"/"proposed") — 공개 계약은 대문자로 정규화(spec §5).
    return {"artifact_id": aid, "status": art.meta["status"].upper(), "provenance_carried": True}
```

- [ ] **Step 4: 통과 확인**

Run: `cd specledger && python -m pytest tests/test_promote.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add specledger/src/specledger/promote.py specledger/tests/test_promote.py
git commit -m "feat(specledger): promote_external — CSF(inline) → DRAFT, provenance 보존"
```

### Task 6: `promote_external` MCP 도구 등록

**Files:**
- Modify: `specledger/src/specledger/server.py`

- [ ] **Step 1: import 추가** (`from .publish import publish` 아래):

```python
from .promote import promote_external as _promote_external
```

- [ ] **Step 2: 도구 등록** (`publish_doc` 도구 정의 다음, `return app` 위):

```python
    @app.tool()
    def promote_external(csf: dict, type: str) -> dict:
        return _promote_external(ledger, csf, type)
```

- [ ] **Step 3: import 동작 확인** (등록 자체는 MCP 런타임이라 단위 테스트 대신 import smoke):

Run: `cd specledger && python -c "from specledger.server import build_app; print('ok')"`
Expected: `ok`

- [ ] **Step 4: 커밋**

```bash
git add specledger/src/specledger/server.py
git commit -m "feat(specledger): register promote_external MCP tool"
```

---

## Chunk 4: 크로스툴 E2E

`tests/test_a2a_e2e_specledger_to_nexus.py`를 미러. 외부 예치(in-memory 스토어) → idempotency → capability 거부 → 승격까지 한 바퀴.

### Task 7: 외부 spec E2E (예치 + 승격)

**Files:**
- Create: `tests/test_a2a_e2e_external_spec.py`

- [ ] **Step 1: 실패하는 E2E 작성**

```python
# tests/test_a2a_e2e_external_spec.py
"""Ecosystem E2E — 외부 spec 인바운드(서브프로젝트 A): 메모 예치 + 선택 승격.

실제 Nexus A2A 서버(mount_a2a → 카드 + JSON-RPC + capability 게이트 + audit + 외부 ingest
매핑)를 in-memory 외부 스토어에 와이어. 승격은 specledger promote_external 로 직접. 기존
test_a2a_e2e_specledger_to_nexus.py 와 같은 형태(유일한 스텁은 DB 인덱싱).
"""

from __future__ import annotations

import hashlib

import pytest

pytest.importorskip("nexus")
pytest.importorskip("specledger")
pytest.importorskip("a2a.compat.v0_3.types")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from structlog.testing import capture_logs  # noqa: E402

from nexus.a2a.config import A2AConfig  # noqa: E402
from nexus.a2a.external_ingest_skill import EXTERNAL_LABEL, ExternalIngestOutcome  # noqa: E402
from nexus.a2a.server import mount_a2a  # noqa: E402
from nexus.auth.principal import hash_token  # noqa: E402
from specledger.artifacts import Artifact  # noqa: E402
from specledger.ledger import Ledger  # noqa: E402
from specledger.promote import promote_external  # noqa: E402

_BASE = "http://nexus.test"
_WRITE = "ext-writer-token"
_READ = "read-only-token"
_PRINCIPALS = [
    {"name": "reader", "token_sha256": hash_token(_READ),
     "tenant": "acme", "clearance": "INTERNAL"},
    {"name": "depositor", "token_sha256": hash_token(_WRITE),
     "tenant": "acme", "clearance": "INTERNAL", "capabilities": ["ingest_external"]},
]


def _csf(body="# Payment\n\n결제 서비스 명세", tool="manifest", sid="p-1"):
    return {
        "id": f"ext-{tool}-{sid}", "kind": "PRD", "title": "Payment PRD",
        "provenance": {
            "source_tool": tool, "source_id": sid,
            "source_url": "https://manifest.app/p-1",
            "source_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        },
        "body": body,
    }


class _ExtStore:
    def __init__(self):
        self.docs: dict[tuple[str, str], dict] = {}
        self.ingests = 0
        self.hits = 0

    def ingest_fn(self, doc: dict, tenant: str) -> ExternalIngestOutcome:
        self.ingests += 1
        shash = doc["provenance"]["source_hash"]
        key = (tenant, doc["id"])
        prior = self.docs.get(key)
        hit = prior is not None and prior["source_hash"] == shash
        if hit:
            self.hits += 1
        self.docs[key] = {"source_hash": shash}
        return ExternalIngestOutcome(
            resource_rid=f"doc_{doc['id']}", labels=[EXTERNAL_LABEL],
            chunks_indexed=0 if hit else 2, idempotent_hit=hit, source_hash=shash,
        )


def _app(ext_fn) -> FastAPI:
    app = FastAPI()
    mount_a2a(
        app, A2AConfig(enabled=True, base_url=_BASE, principals=_PRINCIPALS),
        answer_fn=lambda q, t, c: None, external_ingest_fn=ext_fn,
    )
    return app


def _send(client, token, csf):
    return client.post(
        "/a2a", headers={"Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": "1", "method": "message/send",
              "params": {"message": {
                  "metadata": {"skill_id": "ingest_external_spec"},
                  "parts": [{"kind": "data", "data": csf}]}}},
    )


def test_deposit_then_idempotent_then_promote(tmp_path):
    store = _ExtStore()
    client = TestClient(_app(store.ingest_fn))

    # 1) 메모 예치 — label external_spec 로 인덱싱
    r = _send(client, _WRITE, _csf())
    task = r.json()["result"]
    assert task["status"]["state"] == "completed"
    assert ("acme", "ext-manifest-p-1") in store.docs

    # 2) 동일 재예치 — idempotent
    _send(client, _WRITE, _csf())
    assert store.hits == 1 and len(store.docs) == 1

    # 3) 선택 승격 — 호출자가 들고 있던 CSF 를 specledger DRAFT 로
    led = Ledger(tmp_path, now=lambda: "2026-06-24T00:00:00Z")
    out = promote_external(led, _csf(), "SPEC")
    art = Artifact.load(led._resolve(out["artifact_id"]))
    assert out["status"] == "DRAFT"
    assert art.meta["source_tool"] == "manifest"
    assert art.meta["promoted_from_source_hash"] == _csf()["provenance"]["source_hash"]


def test_read_only_token_denied_and_audited(tmp_path):
    store = _ExtStore()
    client = TestClient(_app(store.ingest_fn))
    with capture_logs() as logs:
        r = _send(client, _READ, _csf())
    assert r.json()["error"]["code"] == -32003  # forbidden
    assert store.ingests == 0
    audit = [x for x in logs if x.get("event") == "a2a.audit"]
    assert any(a["denied"] and a["skill"] == "ingest_external_spec" for a in audit)
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_a2a_e2e_external_spec.py -v`
Expected: 처음엔 import/동작 실패 가능 — Chunk 1~3 완료 후에는 통과해야 한다. 만약 red면 메시지 보고 해당 Chunk 수정.

- [ ] **Step 3: 통과 확인**

Run: `python -m pytest tests/test_a2a_e2e_external_spec.py -v`
Expected: PASS (2 tests)

- [ ] **Step 4: 전체 회귀 확인**

Run: `cd nexus && python -m pytest tests/ -q` 그리고 `cd specledger && python -m pytest tests/ -q` 그리고 `python -m pytest tests/test_a2a_e2e_specledger_to_nexus.py -q`
Expected: 모두 PASS (기존 governed 경로 회귀 없음)

- [ ] **Step 5: 커밋**

```bash
git add tests/test_a2a_e2e_external_spec.py
git commit -m "test(e2e): 외부 spec 인바운드 — 메모 예치 + idempotency + capability 거부 + 승격"
```

---

## 완료 기준 (Definition of Done)

- [ ] `ingest_external_spec` A2A 스킬이 capability `ingest_external`로 게이트되고, CSF를 검증·인덱싱하며, `external_spec` label을 단다(classification 불변).
- [ ] idempotency가 `(id, source_hash)`로 성립한다(동일 재예치 no-op, 변경 시 재인덱싱).
- [ ] `promote_external` MCP 도구가 CSF(인라인)를 specledger DRAFT로 승격하고 provenance + `promoted_from_source_hash`를 보존한다.
- [ ] 카드가 새 스킬을 광고한다.
- [ ] 크로스툴 E2E + 단위 테스트 전부 통과, 기존 governed 경로 회귀 없음.

## 명시적 비범위 (이 계획에 없음)
- Normalizer(임의 포맷 → CSF) — 서브프로젝트 B.
- 마크다운 import CLI/watcher, 완전한 MCP deposit 전송 surface — 서브프로젝트 C.
- Drift 감지·알림 — 후속 슬라이스(이 계획은 `promoted_from_source_hash` 빵부스러기만 남김).
- id-resolution 승격(메모리에서 id만으로) — Nexus read 스킬 필요, 후속.
