# 검색답변 신뢰 신호 배지 (Search-Answer Trust Signal) — 설계

- 날짜: 2026-06-25
- 상태: 승인 대기 (spec review)
- 범위: nexus 웹 UI (표현 계층 전용)

## 1. 문제와 동기

라이브 적재 실증 후, 검색 답변의 **근거(evidence)가 어떤 거버넌스 성격의 문서인지**를
웹 리더가 알 수 없다. `/search`·`/search/answer` 응답은 이제 `doc_type`(축-A 타입:
ADR/RFC/DESIGN/PRD/RUNBOOK/POSTMORTEM/NOTE)을 싣지만(#56), 웹은 이를 표시하지 않거나
(documents 뷰) raw 텍스트로만 보여준다(예: "NOTE").

khala 미션([[khala-debt-reframe-adr-0002]])의 한 축은 **"인간이 판단을 멈춘다"는 부채를
신뢰 보정으로 갚는 것**이다. 검색 리더가 근거를 볼 때, 그것이 *승인된 거버넌스 결정*인지
*추적 문서*인지 *비거버넌스 메모*인지 즉시 calibrate할 수 있어야 한다. 현재는 그 신호가 없다.

**소비자:** 웹 리더(사람). `localhost:8000` 채팅/검색 사용자.

## 2. 비목표 (Non-goals)

- **풀 운용 가이드 표시 안 함.** `guidance_for`(예: "ADR 불변+supersede, 5섹션…")는
  작성자·에이전트용 운용 지침으로, 검색 리더에겐 소음이다. specledger `guide(type)` MCP에
  그대로 둔다. 웹엔 terse 신뢰 신호만.
- **nexus 백엔드/API 변경 없음.** (§5 경계 참조)
- **tier 계산을 nexus에 도입하지 않음.**
- 에이전트/MCP 소비자는 본 범위 밖(이미 nexus search + specledger `guide(type)` 조합 가능).

## 3. 설계

### 3.1 데이터: `nexus/web/js/doctype-signal.js` (신규, 순수 함수)

```
trustSignal(docType: string) -> { label, tier, tone, note }
```

축-A 7타입을 3개 신뢰 등급으로 매핑. 미지/빈 타입 → 보수적 기본(메모, T3 default와 일치).

| doc_type | tier(표시) | tone | label | note (툴팁) |
|---|---|---|---|---|
| ADR, DESIGN, RFC | 거버넌스 | `governed` | 승인된 거버넌스 결정 | 승인 게이트를 거친 정본 결정 — 상태(accepted/superseded) 확인 |
| PRD, RUNBOOK, POSTMORTEM | 추적 | `tracked` | 추적 문서 | 리뷰되나 승인 게이트 없음 — drift/staleness 주의 |
| NOTE, (미지/빈값) | 메모 | `memo` | 비거버넌스 메모 | 정본 아님 — 인덱싱·검색용 참고. 정본이면 promote 필요 |

- 입력 정규화: 대소문자·공백 무시. 알 수 없는 값은 `memo`로 보수적 강등.
- **미러 명시:** 이 타입→tier 그룹핑은 specledger `document_types.yaml`(정본)의 **표현용 미러**다.
  모듈 상단 주석에 "source of truth = specledger doctypes; terse 표현 미러(패키지 디커플링)"를 명시한다.
  이는 기존 `nexus/.../external_ingest_skill.py`의 `_KIND_ALIASES` 미러 선례와 동일한 패턴이며,
  **운용 가이드 전문은 미러하지 않고 짧은 신뢰 신호만** 미러하므로 drift 표면이 최소다.

### 3.2 렌더: 기존 두 사이트에 배지 부착

1. **`views/chat.js` `renderEvidence()` (주 surface).** 각 근거 항목(`evidence-item`)의
   제목(`ev-title`) 옆에 `tone`별 배지를 추가하고, 배지에 `title`(호버 툴팁)로 `note`를 단다.
   근거 데이터는 `evidence_snippets[*].doc_type`(#56로 응답에 포함).
2. **`views/documents.js` `renderTable()`.** 기존 raw `doc-type-badge`(타입 텍스트만)를
   `tone` 색 + 툴팁(note)으로 강화. 텍스트는 raw `doc_type` 유지(타입 정보 보존), tone로 등급 신호.

### 3.3 스타일: `css/style.css`

기존 `.doc-type-badge` / `.status-badge` 패턴 재사용. `tone` 3종(`governed`/`tracked`/`memo`)
색 변형 추가(브랜드 토큰 사용). 신규 컴포넌트 최소화.

## 4. 데이터 흐름

```
/search/answer 응답
  └ evidence_snippets[*].doc_type  ──(웹)──▶ trustSignal(doc_type)
                                              └▶ {tone,label,note} ─▶ 배지 렌더(chat/documents)
```

백엔드는 `doc_type`만 제공(기존). 신뢰 신호 번역·표시는 전적으로 뷰 계층.

## 5. 경계 (S3 준수)

S3(intake doc_type, #48)는 **"nexus는 tier 레지스트리 불필요 — tier/거버넌스 파생은
specledger 경계에서만"**을 의도적으로 결정했다. 본 설계는 nexus 백엔드를 **0줄** 바꾸지 않는다.
신뢰 라벨은 뷰 계층 표현물(프론트 i18n/labeling)이며, nexus 서버가 tier를 파생하지 않는다.
따라서 S3 경계는 100% 보존된다. 풀 가이드의 정본은 specledger에 남는다.

## 6. 에러/엣지 처리

- `doc_type`이 없거나 빈 문자열 → `memo`(보수적). 절대 미정의/크래시 없음.
- 알 수 없는 `doc_type` 문자열 → `memo`(default_tier=T3 정책과 일치).
- 배지는 순수 부가 정보 — 누락/실패해도 답변·근거 렌더는 그대로(점진적 향상).

## 7. 테스트/검증

- **JS 테스트 러너 부재:** nexus/web은 vanilla ES 모듈이고 JS 테스트 하니스가 없다. 러너 신설은
  scope creep이라 본 범위에서 기각한다. `trustSignal`은 인자 1개 순수 lookup이라 저위험.
- **검증 = verify 스킬(런타임 관찰):** 실제 적재된 NOTE 코퍼스로 채팅 검색 → 근거 배지가
  `memo` 톤·올바른 라벨/툴팁으로 렌더되는지 관찰. (가능하면 documents 뷰도.)
- (선택, 별도 결정) 향후 vitest 도입 시 `trustSignal` 매핑/기본값 단위 테스트 추가 여지.

## 8. YAGNI / 보류

- 답변 단위 **집계 신뢰 요약**("근거 N건 중 거버넌스 X / 메모 Y")은 가치 있으나 1차 범위 밖 —
  per-근거 배지가 핵심. 수요 확인 시 후속.
- 백엔드 미러(B안)·specledger 발행(C안)은 경계/과잉 이유로 기각(브레인스토밍 기록).
