# Intake 타입 보존 + 검색 노출 (S3, thin) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 외부 intake가 정규화된 축-A `doc_type`을 `documents` 행에 저장하고, 검색 결과·LLM 근거에 `doc_type`을 노출한다.

**Architecture:** 두 영역. (1) 검색 노출 — `SearchHit`/SQL/`EvidenceSnippet`/`format_for_llm`에 `doc_type` 전파(순수, full TDD). (2) intake 저장 — `_default_external_ingest_fn`이 ingest 후 `doc_type` UPDATE(기존 `external_spec` label UPDATE 패턴 미러; quarantine 제외). nexus는 tier 레지스트리 불필요 — S1 `normalize_csf_kind`만 사용.

**Tech Stack:** Python, asyncpg, pytest. 기존 nexus 검색·intake 패턴 준수.

**Spec:** `docs/superpowers/specs/2026-06-25-intake-doctype-persist-s3-design.md`

---

## File Structure

| 파일 | 변경 |
|---|---|
| `nexus/nexus/search/hybrid.py` | `SearchHit.doc_type` 필드 + SQL `d.doc_type` + hit 생성에 전달 |
| `nexus/nexus/search/evidence_packet.py` | `EvidenceSnippet.doc_type` + `assemble_packet` 전파 + `format_for_llm` 노출 |
| `nexus/tests/test_evidence_packet_doctype.py` (생성) | assemble_packet 전파 + formatter 노출 단위 테스트 |
| `nexus/nexus/a2a/server.py` | `_default_external_ingest_fn`에 doc_type UPDATE(label UPDATE 미러) |

---

## Chunk 1: 검색 doc_type 노출 (TDD, 순수)

### Task 1: SearchHit.doc_type + SQL

**Files:**
- Modify: `nexus/nexus/search/hybrid.py:31-40` (SearchHit), `:193-195` (SQL), `:211-224` (hit 생성)

- [ ] **Step 1: SearchHit 에 doc_type 필드 추가**

`nexus/nexus/search/hybrid.py` 의 `SearchHit` 에 `classification` 줄 위/아래로:

```python
    doc_type: str = ""
```

- [ ] **Step 2: SQL 에 d.doc_type 추가**

`SELECT ...` 블록(현재 `d.title as doc_title, d.approved_hash as approved_hash`)을:

```python
        SELECT c.rid, c.doc_rid, c.section_path, c.chunk_text, c.source_uri,
               c.classification, c.source_version,
               d.title as doc_title, d.approved_hash as approved_hash,
               d.doc_type as doc_type
        FROM chunks c
        LEFT JOIN documents d ON c.doc_rid = d.rid
        WHERE c.rid IN ({placeholders})
```

- [ ] **Step 3: hit 생성에 doc_type 전달**

`hits.append(SearchHit(...))` 의 `approved_hash=...` 줄 아래에:

```python
            doc_type=r["doc_type"] or "",
```

- [ ] **Step 4: 검색 회귀 확인**

Run: `cd nexus && python -m pytest tests/test_hybrid.py -q`
Expected: PASS (신규 필드 기본값 `""` — 회귀 없음)

- [ ] **Step 5: Commit**

```bash
git add nexus/nexus/search/hybrid.py
git commit -m "feat(search): SearchHit.doc_type + SQL d.doc_type 노출 (S3)"
```

### Task 2: EvidenceSnippet 전파 + LLM 노출

**Files:**
- Modify: `nexus/nexus/search/evidence_packet.py`
- Test: `nexus/tests/test_evidence_packet_doctype.py` (생성)

- [ ] **Step 1: 실패 테스트 작성**

`nexus/tests/test_evidence_packet_doctype.py`:

```python
from __future__ import annotations

from nexus.search.evidence_packet import assemble_packet, format_for_llm
from nexus.search.hybrid import SearchHit


def _hit(doc_type="DESIGN"):
    return SearchHit(
        rid="chunk_1", doc_rid="doc_1", doc_title="결제 설계",
        section_path="개요", source_uri="git:payment.md",
        snippet="결제 서비스 명세", score=0.9, classification="INTERNAL",
        doc_type=doc_type,
    )


def test_assemble_packet_propagates_doc_type():
    packet = assemble_packet([_hit("DESIGN")])
    assert packet.snippets[0].doc_type == "DESIGN"


def test_format_for_llm_surfaces_doc_type():
    out = format_for_llm(assemble_packet([_hit("ADR")]))
    assert "ADR" in out


def test_assemble_packet_handles_missing_doc_type():
    packet = assemble_packet([_hit("")])
    assert packet.snippets[0].doc_type == ""
```

- [ ] **Step 2: 실패 확인**

Run: `cd nexus && python -m pytest tests/test_evidence_packet_doctype.py -q`
Expected: FAIL (`EvidenceSnippet` 에 `doc_type` 없음 → TypeError)

- [ ] **Step 3: EvidenceSnippet + assemble_packet + formatter 구현**

`nexus/nexus/search/evidence_packet.py` 의 `EvidenceSnippet` 에 `classification: str` 아래로:

```python
    doc_type: str = ""
```

`assemble_packet` 의 `EvidenceSnippet(...)` 생성에 `classification=hit.classification,` 아래로:

```python
            doc_type=hit.doc_type,
```

`format_for_llm` 의 snippet 헤더(`parts.append(f"분류: {s.classification}")` 아래)에:

```python
        if s.doc_type:
            parts.append(f"타입: {s.doc_type}")
```

- [ ] **Step 4: 통과 확인**

Run: `cd nexus && python -m pytest tests/test_evidence_packet_doctype.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: 검색·evidence 회귀 + ruff**

Run: `cd nexus && python -m pytest tests/test_hybrid.py tests/test_evidence_packet_doctype.py -q && python -m ruff check nexus/search/evidence_packet.py nexus/search/hybrid.py tests/test_evidence_packet_doctype.py`
Expected: PASS + All checks passed!

- [ ] **Step 6: Commit**

```bash
git add nexus/nexus/search/evidence_packet.py nexus/tests/test_evidence_packet_doctype.py
git commit -m "feat(evidence): doc_type 전파 + LLM 근거 노출 (S3)"
```

---

## Chunk 2: Intake doc_type 저장 (DB 경로)

`_default_external_ingest_fn`이 ingest 후 정규화된 `doc_type`을 행에 저장한다. **단위테스트 seam 없음** — 이 함수는 DB/`run_ingest` 의존 프로덕션 경로이며, 형제인 `external_spec` label UPDATE도 동일하게 단위테스트되지 않는다(실 Postgres 경로). doc_type 값 계산은 `normalize_csf_kind`(S1, 단위테스트 완료)를 재사용하므로, 신규 위험은 UPDATE 문 자체로 국한되고 기존 label UPDATE와 구조 동일하다. (참고: `_default_external_ingest_fn` DB 경로 전반의 단위 커버리지 부재는 기존 알려진 공백 — 별도 슬라이스.)

### Task 3: _default_external_ingest_fn 에 doc_type UPDATE

**Files:**
- Modify: `nexus/nexus/a2a/server.py` (`_default_external_ingest_fn`, label UPDATE 블록)

- [ ] **Step 1: import 추가**

`nexus/nexus/a2a/server.py` 상단 external_ingest_skill import 에 `normalize_csf_kind` 추가:

```python
from nexus.a2a.external_ingest_skill import (
    EXTERNAL_LABEL,
    ExternalIngestOutcome,
    build_external_ingest_artifact,
    compute_source_hash,
    extract_external_spec,
    normalize_csf_kind,
    validate_external_spec,
)
```

- [ ] **Step 2: doc_type UPDATE 추가**

`_default_external_ingest_fn` 의 label UPDATE 블록(현재 `if not idempotent and not quarantined:` 안의 `external_spec` label UPDATE) 바로 뒤에, 같은 가드 안에서 doc_type UPDATE 추가. doc 의 kind 를 정규화해 행에 박는다(분류기 추측값 override):

```python
        # 축-A doc_type 보존(S3): CSF 선언 타입을 정규화해 행에 저장(분류기 추측값 override).
        # quarantine 행에는 절대 쓰지 않는다(label 규칙과 동일).
        await db.execute(
            "UPDATE documents SET doc_type = $3 WHERE rid = $1 AND tenant = $2",
            rid, tenant, normalize_csf_kind(str(doc.get("kind", "") or "NOTE")),
        )
```

(주: `_default_external_ingest_fn` 시그니처는 `(doc, tenant)` 이므로 `doc.get("kind")` 접근 가능. kind 없으면 NOTE 기본.)

- [ ] **Step 3: import 회귀 + ruff**

Run: `cd nexus && python -m pytest tests/ -q -k a2a && python -m ruff check nexus/a2a/server.py`
Expected: PASS + All checks passed! (server.py import/구문 회귀 없음; _default 경로는 stub 로 우회되어 기존 a2a 테스트 그대로 통과)

- [ ] **Step 4: Commit**

```bash
git add nexus/nexus/a2a/server.py
git commit -m "feat(intake): 외부 ingest 시 축-A doc_type 행 저장 (S3, label UPDATE 미러)"
```

---

## Task 4: 전체 회귀 + 교차 E2E

**Files:** (없음 — 검증 전용)

- [ ] **Step 1: nexus 전체 + 외부-spec E2E**

Run: `cd nexus && python -m pytest -q`
Run (repo root): `python -m pytest tests/ -q`
Expected: 둘 다 PASS (신규 필드 기본값·stub 경로로 회귀 없음)

- [ ] **Step 2: ruff 전체 변경분**

Run: `cd nexus && python -m ruff check nexus/search/ nexus/a2a/ tests/test_evidence_packet_doctype.py`
Expected: All checks passed!

## Acceptance (스펙 §4 대응)

- [ ] `_default_external_ingest_fn`이 비-quarantine 행에 정규화 doc_type UPDATE (Task 3)
- [ ] `assemble_packet` 전파 + `format_for_llm` 노출 (Task 2)
- [ ] 기존 검색/외부-ingest 회귀 없음 (Task 1·4)
