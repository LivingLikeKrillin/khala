# Design Spec — CSF + Ingest Gateway (외부 spec 인바운드 거버넌스 허브, 서브프로젝트 A)

- **Date:** 2026-06-24
- **Status:** Design (brainstorming output) — pending spec review + user approval
- **Author:** LivingLikeKrillin (with Claude)
- **Source of insight:** manyfast.io(Manifest) 검토에서 출발한 전략 전환 — "또 하나의 spec 저작 도구"가 아니라 **기존 도구 사용자가 들어올 인바운드 거버넌스 허브**가 된다. 진입장벽을 낮추는 온램프 제공 = 생존 법칙.
- **Deliverable (이 서브프로젝트 A):** Nexus의 새 A2A 스킬 `ingest_external_spec`, specledger의 새 MCP 도구 `promote_external`, 그리고 둘을 잇는 교환 계약 **CSF(Canonical Spec Format)**. + E2E 검증 테스트.

---

## 1. Purpose

khala를 **외부 spec 저작 도구들(Manifest·Notion·Cursor·Claude Code 등)의 수렴점**으로 만드는 3-서브시스템 이니셔티브의 **첫 조각**이다. 이 문서는 그중 **A: 계약(CSF) + Ingest Gateway**만 다룬다.

목표는 외부 도구가 만든 spec을 khala가 **기본은 "기억"으로 흡수**(provenance 태그 + Nexus 인덱싱)하고, 사람이 "이건 정본이다" 판단할 때만 **선택적으로 거버넌스로 승격**(specledger 게이트)하는 단방향 입구를 여는 것이다.

이 설계는 khala의 통치 규율을 만족해야 한다:

- **demand-pull, not build-push** — 첫 검증 소비자는 "MCP/A2A로 spec을 예치하는 AI 에이전트"(도그푸딩 가능한 실제 입구). 제네릭 멀티-어댑터는 짓지 않는다.
- **진입장벽 낮추기 = 생존 법칙** — 외부 도구가 source-of-truth로 남고, khala는 *낮은 비용의 입구*만 제공한다. 외부 도구를 대체하지 않는다.
- **순수 추가(additive)** — 기존 governed publish 경로(approved_hash provenance)는 한 줄도 바꾸지 않는다.
- **자산 재활용** — CSF는 새 포맷이 아니라 specledger Artifact 스키마 + provenance 블록. 메모 인덱싱은 기존 Nexus A2A ingest 기계(audit·ratelimit·idempotency)를 재사용한다.

## 2. Scope (이 서브프로젝트가 짓는 것 / 안 짓는 것)

**A가 산출하는 것:**

1. **CSF** — 외부 spec의 정규화된 와이어 포맷(계약).
2. **`ingest_external_spec`** — Nexus의 새 A2A 스킬(메모 경로).
3. **`promote_external`** — specledger의 새 MCP 도구(승격 경로).
4. **E2E 검증** — A2A 클라이언트 → 인덱싱 → idempotency → 승격까지 한 바퀴.

**A가 *짓지 않는* 것 (명시적 deferral):**

| 미루는 것 | 어디로 |
|---|---|
| Normalizer (임의 소스 포맷 → CSF, 어댑터 N개) | 서브프로젝트 B (별도 도구) |
| 마크다운 import CLI/watcher, 완전한 MCP deposit 전송 surface | 서브프로젝트 C (전송) |
| Drift 알림 (소스가 승격 이후 바뀜 감지) | 후속 슬라이스 (A는 빵부스러기만 남김, §6) |
| 멀티 어댑터, SaaS 웹훅, 양방향 동기화 | 범위 밖 |

검증은 전송(MCP/마크다운)을 짓지 않고도 A2A 클라이언트 직접 호출로 완결된다 — 기존 `tests/test_a2a_e2e_specledger_to_nexus.py` 패턴 미러.

## 3. CSF — Canonical Spec Format (교환 계약)

CSF는 specledger Artifact frontmatter를 그대로 쓰고 **provenance 블록만 추가**한다. 새 포맷 발명 없음.

```yaml
---
# --- 코어 필드 (specledger Artifact 미러) ---
id: ext-<source_tool>-<source_id>      # 결정적(deterministic) 외부 ID
kind: PRD | SPEC | ADR | FLOW | NOTE   # 소스 문서 종류 (열린 enum)
title: <string>
# --- provenance 블록 (신규) ---
provenance:
  source_tool: <string>                # manifest | notion | cursor | claude-code | ...
  source_id:   <string>                # 소스 시스템 내 ID
  source_url:  <string>                # 원본 딥링크 (optional)
  source_hash: <sha256 hex>            # 정규화된 body의 해시
  ingested_at: <iso8601>               # 서버가 채움
  ingested_by: <string>                # A2A principal (서버가 채움)
linked: []                             # optional 참조 목록
---
<markdown body>
```

**필드 규칙:**

- `id` **결정적**: `ext-<source_tool>-<source_id>`. 같은 소스 문서 재예치 시 같은 ID → idempotency·dedup 키 성립.
- `kind` **열린 enum**: 메모 단계에선 인덱싱만 하므로 자유. *승격* 시점에만 khala 어휘(`SPEC`|`ADR`)로 매핑을 강제한다(§5).
- `provenance.source_hash`는 **클라이언트가 본문에 대해 계산**해 보내고, 서버가 재계산·검증한다(불일치 시 거부).
- `provenance.ingested_at` / `ingested_by`는 **서버가 채운다**(클라이언트 값 무시) — 감사 무결성.
- 외부 artifact는 **specledger 상태머신에 들어가지 않는다.** 승격 전까지는 Nexus 리소스로 `classification=external_spec` 태그를 달고 살 뿐이다. specledger lifecycle(DRAFT→PROPOSED→…)은 승격 후에야 시작된다.

**검증(서버측):** 필수 필드 누락(`id`/`kind`/`title`/`provenance.source_tool`/`source_id`/`source_hash`/body) → 거부. `id`가 `ext-<source_tool>-<source_id>`와 불일치 → 거부. `source_hash` 재계산 불일치 → 거부.

## 4. 메모 경로 — `ingest_external_spec` (Nexus A2A 스킬)

Nexus에 `ingest_governed_doc`의 **형제 스킬**을 추가한다. governed 경로는 건드리지 않는다.

**인터페이스:**

```
A2A skill: ingest_external_spec
  input:  CSF (frontmatter + body)
  output: IngestOutcome {
            resource_rid,
            classification: "external_spec",
            chunks_indexed,
            idempotent_hit: bool,
            source_hash
          }
```

**동작:**

1. **Capability 게이트:** 호출 토큰은 `ingest_external` capability를 보유해야 한다(governed publish의 `ingest_governed`와 **분리**). 외부 예치 토큰이 governed로 위장 못 함. 기존 capability-gating 재사용.
2. **검증:** §3 서버측 검증 수행.
3. **Idempotency:** 키 `(id, source_hash)`. 동일 키 재예치 = no-op으로 `idempotent_hit: true` 반환(재인덱싱 안 함). 같은 `id` + 다른 `source_hash` = 새 메모 버전(재인덱싱). 기존 Nexus idempotency `(doc_id, approved_hash)` 패턴 미러.
4. **인덱싱:** body를 청크·임베딩하여 Nexus에 `classification=external_spec` + provenance 메타로 인덱싱. 검색 시 provenance(출처 도구·딥링크)가 evidence에 노출된다.
5. **Audit:** 모든 호출을 기존 `a2a_audit` 테이블에 기록(principal, capability, result, idempotent_hit).
6. **Rate limit:** 기존 per-principal 쿼터 그대로 적용.

**경계:** 이 스킬은 specledger를 호출하지 않는다. "기본은 메모"가 불변식이다. governed 경로(approved_hash provenance)와 데이터·코드를 공유하지 않는 순수 추가 채널이다.

## 5. 승격 경로 — `promote_external` (specledger MCP 도구)

승격은 거버넌스 행위이므로 **specledger가 소유**한다. 사람이 Claude Code 안에서 명시적으로 호출한다.

**인터페이스:**

```
MCP tool: promote_external
  input:  { ref: <external id 또는 resource_rid>, kind: "SPEC" | "ADR" }
  output: { artifact_id, status: "DRAFT", provenance_carried: bool }
```

**동작:**

1. `ref`로 Nexus에서 external 리소스의 body + provenance를 가져온다.
2. `kind` 매핑을 강제한다(CSF의 열린 `kind` → specledger 어휘 `SPEC`|`ADR`). 매핑 불가 시 오류.
3. specledger `record()`로 **DRAFT** artifact를 생성한다.
4. provenance를 새 artifact frontmatter에 보존: `source_tool`, `source_url`, `source_hash`, 그리고 drift 빵부스러기 `promoted_from_source_hash`(§6).
5. 이후는 **기존 흐름 그대로** — `critique()` → 인간 disposition → `approve()` → `approved_hash` 스탬프. A는 이 흐름에 아무것도 추가하지 않는다.

**경계:** 승격 전까지 specledger는 외부 데이터를 전혀 보지 않는다. 승격은 인간이 트리거하는 단발 행위이며 자동화하지 않는다.

## 6. Identity / Idempotency / Drift

- **Identity:** 결정적 `id`(§3) + idempotency `(id, source_hash)`(§4).
- **Drift — 지금 만들지 않는다(YAGNI). 단 훅만 남긴다:** 승격 시 `promoted_from_source_hash`를 frontmatter에 기록한다. 이후 동일 `id`로 더 새로운 `source_hash`가 메모로 들어오면, 승격된 정본과 소스가 어긋났음을 감지할 수 있다. 이 감지·알림은 **후속 슬라이스**로 분리한다(khala staleness/cognitive-debt 미션과 정합하므로 demand-pull 신호가 잡히면 연다). A는 빵부스러기만 보존한다.

## 7. Auth / Audit / Rate limiting

전부 기존 A2A governance 레이어 재사용. 신규 표면은 capability 이름 하나뿐.

| 관심사 | 처리 |
|---|---|
| Capability | 신규 `ingest_external` (governed `ingest_governed`와 분리). 읽기 토큰·governed 토큰은 서버측 거부 |
| Audit | 기존 `a2a_audit` 테이블에 그대로 기록 |
| Rate limit | 기존 per-principal 쿼터 그대로 |
| Classification | 서버가 `external_spec`로 고정. PII 격리 정책은 기존 policy 레이어 그대로 적용 |

## 8. 검증 (Acceptance test)

기존 `tests/test_a2a_e2e_specledger_to_nexus.py` 패턴을 미러한 **단일 E2E**가 A의 완료 기준이다.

시나리오:

1. 테스트 A2A 클라이언트(`ingest_external` 토큰)가 CSF를 `ingest_external_spec`로 전송한다.
   → `IngestOutcome.classification == "external_spec"`, `chunks_indexed > 0`, provenance가 인덱스 메타에 존재.
2. **동일 CSF 재전송** → `idempotent_hit == true`, 재인덱싱 없음.
3. **body 변경 후 동일 `id` 전송** → `idempotent_hit == false`, 새 source_hash로 재인덱싱.
4. `read` 전용 토큰으로 전송 시도 → capability 거부.
5. `promote_external(ref, kind="SPEC")` 호출 → specledger DRAFT 생성, frontmatter에 provenance + `promoted_from_source_hash` 보존.

추가 단위 테스트: CSF 서버측 검증(필수 필드 누락·id 불일치·source_hash 불일치 거부).

## 9. 단위(units)와 경계

| Unit | 책임 | 의존 | 독립 테스트 |
|---|---|---|---|
| **CSF 검증기** | CSF 파싱 + 서버측 검증(필드·id·hash) | 없음(순수 함수) | 단위 테스트(유효/무효 CSF) |
| **`ingest_external_spec` 스킬** | 메모 인덱싱 + idempotency + audit | CSF 검증기, Nexus 인덱스, 기존 audit/ratelimit | E2E 1~4 |
| **`promote_external` 도구** | external 리소스 → specledger DRAFT(provenance 보존) | Nexus 읽기, specledger `record()` | E2E 5 |

각 unit은 내부를 읽지 않고도 "무엇을 하는가"를 인터페이스만으로 알 수 있고, 독립적으로 테스트된다.

## 10. 향후(이 문서 범위 밖, 의존 순서)

- **서브프로젝트 B — Normalizer(별도 도구):** 임의 소스 포맷 → CSF. 첫 어댑터 = markdown+frontmatter. CSF 계약(이 문서)에 의존.
- **서브프로젝트 C — 전송 2종:** MCP `deposit_spec` 도구 + 마크다운 import CLI/watcher. B(Normalizer)와 A(Gateway)에 의존.
- **Drift 슬라이스:** §6 빵부스러기 위에 감지·알림.
