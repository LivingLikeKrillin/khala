# 문서-타입 Taxonomy + Tier 정책 (S1 spine) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 문서-타입 → tier → 생애주기를 선언하는 단일 정본 레지스트리를 specledger에 만들고, `promote_external`을 레지스트리 기반으로 일반화하며(ADR/DESIGN/RFC 지원), 외부-spec gateway가 CSF `kind`를 축-A로 정규화해 메타에 실어 나르게 한다.

**Architecture:** 레지스트리(YAML 데이터 + 순수 reader 모듈)는 거버넌스 owner인 **specledger**에 산다. `promote_external`은 reader를 통해 "promote 가능 = tier==T1"을 강제하고 축-A 타입을 specledger 어휘(spec/adr)로 매핑한다. **nexus** gateway는 CSF `kind`→축-A 정규화(작은 alias 미러)를 수행해 artifact 메타에 `doc_type`을 실어 나른다(라우팅 행위는 불변 — 여전히 T3 메모; tier 라우팅은 S3). 패키지는 서로 import하지 않으므로 alias는 소량 중복하고 S3에서 read-path를 통합한다.

**Tech Stack:** Python 3.11+, dataclass, PyYAML, pytest. 기존 specledger(`promote.py`, `ledger.py`)·nexus(`a2a/external_ingest_skill.py`) 패턴 준수.

**Spec:** `docs/superpowers/specs/2026-06-25-document-type-taxonomy-governance-tiers-design.md`

---

## File Structure

| 파일 | 책임 |
|---|---|
| `specledger/src/specledger/document_types.yaml` (생성) | 정본 레지스트리 데이터 — 타입→tier·immutable·owner_required·specledger_type |
| `specledger/src/specledger/doctypes.py` (생성) | reader: 로드+검증 + `tier_of`/`lifecycle_of`/`normalize_kind`/`specledger_type_of`/`is_promotable` |
| `specledger/tests/test_doctypes.py` (생성) | reader 단위 테스트 |
| `specledger/src/specledger/promote.py` (수정) | `_KIND_TO_TYPE` 하드코딩 제거 → `doctypes` 레지스트리 기반 |
| `specledger/tests/test_promote.py` (수정) | DESIGN/RFC 추가 케이스 + 레거시 회귀 |
| `nexus/nexus/a2a/external_ingest_skill.py` (수정) | `normalize_csf_kind()` + artifact 데이터에 `doc_type`(축-A) |
| `nexus/tests/test_a2a_external_ingest.py` (수정) | 정규화 + artifact doc_type 테스트 |

---

## Chunk 1: 타입 레지스트리 + reader (specledger)

정본 레지스트리(YAML)와 순수 reader. 다운스트림(promote)이 정책을 직접 읽지 않고 reader API만 본다.

### Task 1: 레지스트리 데이터 파일

**Files:**
- Create: `specledger/src/specledger/document_types.yaml`

- [ ] **Step 1: 레지스트리 YAML 작성**

`specledger/src/specledger/document_types.yaml`:

```yaml
# 문서-타입 정본 레지스트리 (S1). 축-A 거버넌스 타입 → tier·생애주기 정책.
# tier(T1/T2/T3) ↔ lifecycle(governed/tracked/memo)는 1:1 불변식(doctypes.py가 강제).
# specledger_type: T1(거버넌스) 타입만 보유 — promote_external이 이 값으로 record() 한다.
default_tier: T3   # 미지/미분류 타입은 메모로 안전 강등

types:
  ADR:        { tier: T1, immutable: true,  owner_required: true,  specledger_type: adr }
  DESIGN:     { tier: T1, immutable: true,  owner_required: true,  specledger_type: spec }
  RFC:        { tier: T1, immutable: true,  owner_required: true,  specledger_type: spec }
  PRD:        { tier: T2, immutable: false, owner_required: true }
  RUNBOOK:    { tier: T2, immutable: false, owner_required: true }
  POSTMORTEM: { tier: T2, immutable: false, owner_required: true }
  NOTE:       { tier: T3, immutable: false, owner_required: false }

# 레거시 CSF kind → 축-A 정본 타입 정규화(alias). 상류에서 1회.
aliases:
  SPEC: DESIGN     # 레거시 CSF 토큰
  FLOW: NOTE       # 모호 → 메모로 보수적 강등(default-deny 정신)
```

- [ ] **Step 2: Commit**

```bash
git add specledger/src/specledger/document_types.yaml
git commit -m "feat(doctypes): 문서-타입 정본 레지스트리 데이터 (S1)"
```

### Task 2: reader 모듈 — 로드·검증·tier 조회

**Files:**
- Create: `specledger/src/specledger/doctypes.py`
- Test: `specledger/tests/test_doctypes.py`

- [ ] **Step 1: 실패 테스트 작성**

`specledger/tests/test_doctypes.py`:

```python
from __future__ import annotations

import pytest

from specledger import doctypes


def test_known_type_resolves_tier_and_lifecycle():
    assert doctypes.tier_of("ADR") == "T1"
    assert doctypes.lifecycle_of("ADR") == "governed"
    assert doctypes.tier_of("PRD") == "T2"
    assert doctypes.lifecycle_of("PRD") == "tracked"
    assert doctypes.tier_of("NOTE") == "T3"
    assert doctypes.lifecycle_of("NOTE") == "memo"


def test_unknown_type_falls_back_to_default_tier():
    assert doctypes.tier_of("WHATEVER") == "T3"
    assert doctypes.lifecycle_of("WHATEVER") == "memo"


def test_tier_lifecycle_invariant_holds_for_all_registry_types():
    # 1:1 불변식: 모든 등록 타입의 lifecycle 은 tier 에서 유도된 값과 일치.
    reg = doctypes.load_registry()
    for name, dt in reg.items():
        assert doctypes.lifecycle_of(name) == doctypes.LIFECYCLE_BY_TIER[dt.tier]
```

- [ ] **Step 2: 실패 확인**

Run: `cd specledger && python -m pytest tests/test_doctypes.py -q`
Expected: FAIL (`ModuleNotFoundError: specledger.doctypes` 또는 AttributeError)

- [ ] **Step 3: reader 구현**

`specledger/src/specledger/doctypes.py`:

```python
"""문서-타입 정본 레지스트리 reader (S1).

document_types.yaml 을 로드·검증하고, 다운스트림이 정책 데이터를 직접 읽지 않도록
조회 API(tier_of/lifecycle_of/normalize_kind/specledger_type_of/is_promotable)만 노출한다.
tier(T1/T2/T3) ↔ lifecycle(governed/tracked/memo) 1:1 불변식을 여기서 강제한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

# tier ↔ lifecycle 1:1 불변식(정본). 레지스트리는 tier 만 선언하고 lifecycle 은 유도된다.
LIFECYCLE_BY_TIER = {"T1": "governed", "T2": "tracked", "T3": "memo"}


class RegistryError(ValueError):
    """레지스트리 데이터가 스키마를 위반할 때."""


@dataclass(frozen=True)
class DocType:
    name: str
    tier: str
    immutable: bool
    owner_required: bool
    specledger_type: str | None = None  # T1 만 보유


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, DocType], str, dict[str, str]]:
    raw = yaml.safe_load(Path(__file__).with_name("document_types.yaml").read_text("utf-8"))
    default_tier = raw.get("default_tier", "T3")
    if default_tier not in LIFECYCLE_BY_TIER:
        raise RegistryError(f"default_tier 가 알 수 없는 tier: {default_tier!r}")
    types: dict[str, DocType] = {}
    for name, spec in (raw.get("types") or {}).items():
        tier = spec.get("tier")
        if tier not in LIFECYCLE_BY_TIER:
            raise RegistryError(f"{name}: 알 수 없는 tier {tier!r}")
        st = spec.get("specledger_type")
        # 불변식: specledger_type 은 T1 에만, T1 은 반드시 보유.
        if (tier == "T1") != bool(st):
            raise RegistryError(f"{name}: specledger_type 은 T1 에만 존재해야 한다")
        types[name] = DocType(
            name=name, tier=tier,
            immutable=bool(spec.get("immutable", False)),
            owner_required=bool(spec.get("owner_required", False)),
            specledger_type=st,
        )
    aliases = {str(k): str(v) for k, v in (raw.get("aliases") or {}).items()}
    return types, default_tier, aliases


def load_registry() -> dict[str, DocType]:
    return _load()[0]


def tier_of(type_name: str) -> str:
    """알려진 타입→tier, 미지 타입→default_tier(보수적 강등)."""
    types, default_tier, _ = _load()
    dt = types.get(type_name)
    return dt.tier if dt else default_tier


def lifecycle_of(type_name: str) -> str:
    return LIFECYCLE_BY_TIER[tier_of(type_name)]


def normalize_kind(csf_kind: str) -> str:
    """레거시 CSF kind → 축-A 정본 타입. alias 없으면 그대로(상류 1회 정규화)."""
    _, _, aliases = _load()
    return aliases.get(csf_kind, csf_kind)


def specledger_type_of(type_name: str) -> str | None:
    """축-A 타입 → specledger 어휘(spec/adr). 비-T1 이면 None."""
    return _load()[0].get(type_name, DocType(type_name, "T3", False, False)).specledger_type


def is_promotable(type_name: str) -> bool:
    """거버넌스(T1)로 승격 가능한가 = specledger_type 보유."""
    return specledger_type_of(type_name) is not None
```

- [ ] **Step 4: 통과 확인**

Run: `cd specledger && python -m pytest tests/test_doctypes.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add specledger/src/specledger/doctypes.py specledger/tests/test_doctypes.py
git commit -m "feat(doctypes): 레지스트리 reader — tier/lifecycle/normalize/promotable"
```

### Task 3: 정규화·승격가능성 reader 케이스

**Files:**
- Modify: `specledger/tests/test_doctypes.py`

- [ ] **Step 1: 실패 테스트 추가**

`specledger/tests/test_doctypes.py` 끝에 추가:

```python
def test_normalize_kind_resolves_legacy_csf_tokens():
    assert doctypes.normalize_kind("SPEC") == "DESIGN"   # 레거시→정본
    assert doctypes.normalize_kind("FLOW") == "NOTE"
    assert doctypes.normalize_kind("ADR") == "ADR"        # 이미 정본이면 그대로
    assert doctypes.normalize_kind("MYSTERY") == "MYSTERY"  # 미지는 그대로(이후 tier_of 가 T3)


def test_specledger_type_and_promotability():
    assert doctypes.specledger_type_of("ADR") == "adr"
    assert doctypes.specledger_type_of("DESIGN") == "spec"
    assert doctypes.specledger_type_of("RFC") == "spec"
    assert doctypes.specledger_type_of("PRD") is None      # T2 는 승격 불가
    assert doctypes.is_promotable("ADR") is True
    assert doctypes.is_promotable("PRD") is False
    assert doctypes.is_promotable("NOTE") is False
```

- [ ] **Step 2: 실패→통과 확인** (구현은 Task 2에서 이미 완료 — 이 테스트가 그 계약을 고정)

Run: `cd specledger && python -m pytest tests/test_doctypes.py -q`
Expected: PASS (5 tests). 만약 FAIL 이면 Task 2 구현을 수정(테스트를 바꾸지 말 것).

- [ ] **Step 3: Commit**

```bash
git add specledger/tests/test_doctypes.py
git commit -m "test(doctypes): normalize_kind + 승격가능성 계약 고정"
```

---

## Chunk 2: promote_external 레지스트리 기반 일반화 (specledger)

`_KIND_TO_TYPE` 하드코딩(SPEC/ADR)을 제거하고 레지스트리로 일반화한다. 레거시 토큰(SPEC/ADR)은 정규화로 회귀 없이 동작하고, DESIGN/RFC 가 새로 지원되며, T2(PRD 등)는 승격 거부된다.

### Task 4: promote_external 가 레지스트리를 쓰도록 전환

**Files:**
- Modify: `specledger/src/specledger/promote.py:17-18,38-39,52`
- Test: `specledger/tests/test_promote.py`

- [ ] **Step 1: 실패 테스트 추가**

`specledger/tests/test_promote.py` 끝에 추가:

```python
def test_promote_design_axis_a_type_creates_draft(tmp_path):
    # 신규 축-A 타입 DESIGN → specledger spec 어휘 → DRAFT.
    out = promote_external(_led(tmp_path), _csf(), "DESIGN")
    assert out["status"] == "DRAFT"
    assert out["provenance_carried"] is True


def test_promote_rfc_axis_a_type_creates_draft(tmp_path):
    out = promote_external(_led(tmp_path), _csf(), "RFC")
    assert out["status"] == "DRAFT"


def test_promote_legacy_spec_token_still_works(tmp_path):
    # 레거시 CSF 토큰 SPEC 은 정규화(→DESIGN)되어 회귀 없이 DRAFT.
    out = promote_external(_led(tmp_path), _csf(), "SPEC")
    assert out["status"] == "DRAFT"


def test_promote_rejects_tracked_tier_type(tmp_path):
    # PRD 는 T2(추적) — 거버넌스 원장으로 승격 불가.
    with pytest.raises(PromoteError):
        promote_external(_led(tmp_path), _csf(), "PRD")
```

- [ ] **Step 2: 실패 확인**

Run: `cd specledger && python -m pytest tests/test_promote.py -q -k "design or rfc or legacy_spec or tracked_tier"`
Expected: FAIL (DESIGN/RFC 는 `type must be SPEC or ADR` 로 거부됨)

- [ ] **Step 3: promote.py 전환**

`specledger/src/specledger/promote.py` 에서 `_KIND_TO_TYPE` 상수를 삭제하고 import 에 doctypes 추가:

```python
from . import doctypes
from .artifacts import Artifact
from .ledger import Ledger
```

(`_KIND_TO_TYPE = {"SPEC": "spec", "ADR": "adr"}` 줄 삭제. `_REQUIRED`/`_REQUIRED_PROV`/`_UNSAFE_ID_CHARS` 는 유지.)

`promote_external` 의 type 검증·매핑 블록을 교체. 기존:

```python
    if type not in _KIND_TO_TYPE:
        raise PromoteError(f"type must be SPEC or ADR, got {type!r}")
```

신규:

```python
    # type 은 축-A 타입(또는 레거시 CSF 토큰) — 상류 정규화와 동일 규칙으로 정본화한 뒤
    # 레지스트리로 승격가능성(=T1)과 specledger 어휘를 결정한다(하드코딩 제거).
    axis_a = doctypes.normalize_kind(type)
    sl_type = doctypes.specledger_type_of(axis_a)
    if sl_type is None:
        raise PromoteError(
            f"type 은 거버넌스(T1) 타입이어야 한다(ADR/DESIGN/RFC/레거시 SPEC), got {type!r}"
        )
```

그리고 `record()` 호출의 매핑을 교체. 기존:

```python
    aid = ledger.record(_KIND_TO_TYPE[type], str(csf["title"]))
```

신규:

```python
    aid = ledger.record(sl_type, str(csf["title"]))
```

- [ ] **Step 4: 신규 테스트 통과 확인**

Run: `cd specledger && python -m pytest tests/test_promote.py -q -k "design or rfc or legacy_spec or tracked_tier"`
Expected: PASS (4 tests)

- [ ] **Step 5: 전체 promote 회귀 확인**

Run: `cd specledger && python -m pytest tests/test_promote.py -q`
Expected: PASS (기존 + 신규 전부). 특히 `test_promote_rejects_unknown_type`("PRD")·`test_promote_creates_draft_spec_with_body`("SPEC")·`test_promote_adr...`("ADR") 회귀 없음.

- [ ] **Step 6: Commit**

```bash
git add specledger/src/specledger/promote.py specledger/tests/test_promote.py
git commit -m "feat(promote): 레지스트리 기반 일반화 — DESIGN/RFC 지원, T2 승격 거부, 레거시 무회귀"
```

### Task 5: specledger 전체 스위트 회귀

**Files:** (없음 — 검증 전용)

- [ ] **Step 1: specledger 전체 테스트**

Run: `cd specledger && python -m pytest -q`
Expected: PASS (server.py 의 `promote_external` MCP 래핑 포함 회귀 없음)

- [ ] **Step 2: ruff**

Run: `cd specledger && python -m ruff check src/specledger/ tests/`
Expected: All checks passed!

---

## Chunk 3: nexus CSF kind 정규화 (gateway)

외부-spec gateway 가 CSF `kind` 를 축-A 로 정규화해 artifact 데이터에 `doc_type` 으로 실어 나른다. **라우팅 행위는 불변**(여전히 T3 메모) — tier 라우팅은 S3. nexus 는 specledger 를 import 하지 않으므로 alias 를 소량 미러한다(S3에서 read-path 통합).

### Task 6: normalize_csf_kind + artifact doc_type

**Files:**
- Modify: `nexus/nexus/a2a/external_ingest_skill.py`
- Test: `nexus/tests/test_a2a_external_ingest.py`

- [ ] **Step 1: 실패 테스트 추가**

`nexus/tests/test_a2a_external_ingest.py` 의 import 블록에 `normalize_csf_kind` 추가하고(아래 Step 3에서 정의), 파일 끝에 테스트 추가:

```python
def test_normalize_csf_kind_maps_legacy_to_axis_a():
    from nexus.a2a.external_ingest_skill import normalize_csf_kind
    assert normalize_csf_kind("SPEC") == "DESIGN"
    assert normalize_csf_kind("FLOW") == "NOTE"
    assert normalize_csf_kind("ADR") == "ADR"
    assert normalize_csf_kind("PRD") == "PRD"


def test_artifact_carries_normalized_doc_type():
    csf = _csf(source_tool="manifest", source_id="p-1")
    csf["kind"] = "SPEC"  # 레거시 토큰
    outcome = ExternalIngestOutcome(
        resource_rid="doc_x", labels=[EXTERNAL_LABEL], chunks_indexed=1,
        idempotent_hit=False, source_hash=csf["provenance"]["source_hash"],
    )
    artifact_json, _state, _reason = build_external_ingest_artifact(outcome, csf, "acme")
    # artifact 의 DataPart 에 정규화된 축-A doc_type 이 실린다(라우팅은 불변, 메타만 carry).
    blob = repr(artifact_json)
    assert "DESIGN" in blob
```

- [ ] **Step 2: 실패 확인**

Run: `cd nexus && python -m pytest tests/test_a2a_external_ingest.py -q -k "normalize_csf or normalized_doc_type"`
Expected: FAIL (`normalize_csf_kind` 미정의 / artifact 에 doc_type 없음)

- [ ] **Step 3: 구현**

`nexus/nexus/a2a/external_ingest_skill.py` 의 `_UNSAFE_ID_CHARS` 근처에 alias 미러 + 함수 추가:

```python
# 레거시 CSF kind → 축-A 정본 타입(S1). specledger doctypes 레지스트리의 aliases 미러 —
# 패키지 디커플링 때문에 소량 중복하며, read-path 통합은 S3.
_KIND_ALIASES = {"SPEC": "DESIGN", "FLOW": "NOTE"}


def normalize_csf_kind(kind: str) -> str:
    """레거시 CSF kind → 축-A 정본 타입. alias 없으면 그대로."""
    return _KIND_ALIASES.get(kind, kind)
```

`build_external_ingest_artifact` 의 `data` dict 에 `doc_type` 추가(`labels` 줄 아래 등):

```python
        "doc_type": normalize_csf_kind(str(doc.get("kind", ""))),
```

- [ ] **Step 4: 통과 확인**

Run: `cd nexus && python -m pytest tests/test_a2a_external_ingest.py -q -k "normalize_csf or normalized_doc_type"`
Expected: PASS (2 tests)

- [ ] **Step 5: nexus 외부-ingest 회귀**

Run: `cd nexus && python -m pytest tests/test_a2a_external_ingest.py -q`
Expected: PASS (기존 + 신규 전부 — body 미echo·label·idempotency 회귀 없음)

- [ ] **Step 6: Commit**

```bash
git add nexus/nexus/a2a/external_ingest_skill.py nexus/tests/test_a2a_external_ingest.py
git commit -m "feat(ext-ingest): CSF kind→축-A 정규화, artifact doc_type carry (라우팅 불변)"
```

### Task 7: 교차 E2E + 린트 회귀

**Files:** (없음 — 검증 전용)

- [ ] **Step 1: 외부-spec E2E**

Run (repo root): `python -m pytest tests/test_a2a_e2e_external_spec.py -q`
Expected: PASS (2 tests — gateway 변경에도 회귀 없음, acceptance #4)

- [ ] **Step 2: nexus a2a 전체 + ruff**

Run: `cd nexus && python -m pytest tests/ -q -k a2a && python -m ruff check nexus/a2a/external_ingest_skill.py tests/test_a2a_external_ingest.py`
Expected: PASS + All checks passed!

---

## Acceptance (S1 완료 기준 — 스펙 §9 대응)

- [ ] 레지스트리가 §3·§4 모델을 선언하고 스키마 검증 통과 (Task 1·2: `load_registry` + 불변식 테스트)
- [ ] reader: 알려진 타입→올바른 tier, 미지→`default_tier=T3` (Task 2·3)
- [ ] `promote_external` 가 레지스트리로 T1 축-A 타입(ADR/DESIGN/RFC) 매핑, 레거시 SPEC/ADR 회귀 없음, T2 승격 거부 (Task 4·5)
- [ ] 외부-spec gateway 가 CSF kind 를 축-A 로 정규화, 기존 E2E 회귀 없음 (Task 6·7)
- [ ] **신규 거버넌스 기계 0 for T1/T3** — specledger record()/Nexus 메모 재사용만 (전 task: 새 lifecycle 엔진 없음)

## 범위 밖 (후속, demand-pull)

- T2(추적) 거버넌스 기계(version·재확인·deprecate) — 별도 슬라이스
- 비-코드 자동 staleness 감지 — 미해결 연구 문제, 훅만
- 축 B(Diátaxis) 실제 활용 — user-facing docs 후속
- nexus↔specledger 레지스트리 read-path 통합(현재 alias 미러) — S3 intake
- S2(가이드라인)·S3(intake 라우팅)·S4(Notion importer)
