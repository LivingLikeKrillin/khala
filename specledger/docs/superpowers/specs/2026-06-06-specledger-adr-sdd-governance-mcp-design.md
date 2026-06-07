# Specledger — ADR/SDD 기록·거버넌스 MCP (설계 문서)

> 날짜: 2026-06-06 · 상태: Design (검토 대기) · 로드맵: #4 ADR/SDD MCP (NOW)
> 작업명: **specledger** (spec/ADR을 기록·추적하는 대장)

## 1. 문제와 목표

### 배경 문제 (업계 담론으로 검증됨, 2024–2026)
- **리뷰 부재 / rubber-stamping**: AI 코딩 에이전트·SDD 도구(superpowers, GitHub Spec Kit, Kiro 등)가 설계 문서·스펙을 자동 생성하지만, 사람이 제대로 읽지 않고 승인(approve)한다. 원인은 순수 물량(Intercom: PR 93%+ 에이전트 생성, 19%+ 사람 리뷰어 없이 자동 승인). 스펙 문서는 반복적·장황해 특히 외면당한다(Böckeler: "차라리 코드를 리뷰하겠다").
- **무질서한 축적 / 추적성 부재**: 생성된 설계 문서가 일관 형식 없이 쌓여 추적·검색이 안 된다(documentation/agent sprawl).
- **미충족 갭**: peer-reviewed 연구(MSR'26)가 "에이전트 작성 문서는 기존 리뷰 관행으로 완화되지 않는 신뢰성 리스크를 도입한다"며 **책임 있는 리뷰(accountable review) 도구**를 명시적으로 촉구. 기존 도구(Log4brains, Backstage TechDocs, Atlassian MCP)는 각각 일관기록·발견성·위키쓰기만 덮고, **"에이전트 생성 문서의 리뷰 강제"는 비어 있다.**

### 목표
AI가 생성한 설계 결정·스펙을 **(1) 일관된 ADR/SDD 형식으로 기록**하고, **(2) 위키에서 추적 가능**하게 만들며, **(3) 에이전트 생성 문서에 대한 책임 있는 리뷰를 강제**한다. 세 가지 교집합이 시장의 빈칸이며 이 도구의 존재 이유다. **(3) 리뷰 게이트가 핵심 차별점.**

### 비목표 (범위 밖)
- 팀/다중 사용자 인증, 실제 승인자 신원 검증 (솔로 우선 — 필드 구조만 마련)
- Confluence/Backstage 등 외부 위키 동기화 (→ 옵셔널 Khala publish로 대체)
- 코드-스펙 drift 자동 감지(`stale` 자동 전이)
- 이해도 확인 질문의 기본 탑재 (옵션 플래그로만 설계, MVP 미구현)
- spec-as-source 코드 생성 (기존 손작성 코드베이스에 부적합)

## 2. 핵심 설계 결정 (브레인스토밍 확정)

| # | 결정 | 선택 |
|---|---|---|
| D1 | 개입 지점 | 생성 직후 등재(B) + 승인 전 게이트(A) + 구현 시작 게이트(C) 통합 |
| D2 | MVP 범위 | **솔로 우선** — 승인자 필드는 구조만, 인증/공유 미구현 |
| D3 | 라이프사이클 | **이원화: ADR=불변(supersede) / Spec=anchored(living)** |
| D4 | 리뷰 게이트 정의 | **AI 크리틱 선행 + 이슈 처리 + 사인오프 기록 (D)** |
| D5 | 진실원천 | **각 문서의 frontmatter** (git-native, diff 추적) |
| D6 | 강제 메커니즘 | **MCP 서버 + Claude Code PreToolUse 훅** (협조 아닌 강제) |
| D7 | 위키/추적 | **Khala = 옵셔널 발행 대상(sink)**, 진실원천 아님 |

## 3. 아키텍처 개요

세 부품 + 진실원천(파일):

```
  진실원천: docs/.../specs/*.md, docs/adr/*.md  (frontmatter에 상태)
        ▲ 읽기/쓰기            ▲ 스캔               ▲ 조회
   ┌──────────┐         ┌──────────┐        ┌──────────────┐
   │ MCP 서버 │         │ 인덱서   │        │ 강제 훅       │
   │  (뇌)    │         │(대시보드)│        │ (PreToolUse) │
   │ 상태전이의│         └──────────┘        │ 코드편집 차단 │
   │ 유일 통로 │                             └──────────────┘
   └────┬─────┘
        │ publish (옵셔널)
        ▼
   ┌──────────┐
   │  Khala   │  승인 문서를 ingest → 검색·근거 회수 (goal #2)
   └──────────┘
```

- **MCP 서버 (뇌)**: 상태를 바꾸는 유일한 문. 결정론적(파일·상태·스캔) + critique만 독립 LLM 호출.
- **진실원천 (frontmatter)**: 문서 자체가 상태를 들고 있음(D5).
- **강제 훅 (손발)**: 구현 경계를 가로채 상태를 강제(D6) — rubber-stamp 차단의 teeth.
- **인덱서**: frontmatter를 긁어 솔로용 추적 대시보드 생성.
- **Khala (옵셔널 sink)**: specledger는 파일만으로 100% 동작, Khala 있으면 검색·추적 풍부(에코시스템 원칙 — "Probe는 Khala 없이도 100% 동작").

## 4. 아티팩트 모델 (D3)

### ADR — 불변 결정 기록
```yaml
---
id: ADR-0007
title: 리뷰 상태는 frontmatter를 진실원천으로 한다
status: proposed | accepted | superseded | deprecated
date: 2026-06-06
approved_by: eisen            # provenance (지금은 구조만)
reviewed_at: 2026-06-06T14:00Z
review_ref: .reviews/ADR-0007.md
content_hash: sha256:...      # 승인 시점 본문 해시
supersedes: ADR-0003          # optional
superseded_by:                # optional, 나중에 채워짐
---
## Context / Decision / Consequences   (Nygard 5섹션)
```
- `accepted` 후 **본문 불변**. 결정 변경 → **새 ADR이 옛것을 supersede**(옛것 `status: superseded`, 보관).

### Spec — living/anchored 설계 문서
```yaml
---
id: SPEC-virtual-dj-playlist
title: ...
status: draft | in_review | approved | stale
version: 3                    # 진화하며 증가
approved_by: eisen
reviewed_at: ...
review_ref: .reviews/SPEC-...-v3.md
content_hash: sha256:...
linked_adrs: [ADR-0007]
---
```
- **안티-rubber-stamp 규칙**: 승인된 spec 본문을 실질 수정 → content_hash 불일치 → 다음 도구/훅 실행 시 status가 `in_review`로 리셋(§9 report-and-repair) → 재검토 강제.
- `stale`: 코드 drift 시 표시 — **자동 감지는 범위 밖**(수동/미래).

### 리뷰 증거 사이드카 (`.reviews/<id>.md`)
critique가 생성한 이슈와 각 disposition, 승인자·시각을 담는다. frontmatter엔 포인터만 두어 비대화·diff 오염 방지. 사이드카는 YAML frontmatter + 본문으로 구성:
```yaml
---
target: SPEC-virtual-dj-playlist
critiqued_hash: sha256:...      # critique 시점의 본문 해시 (편집 증명용)
critiqued_at: 2026-06-06T13:00Z
issues:
  - issue_id: I-001               # disposition 매칭 키 (dispositions[].issue_id ↔ 이것)
    category: missing-invariant   # 루브릭 키
    severity: high | medium | low
    description: "..."
    status: open | accepted | rejected | deferred
    disposition_reason: null      # rejected/deferred 시 필수. approve가 dispositions[].reason를 여기 기록
approved_by:                      # approve 시 채워짐
approved_at:
---
(사람이 읽을 비평 서술)
```

### content_hash 정의
- **본문(body)만** 대상 — frontmatter는 **제외**한다. (frontmatter는 status/reviewed_at/content_hash/version이 도구에 의해 변하므로, 포함하면 스탬프 순간 자기무효화됨.)
- 정규화: **LF 줄바꿈으로 변환**(Windows 환경), 각 줄 끝 공백 제거, 앞뒤 빈 줄 제거 후 `sha256`. 결정론적 무효화 보장.

## 5. MCP 도구 (API 표면)

언어: **Python** (Khala·re-mcp 선례, frontmatter/markdown, Anthropic SDK 연동).

| 도구 | 시그니처 | 동작 | 비고 |
|---|---|---|---|
| `record` | `(type, title, slug?) -> id` | ADR/spec 파일 생성. **type=adr → status=proposed, type=spec → status=draft**. id 생성은 아래 규칙 | id 재사용 금지 |
| `critique` | `(id) -> issues[]` | **독립 Claude 호출**로 루브릭 비평 → 사이드카에 open 이슈 + `critiqued_hash` 기록, doc status=in_review | 입력/출력 계약은 아래 |
| `approve` | `(id, dispositions[], approver) -> status` | disposition 검증 통과 시 status=approved/accepted, reviewed_at·approver·content_hash 스탬프 | 검증 규칙은 §6 |
| `status` | `(id?) -> state(s)` | 결정론적 스캔 + content_hash 검증. **불일치 감지 시 frontmatter status를 in_review로 write-back**(report-and-repair) | §9 참조 |
| `supersede` | `(old_id, new_id)` | ADR 전이 (옛것 superseded, 새것 supersedes) | ADR 전용 |
| `check_gate` | `(paths[]) -> {allowed, spec_id, status, open_issue_count, reason}` | 활성 마커가 가리키는 spec이 approved인지 (해시 검증 포함). 불일치 감지 시 `status`와 동일하게 in_review로 **write-back**. 반환 필드로 §7 훅 메시지 구성 | 훅 전용, 아래 마커 계약 |
| `begin_implementation` | `(spec_id)` | 활성 spec 마커 설정 | 아래 마커 계약 |
| `end_implementation` | `()` | 활성 마커 해제 | |
| `index` | `() -> path` | frontmatter 스캔 → 대시보드 생성 | |
| `publish` | `(id)` | 승인 문서를 Khala ingest | **MVP에선 항상 수동 호출** (approve가 자동 호출하지 않음), Khala 미설정 시 no-op |

### `id` 생성 규칙
- **ADR**: `ADR-NNNN` (4자리 zero-pad, 단조 증가, 재사용 금지 — Nygard). 다음 번호 = 기존 ADR 최대치 + 1.
- **Spec**: `SPEC-<slug>`. `slug` 인자가 주어지면 그대로 사용, 없으면 `title`에서 파생:
  - 소문자화 → 공백을 `-`로 → `[a-z0-9가-힣-]` 외 문자 제거 → 연속 `-` 축약 → 앞뒤 `-` 트림 → **suffix 여유를 위해 56자로 cap**(전체 id가 60자 넘지 않게). (한글 title 허용; 파일명·git 안전.)
  - **충돌 시**: 동일 slug 존재하면 `-2`, `-3` … suffix 부여(결정론적).

### `critique` 입력/출력 계약
- **입력**: 대상 문서의 **본문(frontmatter 제외)** + `linked_adrs`에 나열된 모든 ADR의 본문 텍스트 + 루브릭. (모순 검사를 위해 linked ADR 본문을 실제로 로드해 함께 전달.)
- **출력**: 위 사이드카 스키마의 `issues[]` (`issue_id` `I-NNN` 단조, category=루브릭 키, severity, description, status=open). 사이드카에 `critiqued_hash`(현재 본문 해시) 기록 — approve의 편집 증명에 사용.
- **루브릭(category)**: `risky-assumption` / `missing-invariant` / `unverifiable-claim` / `scope-creep` / `adr-contradiction` / `undefined`(TBD·placeholder) / `untestable-requirement`.

### `approve` dispositions 계약
- 입력 `dispositions[] = [{issue_id, disposition, reason?}]`, `disposition ∈ {accepted, rejected, deferred}`. issue는 `issue_id`로 매칭.
- `accepted` = "유효한 지적이며 **문서를 고쳐 반영했다**". `rejected`/`deferred` = `reason` 필수.

### 활성 spec 마커 계약 (훅의 teeth)
- **저장**: 프로젝트 루트 `.specledger/active.json`, 스키마 `{ "spec_id": "...", "set_at": "...", "set_by": "agent|user" }`.
- **수명**: `begin_implementation(spec_id)`가 기록(기존 값 덮어씀 — **항상 단일 활성 spec**). `end_implementation()` 또는 해당 spec supersede 시 삭제.
- **`check_gate(paths)` 동작 (MVP, path-agnostic)**: `.specledger/active.json`을 읽어 → 마커 없으면 **deny**("활성 spec 없음, begin_implementation 필요"). 있으면 그 spec의 status를 해시검증 포함 평가 → `approved`면 **소스 경로 편집 일괄 allow**, 아니면 deny(spec id·status·open 이슈 수 표시). ⚠️ **MVP 한계 명시**: 활성 spec이 approved이기만 하면 *어떤* 소스 파일 편집도 허용된다(파일↔spec 정밀 대응 없음). 정밀 매핑(spec frontmatter `governs: [src/**]` 글롭)은 향후 확장.

## 6. 리뷰 게이트 흐름 (D4)

1. `record`로 생성(draft/proposed). (도구 밖 수동 편집은 §9대로 다음 도구/훅 실행 때 in_review로 write-back.)
2. `critique(id)` → 독립 Claude가 루브릭으로 비평 → N개 open 이슈 + `critiqued_hash`를 사이드카에 기록, doc status=in_review.
3. 사람이 각 이슈를 disposition: **accepted**(유효 → 문서 수정해 반영) / **rejected**(사유 필수) / **deferred**(사유 필수).
4. `approve(id, dispositions, approver)` 검증 규칙:
   - 모든 open 이슈에 disposition 존재.
   - `rejected`/`deferred`는 `reason` 필수.
   - **`accepted` 이슈가 하나라도 있으면, 현재 본문 해시 ≠ `critiqued_hash` 여야 함**(= 비평 이후 실제로 문서를 고쳤다는 증명). 안 고쳤으면 거부("accepted 했으나 문서 미수정"). → 값싼 rubber-stamp 차단. *(주의: 이 해시검사는 "고쳤다"만 증명하지 "그 이슈를 올바르게 해소했다"는 증명하지 못함. 비평 이후 본문이 바뀌었으면 재-critique를 권장하나 MVP에선 강제 아님 — 솔로 MVP 한계로 수용.)*
   - 통과 시 status=approved/accepted, reviewed_at·approver·content_hash(현재 본문) 스탬프 + 사이드카 `approved_by`/`approved_at`·disposition을 **한 트랜잭션으로 원자적 기록**(frontmatter와 사이드카가 mid-write로 갈라지지 않게).
5. (옵션, 미구현) 고위험 플래그 spec엔 이해도 질문(Q4-B) 추가.

**진화 시 재검토**: 승인 후 본문 수정 → content_hash 불일치 → 다음 도구/훅 실행 시 status `in_review`로 write-back → 다시 2~4.

## 7. 강제 훅 (D6)

- **트리거**: PreToolUse, 소스 코드 파일 Write/Edit.
- **평가 순서 (명시)**: ① `exempt_paths` 매칭 → allow + 로그 → ② `docs/`·`tests/` allow-glob 매칭 → allow → ③ 그 외(소스) → `check_gate(paths)`. (exempt가 항상 최우선 — 의도된 탈출구이므로.)
- **동작**: ③에서 `check_gate(paths)` 호출 → 지배 spec이 approved 아니면 **차단**, 반환 필드(spec_id·status·open_issue_count·reason)로 메시지 구성.
- **지배 spec 매핑 (MVP)**: §5의 활성 spec 마커 계약 사용. 정밀한 path-glob 매핑(spec frontmatter `governs: [src/**]`)은 향후 확장.
- **default-deny**: 소스 디렉터리는 미승인 시 차단(Khala의 Default-Deny 철학과 동일). `docs/`·`tests/`는 기본 허용(설정의 allow-glob).
- **탈출구(exempt)**: `.specledger/config.yaml`의 `exempt_paths` 글롭에 매칭되는 경로는 게이트 면제. 면제 적용 시 `.specledger/exempt.log`에 `{ts, path, tool}` 한 줄 append(묵시적 우회 금지 — 흔적 남김).
- **한계 명시**: MCP만으로는 강제 불가 → 훅이 강제를 담당하므로 Claude Code 환경에 종속(솔로 환경상 수용).

## 8. 인덱스 / 추적 (goal #2)

- `index()`가 모든 frontmatter를 스캔 → `docs/INDEX.md` 대시보드 생성: 🔴 미검토 / 🟡 검토중 / 🟢 승인 그룹, 각 항목에 승인자·날짜·링크·linked ADR.
- **Khala publish (옵셔널)**: **MVP에선 명시적 `publish(id)` 호출로만** 승인 문서를 Khala에 ingest(approve가 자동 호출하지 않음 — §5와 일치) → 검색 가능한 조직 지식 + 근거 회수. provenance 보존. Khala 미설정 시 전체 흐름 영향 없음. (자동 발행은 향후 옵션.)
- 닫힌 루프: **기록 → 리뷰 → 발행 → (Probe/Khala로) 근거와 함께 회수.**

## 9. 에러 처리 / 엣지 케이스

| 상황 | 처리 |
|---|---|
| 도구 밖 수동 편집 | 편집 즉시 frontmatter가 마법처럼 바뀌진 않음. **다음에 어떤 specledger 도구나 훅이 그 문서를 지날 때** content_hash 불일치를 감지하고 `status`를 `in_review`로 **write-back(report-and-repair)**. 즉 무효화 감지는 lazy하되 결과는 영속화됨. `check_gate`도 불일치를 미승인으로 취급 |
| accepted ADR 본문 변경 후 approve 시도 | 거부 + supersede 안내 |
| critique LLM 호출 실패 | **fail-closed** — 비평 없으면 approve 불가 |
| 훅이 지배 spec 못 찾음 | 소스 → 차단(명확 메시지), docs/tests → 허용 |
| id 충돌/재사용 | 에러 (단조 증가, 재사용 금지 — Nygard) |
| frontmatter ↔ 사이드카 불일치 | frontmatter가 상태의 권위, 사이드카는 증거. `status`가 보고 |
| Khala 미설정/다운 | publish no-op, 핵심 흐름 무영향 |
| 미승인/없는 spec에 `begin_implementation` | 허용됨(마커만 설정). 실패는 구현 시작 시 `check_gate`에서 발생 — 의도된 동작(마커 설정 ≠ 승인) |

## 10. 테스트 전략 (TDD red-first, 하네스 #13 원칙)

- **단위**: frontmatter 파싱·쓰기 / id 단조 배정 / 상태 전이(draft→in_review→approved) / content_hash 무효화 / ADR 불변성 거부 / disposition 검증(미처리 시 거부, 사유 누락 거부).
- **통합**: 전체 게이트 흐름(record → critique[mock LLM] → approve → status) / 훅 차단(미승인)·허용(승인) / index 생성 스냅샷 / supersede 전이.
- critique LLM은 테스트에서 mock(결정론적). 선택적으로 실제 API 계약 테스트 1건.

## 11. 첫 소비자 / 검증

로드맵 첫 소비자 = **Engception 스펙 정리**. eng-ception의 흩어진 `docs/superpowers/specs/*`를 specledger로 등재·비평·승인하며 도구를 실전 검증한다(소비자 없는 과설계 방지).

## 12. 프로젝트 위치

`[claude] mcp-tools/specledger/` (신규, 자체 git repo). 스펙은 프로젝트 repo 안에서 추적: `[claude] mcp-tools/specledger/docs/superpowers/specs/`.
