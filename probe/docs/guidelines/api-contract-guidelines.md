# API 계약 운영 규정 (API Contract Guidelines)

> **프레임워크 위치**: 규정 ② — 개발 중 동기화
> **버전**: v1.1
> **대상**: 프론트엔드 · 백엔드 (+ 기획·디자인은 참조)

---

## 0. 목적

프론트엔드와 백엔드가 **항상 같은 스펙을 보고 개발**하고, API 변경이 발생하면 **상대방이 반드시 인지**하도록 보장한다.

이 규정이 없을 때 반복되는 상황:

| 시점 | 발생하는 문제 | 근본 원인 |
|------|---------------|-----------|
| FE 개발 중 | "이 필드 nullable인지 아닌지 모르겠어요" | 스펙에 nullable 표시 없음 |
| FE-BE 연동 | "스웨거랑 실제 응답이 달라요" | 스웨거가 코드와 동기화되지 않음 |
| FE-BE 연동 | "에러 형태가 엔드포인트마다 달라요" | 에러 응답 구조가 통일되지 않음 |
| 기능 추가 | "이 API 바뀐 거 언제 알려줬어요?" | 변경 전파 체계 없음 |
| 운영 중 | "이 엔드포인트 아직 쓰는 데가 있었네요" | 삭제 전 영향 분석 없음 |

---

## 1. 핵심 원칙

### 1.1 스웨거는 코드에서 생성한다

스웨거(OpenAPI 스펙)를 수작업으로 작성하지 않는다. **코드가 곧 스펙**이다.

| 프로토콜 | 스택 | 도구 | 방식 |
|----------|------|------|------|
| REST | Spring/Kotlin | springdoc-openapi | 어노테이션 → OpenAPI 자동 생성 |
| REST | NestJS | `@nestjs/swagger` | 데코레이터 → OpenAPI 자동 생성 |
| REST | FastAPI | 내장 | Pydantic 모델 → OpenAPI 자동 생성 |
| **WebSocket** | **Spring/Kotlin** | **Springwolf** | **어노테이션 → AsyncAPI 자동 생성** |
| **WebSocket** | **NestJS** | **`@nestjs/asyncapi`** | **데코레이터 → AsyncAPI 자동 생성** |
| 기타 | — | 코드 기반 생성기 우선 | 수작업 yaml은 최후의 수단 |

**이유**: 수작업 스펙은 반드시 코드와 어긋난다. 시간 문제가 아니라 확률의 문제다. REST든 WebSocket이든 동일하다.

### 1.2 스펙 파일은 레포에 커밋한다

CI에서 생성된 OpenAPI 스펙(JSON/YAML)을 레포에 커밋한다.

* REST API 위치: `api/openapi.json` (또는 `api/openapi.yaml`)
* WebSocket API 위치: `api/asyncapi.json` (또는 `api/asyncapi.yaml`)
* 커밋 방법: CI에서 `pnpm api:generate` → diff 발생 시 커밋 또는 PR 생성
* 수작업 편집 금지 (규정 ③의 토큰 산출물과 동일한 원칙)

**커밋하는 이유**:
* Git diff로 API 변경 이력을 추적할 수 있다
* `api:diff`로 breaking 변경을 자동 탐지할 수 있다
* 프론트엔드가 이 파일을 기반으로 타입/클라이언트를 자동 생성한다

### 1.3 프론트엔드가 스웨거만 보고 연동할 수 있어야 한다

이것이 스펙 품질의 판단 기준이다. "Slack으로 물어봐야 아는 것"이 있으면 스펙이 부족한 것이다.

---

## 2. 스펙 품질 레벨 (필수 준수 기준)

### 2.1 레벨 정의

팀은 최소 **Level 2**를 준수해야 하며, **Level 3**을 목표로 한다.

```
Level 1 — 기본 (이것 없으면 스웨거가 아님)
Level 2 — 연동 가능 (프론트가 스웨거만 보고 일할 수 있음)   ← 최소 기준
Level 3 — 유지보수 가능 (새 팀원이 와도 이해 가능)          ← 목표 기준
Level 4 — 성숙 (외부 공개/대규모 팀 수준)                   ← 선택적 확장
```

### 2.2 Level 1 — 기본

이 수준 미달 시 스웨거를 아무도 신뢰하지 않게 된다.

* [ ] 모든 엔드포인트의 요청/응답 **스키마가 실제 코드와 일치**
* [ ] 모든 필드에 **타입이 명시**됨 (`string`, `integer`, `boolean`, `array`, `object`)
* [ ] **required / optional 구분**이 정확함

**린트 규칙**: `pnpm api:lint`에서 타입 미명시 필드, required 미구분 필드 탐지 시 CI 실패.

### 2.3 Level 2 — 연동 가능 (최소 기준)

프론트가 Slack으로 물어보지 않고 연동할 수 있는 수준.

#### 2.3.1 nullable 정확히 표시

현업에서 가장 빈번한 FE-BE 불일치 원인.

```yaml
# 나쁜 예 — nullable인지 알 수 없음
properties:
  nickname:
    type: string

# 좋은 예 — nullable임을 명시
properties:
  nickname:
    type: string
    nullable: true
    description: "사용자 닉네임. 미설정 시 null"
```

**규칙**:
* 모든 필드는 **non-nullable이 기본값**이다
* null이 가능한 필드는 반드시 `nullable: true`를 명시한다
* **nullable과 optional을 동시에 적용하지 않는다** — 혼란의 원인
  * 필드가 응답에 아예 안 올 수 있다 → optional (required에서 제외)
  * 필드는 항상 오지만 값이 null일 수 있다 → nullable
  * 둘 다인 경우가 필요하다면 → 설계를 재검토한다

**린트 규칙**: nullable과 optional이 동시에 적용된 필드 탐지 시 CI 경고.

#### 2.3.2 에러 응답 구조 통일

엔드포인트마다 에러 형태가 다르면 프론트에서 에러 핸들링을 공통화할 수 없다.

**공통 에러 스키마 (필수)**:

```yaml
components:
  schemas:
    ErrorResponse:
      type: object
      required:
        - error
      properties:
        error:
          type: object
          required:
            - code
            - message
          properties:
            code:
              type: string
              description: "머신 판독용 에러 코드 (UPPER_SNAKE_CASE)"
              example: "RESOURCE_NOT_FOUND"
            message:
              type: string
              description: "사람이 읽을 수 있는 에러 메시지"
              example: "요청한 리소스를 찾을 수 없습니다"
            details:
              type: object
              nullable: true
              description: "추가 에러 정보 (필드 검증 에러 등)"
              example: { "field": "email", "reason": "이미 사용 중인 이메일입니다" }
```

**규칙**:
* 모든 4xx/5xx 응답은 위 `ErrorResponse` 스키마를 따른다
* `code`는 프론트가 에러 종류를 구분하는 데 사용한다 (UI 분기 기준)
* `message`는 개발/디버깅용이며, **사용자에게 직접 노출하지 않는 것**을 권장한다
* `details`는 폼 검증 에러 등 추가 정보가 필요한 경우에만 포함한다

**HTTP 상태 코드 사용 규칙**:

| 코드 | 의미 | 사용 기준 |
|------|------|-----------|
| `400` | 잘못된 요청 | 요청 파라미터/바디 검증 실패 |
| `401` | 인증 필요 | 토큰 없음/만료/유효하지 않음 |
| `403` | 권한 없음 | 인증됨 + 해당 리소스에 대한 권한 없음 |
| `404` | 리소스 없음 | 존재하지 않는 리소스 접근 |
| `409` | 충돌 | 동시 수정, 중복 생성 등 |
| `422` | 처리 불가 | 비즈니스 규칙 위반 (형식은 맞으나 로직상 불가) |
| `429` | 요청 초과 | Rate limit 초과 |
| `500` | 서버 에러 | 서버 내부 오류 (클라이언트 잘못 아님) |

**흔한 실수**: 비즈니스 규칙 위반을 `400`으로 처리하는 경우. 요청 형식은 맞지만 비즈니스 로직상 불가한 경우에는 `422`를 사용한다. 예: "잔액 부족"은 `422`, "금액이 숫자가 아님"은 `400`.

#### 2.3.3 페이지네이션 명시

목록 API는 페이지네이션 방식과 파라미터를 반드시 명시한다.

```yaml
# cursor 기반 (권장)
parameters:
  - name: cursor
    in: query
    schema:
      type: string
      nullable: true
    description: "다음 페이지 커서. 첫 요청 시 생략"
  - name: limit
    in: query
    schema:
      type: integer
      default: 20
      minimum: 1
      maximum: 100
    description: "한 페이지당 항목 수"

# 응답
properties:
  items:
    type: array
    items:
      $ref: '#/components/schemas/Resource'
  cursor:
    type: string
    nullable: true
    description: "다음 페이지 커서. null이면 마지막 페이지"
  total:
    type: integer
    description: "전체 항목 수"
```

**규칙**:
* 팀 내 페이지네이션 방식을 **하나로 통일**한다 (cursor 또는 offset)
* 혼용 금지. 엔드포인트마다 다르면 프론트 공통 훅 구현이 불가능하다
* "마지막 페이지" 판별 방법을 반드시 명시한다 (`cursor: null` 또는 `hasNext: false`)

### 2.4 Level 3 — 유지보수 가능 (목표 기준)

새 팀원이 와도 코드를 뜯어보지 않고 스웨거만으로 이해할 수 있는 수준.

#### 2.4.1 enum 값 명시

```yaml
# 나쁜 예
properties:
  status:
    type: string

# 좋은 예
properties:
  status:
    type: string
    enum:
      - ACTIVE
      - INACTIVE
      - SUSPENDED
    description: "사용자 상태"
```

**규칙**: 값이 정해진 유한 집합이면 반드시 enum으로 명시한다. `string`으로만 적혀 있으면 프론트는 어떤 값이 올 수 있는지 코드를 뜯어봐야 한다.

#### 2.4.2 example 제공

```yaml
properties:
  createdAt:
    type: string
    format: date-time
    example: "2025-03-08T09:00:00Z"
    description: "생성 일시 (ISO 8601, UTC)"
  amount:
    type: integer
    example: 15000
    description: "결제 금액 (원 단위, VAT 포함)"
```

**규칙**: 최소한 아래 유형의 필드에는 example을 필수로 넣는다.
* 날짜/시간 (포맷 확인용)
* 금액/수량 (단위 확인용)
* ID/코드 (형식 확인용)
* 복잡한 중첩 객체 (구조 파악용)

#### 2.4.3 deprecated 표시

```yaml
paths:
  /v1/users:
    get:
      deprecated: true
      description: "⚠️ Deprecated — /v2/users를 사용하세요. 2025-06-01 삭제 예정."
      x-sunset: "2025-06-01"
      x-replacement: "/v2/users"
```

**규칙**: 더 이상 사용하지 않는 엔드포인트/필드는 삭제하지 말고 `deprecated: true`를 먼저 표시한다. 삭제 예정일과 대체 경로를 함께 명시한다.

#### 2.4.4 엔드포인트 설명과 태그

```yaml
tags:
  - name: users
    description: "사용자 관리"
  - name: payments
    description: "결제 처리"

paths:
  /users:
    get:
      tags: [users]
      summary: "사용자 목록 조회"
      description: |
        관리자 권한이 필요합니다.
        검색/필터/정렬을 지원하며, cursor 기반 페이지네이션을 사용합니다.
```

### 2.5 Level 4 — 성숙 (선택적 확장)

외부 API 제공이나 대규모 팀에서 필요한 수준. 중규모 팀에서는 선택.

* 비즈니스 에러 코드의 완전한 enum 관리 (모든 `code` 값을 중앙에서 관리)
* 엔드포인트별 rate limit 명시 (`x-rate-limit` 커스텀 필드)
* API 버저닝 전략 (URL path 기반 또는 헤더 기반)
* API changelog 자동 생성
* 요청/응답 예시의 시나리오별 분류 (성공/에러/엣지 케이스)

---

## 3. 공통 스키마 규칙

### 3.1 네이밍 컨벤션

| 대상 | 규칙 | 예시 |
|------|------|------|
| 엔드포인트 | `kebab-case`, 복수형 명사 | `/user-groups`, `/payment-methods` |
| 필드명 | `camelCase` | `createdAt`, `userId`, `isActive` |
| 에러 코드 | `UPPER_SNAKE_CASE` | `RESOURCE_NOT_FOUND`, `LIMIT_EXCEEDED` |
| enum 값 | `UPPER_SNAKE_CASE` | `ACTIVE`, `INACTIVE` |
| 쿼리 파라미터 | `camelCase` | `sortBy`, `pageSize`, `createdAfter` |

### 3.2 날짜/시간 형식

* 형식: **ISO 8601** (`2025-03-08T09:00:00Z`)
* 시간대: **UTC** (클라이언트가 로컬 시간으로 변환)
* OpenAPI: `type: string, format: date-time`
* 날짜만 필요한 경우: `type: string, format: date` (`2025-03-08`)

### 3.3 ID 형식

* 형식: 팀 내 **하나로 통일** (UUID v4 또는 auto-increment integer)
* OpenAPI: `type: string, format: uuid` 또는 `type: integer, format: int64`
* 혼용 금지: 같은 API 내에서 어떤 엔드포인트는 UUID, 어떤 엔드포인트는 integer이면 프론트 타입 정의가 복잡해진다

### 3.4 목록 응답 공통 구조

```yaml
components:
  schemas:
    PaginatedResponse:
      type: object
      required:
        - items
        - cursor
        - total
      properties:
        items:
          type: array
          description: "현재 페이지의 항목 목록"
        cursor:
          type: string
          nullable: true
          description: "다음 페이지 커서. null이면 마지막 페이지"
        total:
          type: integer
          description: "전체 항목 수 (필터 적용 후)"
```

모든 목록 API는 이 구조를 따른다. 엔드포인트마다 다른 형태의 목록 응답을 만들지 않는다.

---

## 4. API 변경 관리

### 4.1 변경 분류

| 변경 유형 | 예시 | 호환성 | 라벨 |
|-----------|------|--------|------|
| **추가** | 새 엔드포인트, 응답에 optional 필드 추가, 새 optional 파라미터 | 호환 | `api:additive` |
| **수정** | 필드 타입 변경, required ↔ optional 변경, 응답 구조 변경 | **비호환** | `api:breaking` |
| **삭제** | 엔드포인트 제거, 필드 제거, enum 값 제거 | **비호환** | `api:breaking` |
| **동작 변경** | 같은 입력에 다른 결과, 정렬 순서 변경, 기본값 변경 | **잠재적 비호환** | `api:breaking` |
| **폐기 예고** | deprecated 표시 추가 | 호환 | `api:deprecation` |

**판단 기준**: "프론트엔드 코드를 한 줄도 안 바꿔도 기존처럼 동작하는가?"
* Yes → 호환 (`api:additive`)
* No 또는 불확실 → 비호환 (`api:breaking`)

### 4.2 호환 변경 (Additive) 절차

```
BE가 기능 구현 + 스펙 자동 생성
    │
    ├─ PR에 `api:additive` 라벨
    ├─ CI에서 api:diff 자동 실행 → 변경 요약 PR 코멘트
    ├─ BE 리뷰어 1명 승인
    │
    └─ 머지 → api:codegen 자동 실행 → FE 타입 갱신 알림
```

### 4.3 비호환 변경 (Breaking) 절차

```
BE가 변경 필요성 인지
    │
    ├─ 1. FE와 변경 범위 사전 합의 (Slack/미팅)
    │
    ├─ 2. 마이그레이션 전략 결정
    │     ├─ 전략 A: 신규 엔드포인트 추가 → 구 엔드포인트 deprecated → 삭제
    │     └─ 전략 B: FE-BE 동시 배포 (작은 변경에 한해)
    │
    ├─ 3. PR 생성
    │     ├─ `api:breaking` 라벨
    │     ├─ 마이그레이션 가이드 포함 (before/after 예시)
    │     └─ 영향받는 FE 코드 목록
    │
    ├─ 4. 리뷰
    │     ├─ BE 리뷰어 1명
    │     └─ FE 리뷰어 1명 (필수)
    │
    └─ 5. 머지 → FE 마이그레이션 PR 연쇄
```

### 4.4 Deprecation 생명주기

```
[Active] → [Deprecated] → [Sunset] → [Removed]
```

| 단계 | 스펙 표시 | 런타임 동작 | 최소 유지 기간 |
|------|-----------|-------------|----------------|
| Active | — | 정상 | — |
| Deprecated | `deprecated: true` + `x-sunset` + `x-replacement` | 정상 동작 + 응답 헤더 `Deprecation: true` | — |
| Sunset | 위와 동일 | 정상 동작 + 응답 헤더 `Sunset: <date>` | **2 스프린트** (sunset 기간) |
| Removed | 스펙에서 제거 | `410 Gone` | — |

**규칙**:
* Deprecated 표시 없이 바로 삭제하는 것은 금지한다
* Sunset 기간(최소 2 스프린트) 중 해당 엔드포인트 호출이 0건임이 로그로 확인된 후 삭제한다
* 긴급 삭제(보안 이슈 등)는 예외 절차를 따른다

### 4.5 PR 필수 포함 항목

```md
## API Change

### What
- (변경 요약 1~2문장)

### Changed endpoints
- `METHOD /path` — 변경 내용

### Compatibility
- breaking: yes|no
- migration guide: (breaking이면 필수, before/after 예시 포함)

### Affected clients
- (영향받는 FE 코드/화면 목록)

### State Matrix sync
- (관련 State Matrix 업데이트 여부 — 규정 ① 연동)

### Checklist
- [ ] api:additive | api:breaking | api:deprecation
- [ ] 스펙이 코드에서 자동 생성됨 (수작업 편집 아님)
- [ ] nullable / required 정확히 표시
- [ ] 에러 응답이 ErrorResponse 스키마를 따름
- [ ] (breaking이면) FE 리뷰어 승인
- [ ] (breaking이면) 마이그레이션 가이드 포함
```

---

## 5. 스펙 기반 자동화

### 5.1 필수 스크립트

| 스크립트 | 역할 | 실행 시점 |
|----------|------|-----------|
| `pnpm api:generate` | 코드에서 OpenAPI 스펙 JSON/YAML 생성 | BE 빌드 시 |
| `pnpm api:lint` | 스펙 품질 검증 (아래 5.2 규칙) | CI |
| `pnpm api:diff` | Git diff 기반 API 변경 탐지 + breaking 여부 판별 | PR 생성 시 |
| `pnpm api:compatibility` | 이전 버전 스펙과 호환성 검사 | CI (`api:breaking` 라벨 PR) |
| `pnpm api:codegen` | 스펙 → FE 타입/클라이언트 자동 생성 | API 변경 머지 시 |
| `pnpm api:mock` | 스펙 기반 Mock 서버 실행 | FE 로컬 개발 시 |

### 5.2 `pnpm api:lint` 검사 규칙

| 규칙 | 심각도 | 설명 |
|------|--------|------|
| 타입 미명시 필드 | error | 모든 필드에 type 필수 |
| required 미구분 | error | required 목록에 누락 또는 과잉 |
| nullable + optional 동시 적용 | warning | 설계 재검토 권장 |
| 에러 응답 스키마 불일치 | error | ErrorResponse 스키마를 따르지 않는 4xx/5xx |
| enum 미사용 (`type: string`이나 값이 유한 집합) | warning | enum 전환 권장 |
| example 누락 (날짜/금액/ID) | warning | Level 3 기준 |
| description 누락 | warning | 주요 필드에 설명 권장 |
| deprecated 표시 없이 삭제 | error | Deprecation 절차 미준수 |
| 네이밍 컨벤션 위반 | error | 3.1 규칙 미준수 |
| 페이지네이션 미명시 (배열 응답) | warning | 목록 API에 페이지네이션 권장 |

### 5.3 `pnpm api:diff` 출력 형식

PR 코멘트로 자동 게시.

```md
## API Diff Report

### Summary
- 2 endpoints changed, 1 endpoint added, 0 endpoints removed
- Breaking changes: NO

### Changes

#### Added
- `GET /v1/notifications` — 알림 목록 조회

#### Modified
- `GET /v1/users`
  - Response: added optional field `lastLoginAt` (string, nullable)
  - ✅ Additive (non-breaking)

- `POST /v1/payments`
  - Request: field `currency` changed from optional to required
  - ⚠️ Breaking — 기존 클라이언트가 currency를 안 보내면 400 에러
```

### 5.4 `pnpm api:codegen` 동작

스펙에서 프론트엔드 타입과 API 클라이언트를 자동 생성한다.

**생성물**:

| 파일 | 내용 |
|------|------|
| `src/api/types.ts` | 요청/응답 타입 정의 |
| `src/api/client.ts` | API 호출 함수 (fetch/axios 래퍼) |
| `src/api/errors.ts` | 에러 코드 enum + 에러 타입 |

**규칙**:
* 생성된 파일은 **수작업 편집 금지** (덮어쓰기됨)
* 커스텀 로직이 필요하면 생성된 파일을 import하는 별도 파일에서 확장
* 생성 도구: `openapi-typescript` + 커스텀 코드젠 또는 `orval` 등 팀에 맞는 도구 선택

### 5.5 `pnpm api:mock` 동작

OpenAPI 스펙 기반으로 Mock 서버를 자동 실행한다.

**용도**:
* BE API가 아직 구현되지 않았을 때 FE 개발 가능
* State Matrix의 에러 케이스를 강제로 재현 (특정 에러 코드 반환 설정)

**도구**: Prism, MSW(Mock Service Worker), 또는 팀에 맞는 도구 선택

**규칙**:
* Mock 서버의 응답은 스펙을 정확히 따른다 (커스텀 Mock 금지 — 스펙 기반만 허용)
* 스펙에 example이 있으면 example을 반환, 없으면 스키마 기반 랜덤 생성

---

## 6. WebSocket 계약 관리

OpenAPI(Swagger)는 HTTP 요청-응답 모델 전용이다. WebSocket의 양방향 지속 연결, 서버 푸시, 이벤트 스트리밍은 OpenAPI로 표현할 수 없다. WebSocket API는 **AsyncAPI** 스펙으로 별도 관리한다.

### 6.1 OpenAPI vs AsyncAPI — 역할 분리

| 프로토콜 | 스펙 도구 | 커버하는 것 | 커버하지 못하는 것 |
|----------|-----------|-------------|---------------------|
| REST | OpenAPI (Swagger) | 요청/응답 스키마, HTTP 상태 코드, 에러 구조 | 양방향 통신, 이벤트 스트림, 연결 상태 |
| WebSocket | AsyncAPI | 채널, 이벤트 이름, pub/sub 메시지 스키마 | HTTP 요청/응답 (REST 영역) |

**원칙**: 하나의 API가 REST + WebSocket을 함께 사용하면, 두 스펙 파일이 모두 존재해야 한다.

### 6.2 AsyncAPI 도입 범위

**백엔드만 도입한다.** 프론트엔드에 AsyncAPI 의존성을 추가할 필요는 없다.

```
BE (생산)                          FE (소비)
─────────                          ─────────
코드에서 AsyncAPI 스펙 자동 생성     생성된 문서 UI로 스펙 확인
  (Springwolf 어노테이션 등)        스펙에서 타입 자동 생성 (선택)
                                   스펙 기반으로 이벤트 핸들러 구현
```

OpenAPI에서 springdoc이 하는 역할을 AsyncAPI에서는 Springwolf가 한다. 프론트엔드가 스웨거 UI를 브라우저로 보는 것처럼, AsyncAPI Studio(문서 UI)를 보는 것이 전부다.

### 6.3 도입 기준

모든 프로젝트에 AsyncAPI가 필요한 것은 아니다.

| WebSocket 이벤트 수 | 권장 관리 방식 |
|---------------------|----------------|
| 1~5개 (단순) | 레포 내 마크다운 문서 + 공유 TypeScript 타입 정의 |
| 6개 이상 또는 복잡한 pub/sub | **AsyncAPI 도입** |
| 외부 공개 WebSocket API | **AsyncAPI 필수** |

"단순"의 기준: 채널이 1~2개이고, 메시지 종류가 5개 이하이며, 단방향(서버→클라이언트) 위주인 경우.

### 6.4 AsyncAPI 스펙 필수 항목

AsyncAPI를 도입하면 아래 항목을 반드시 포함한다.

```yaml
asyncapi: '2.6.0'
info:
  title: 서비스명 WebSocket API
  version: '1.0.0'
  description: WebSocket 이벤트 스펙

servers:
  production:
    url: wss://api.example.com/ws
    protocol: ws

channels:
  /notifications:                          # 채널 경로
    description: "실시간 알림 채널"
    subscribe:                              # 클라이언트가 수신하는 메시지
      operationId: onNotification
      message:
        $ref: '#/components/messages/Notification'
    publish:                                # 클라이언트가 발신하는 메시지
      operationId: sendAck
      message:
        $ref: '#/components/messages/NotificationAck'

components:
  messages:
    Notification:
      name: notification
      title: 알림 이벤트
      payload:
        type: object
        required:
          - eventType
          - data
          - timestamp
        properties:
          eventType:
            type: string
            enum:
              - NEW_MESSAGE
              - STATUS_CHANGED
              - USER_JOINED
            description: "이벤트 종류"
          data:
            type: object
            description: "이벤트별 페이로드"
          timestamp:
            type: string
            format: date-time
            example: "2025-03-08T09:00:00Z"

    NotificationAck:
      name: notificationAck
      title: 알림 수신 확인
      payload:
        type: object
        required:
          - eventId
        properties:
          eventId:
            type: string
            format: uuid
```

### 6.5 WebSocket 메시지 설계 규칙

REST API의 공통 규칙(3절)과 동일한 원칙을 WebSocket 메시지에도 적용한다.

#### 6.5.1 공통 메시지 봉투 (Message Envelope)

모든 WebSocket 메시지는 아래 공통 구조를 따른다.

```yaml
# 서버 → 클라이언트 메시지
WebSocketMessage:
  type: object
  required:
    - eventType
    - data
    - timestamp
  properties:
    eventType:
      type: string
      description: "이벤트 종류 (UPPER_SNAKE_CASE)"
    data:
      type: object
      description: "이벤트별 페이로드"
    timestamp:
      type: string
      format: date-time
    correlationId:
      type: string
      format: uuid
      description: "요청-응답 매칭용 ID (해당 시)"

# 에러 메시지
WebSocketError:
  type: object
  required:
    - eventType
    - error
    - timestamp
  properties:
    eventType:
      type: string
      const: "ERROR"
    error:
      type: object
      required:
        - code
        - message
      properties:
        code:
          type: string
          description: "에러 코드 (REST ErrorResponse와 동일 네이밍)"
        message:
          type: string
    timestamp:
      type: string
      format: date-time
```

**규칙**:
* `eventType`은 `UPPER_SNAKE_CASE`로 통일한다 (REST의 에러 코드 네이밍과 동일)
* 에러 메시지의 `error` 구조는 REST `ErrorResponse`의 `error`와 동일하게 유지한다 — FE가 에러 핸들링을 공통화할 수 있다
* `timestamp`는 ISO 8601, UTC

#### 6.5.2 이벤트 네이밍 규칙

| 대상 | 규칙 | 예시 |
|------|------|------|
| 채널 경로 | `kebab-case` (REST 엔드포인트와 동일) | `/chat-rooms`, `/notifications` |
| eventType | `UPPER_SNAKE_CASE` | `NEW_MESSAGE`, `USER_JOINED`, `STATUS_CHANGED` |
| 클라이언트→서버 액션 | `동사_목적어` | `SEND_MESSAGE`, `JOIN_ROOM`, `MARK_READ` |
| 서버→클라이언트 이벤트 | `형용사/과거분사_목적어` 또는 `상태` | `MESSAGE_RECEIVED`, `USER_LEFT`, `TYPING` |

#### 6.5.3 연결 상태 이벤트 (필수)

WebSocket을 사용하는 모든 기능은 아래 **연결 상태 이벤트를 반드시 정의**한다. 이것은 State Matrix(규정 ①)의 Layer 4와 직접 연결된다.

| 이벤트 | 방향 | 설명 | State Matrix 대응 |
|--------|------|------|---------------------|
| `CONNECTED` | 서버→클라 | 연결 성공 | `collab:connected` |
| `DISCONNECTED` | 감지 | 연결 끊김 | `collab:disconnected` |
| `RECONNECTING` | 클라 내부 | 재연결 시도 중 | `collab:reconnecting` |
| `ERROR` | 서버→클라 | 서버 에러 발생 | `error:server` |
| `PING` / `PONG` | 양방향 | 연결 유지 확인 | — (인프라 레벨) |

### 6.6 WebSocket 변경 관리

REST API 변경 관리(4절)와 동일한 원칙을 따른다.

| 변경 유형 | 예시 | 호환성 | 라벨 |
|-----------|------|--------|------|
| 새 이벤트 추가 | 새 `eventType` 추가 | 호환 | `api:additive` |
| 메시지 필드 추가 (optional) | `data`에 optional 필드 추가 | 호환 | `api:additive` |
| 이벤트 삭제/rename | `eventType` 제거 또는 변경 | **비호환** | `api:breaking` |
| 메시지 구조 변경 | required 필드 추가, 타입 변경 | **비호환** | `api:breaking` |
| 채널 경로 변경 | `/chat` → `/chat-rooms` | **비호환** | `api:breaking` |

**추가 규칙**:
* WebSocket 이벤트도 REST와 동일한 Deprecation 생명주기(4.4절)를 따른다
* deprecated 이벤트는 `eventType` 목록에서 제거하지 않고, 스펙에 `deprecated: true`를 표시한다
* Breaking 변경 시 FE 리뷰어 승인 필수 (REST와 동일)

### 6.7 WebSocket 전용 자동화 스크립트

| 스크립트 | 역할 | 실행 시점 |
|----------|------|-----------|
| `pnpm api:generate` | OpenAPI + AsyncAPI 스펙 모두 생성 (통합) | BE 빌드 시 |
| `pnpm ws:lint` | AsyncAPI 스펙 검증 (메시지 봉투 준수, 네이밍, 필수 이벤트) | CI |
| `pnpm ws:codegen` | AsyncAPI → FE 이벤트 타입/핸들러 타입 자동 생성 | API 변경 머지 시 |

**`pnpm ws:codegen` 생성물**:

| 파일 | 내용 |
|------|------|
| `src/api/ws-types.ts` | 이벤트별 메시지 페이로드 타입 |
| `src/api/ws-events.ts` | eventType enum + 이벤트 매핑 타입 |

**규칙**:
* 생성된 파일은 수작업 편집 금지 (REST codegen과 동일)
* WebSocket 연결/재연결 로직 자체는 생성하지 않는다 — 이건 FE 구현 영역

### 6.8 단순 WebSocket (AsyncAPI 미도입 시)

이벤트가 5개 이하로 단순한 경우, AsyncAPI 대신 아래 방식으로 관리한다.

**관리 방식**: 레포 내 마크다운 + 공유 TypeScript 타입

```
api/
├── openapi.json            ← REST API (자동 생성)
└── websocket/
    ├── events.md           ← 이벤트 목록 + 메시지 구조 (마크다운)
    └── types.ts            ← 공유 타입 정의 (FE-BE 공통 import)
```

**`events.md` 최소 포함 항목**:

```md
# WebSocket Events

## 연결 정보
- URL: `wss://api.example.com/ws`
- 인증: Bearer token (query param `token` 또는 첫 메시지)
- Heartbeat: 30초 간격 ping/pong

## 이벤트 목록

### NEW_MESSAGE (서버 → 클라이언트)
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| eventType | `"NEW_MESSAGE"` | Y | |
| data.messageId | string (uuid) | Y | |
| data.content | string | Y | 메시지 본문 |
| data.sender | object | Y | `{ id, name, avatar }` |
| data.sentAt | string (date-time) | Y | ISO 8601, UTC |
| timestamp | string (date-time) | Y | |

### SEND_MESSAGE (클라이언트 → 서버)
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| action | `"SEND_MESSAGE"` | Y | |
| data.content | string | Y | 메시지 본문 |
| data.roomId | string (uuid) | Y | |
```

**`types.ts` 예시**:

```typescript
// FE-BE 공유 타입 — 양쪽에서 import

export type WsEventType = 'NEW_MESSAGE' | 'USER_JOINED' | 'USER_LEFT' | 'TYPING' | 'ERROR';

export interface WsMessage<T = unknown> {
  eventType: WsEventType;
  data: T;
  timestamp: string; // ISO 8601
  correlationId?: string;
}

export interface WsError {
  eventType: 'ERROR';
  error: {
    code: string;
    message: string;
  };
  timestamp: string;
}

// 이벤트별 페이로드
export interface NewMessagePayload {
  messageId: string;
  content: string;
  sender: { id: string; name: string; avatar: string | null };
  sentAt: string;
}

export interface TypingPayload {
  userId: string;
  roomId: string;
  isTyping: boolean;
}
```

**공유 타입의 위치 선택**:

| 레포 구조 | 타입 위치 | 방식 |
|-----------|-----------|------|
| 모노레포 (FE+BE 같은 레포) | `packages/shared/ws-types.ts` | 직접 import |
| 멀티레포 | 별도 npm 패키지 또는 Git submodule | 패키지 publish → 양쪽에서 install |
| BE가 Kotlin/Java (타입 공유 불가) | `api/websocket/types.ts` (BE 레포에 위치) | FE가 BE 레포의 타입 파일을 참조 또는 복사 |

### 6.9 State Matrix 연결

WebSocket 이벤트는 State Matrix(규정 ①)의 **Layer 4(비즈니스 특수 상태)** 또는 연결 상태와 직접 연결된다.

| WebSocket 관심사 | State Matrix 위치 | 예시 |
|-------------------|---------------------|------|
| 연결/끊김/재연결 | Layer 4 (`collab:connected` 등) | 연결 상태 이벤트 5종 |
| 서버 푸시 데이터 | Layer 1 (`success` 내 실시간 갱신) | 새 메시지 수신 → 목록 갱신 |
| WebSocket 에러 | Layer 1 (`error`) | 서버 에러 이벤트 → 에러 UI |

**규칙**: WebSocket을 사용하는 화면의 State Matrix에는 **연결 상태 3종(connected/disconnected/reconnecting)**을 반드시 포함한다.

---

## 7. CI 게이트

### 7.1 CI 단계 (API 관련)

```
API 스펙 파일 변경이 포함된 PR
    │
    ├─ 1. pnpm api:generate (스펙 재생성 → 커밋된 파일과 일치 확인)
    ├─ 2. pnpm api:lint (스펙 품질 검증)
    ├─ 3. pnpm ws:lint (AsyncAPI 스펙 검증 — WebSocket 변경 시)
    ├─ 4. pnpm api:diff (변경 요약 + breaking 판별 → PR 코멘트)
    ├─ 5. pnpm api:compatibility (breaking 시 호환성 상세 검사)
    └─ 6. 라벨 자동 제안 (api:additive | api:breaking | api:deprecation)
```

### 7.2 머지 조건

| 조건 | `api:additive` | `api:breaking` | `api:deprecation` |
|------|----------------|----------------|---------------------|
| api:lint 통과 | 필수 | 필수 | 필수 |
| ws:lint 통과 (WebSocket 변경 시) | 필수 | 필수 | 필수 |
| api:diff 리포트 PR 코멘트 | 필수 | 필수 | 필수 |
| BE 리뷰어 승인 | 1명 | 1명 | 1명 |
| FE 리뷰어 승인 | — | **필수 1명** | — |
| 마이그레이션 가이드 | — | **필수** | — |
| Sunset 기간 명시 | — | — | **필수** |

### 7.3 실패 메시지

CI 실패 시 PR 코멘트에 아래를 남긴다.

* 실패 단계 (api:lint / ws:lint / api:diff / api:compatibility)
* 실패 원인 요약 (1~3줄)
* 수정 가이드 (해당 Level의 규칙 참조)

---

## 8. 다른 규정과의 연결

### 8.1 규정 ① (State Matrix) → 규정 ②

State Matrix의 "API 응답" 칸이 API 스펙의 근거가 된다.

| 연결 포인트 | 방향 | 자동 검증 |
|-------------|------|-----------|
| State Matrix의 에러 코드 → API 에러 응답 enum | ① → ② | CI에서 교차 검증 (에러 코드 누락 탐지) |
| State Matrix의 응답 구조 → API 응답 스키마 | ① → ② | 수동 (Kick-off에서 합의) |
| API 스펙의 에러 코드 추가 → State Matrix 업데이트 | ② → ① | Claude Code hook (불일치 시 경고) |

### 8.2 규정 ② → 규정 ③ (UI 변경)

| 연결 포인트 | 방향 | 자동 검증 |
|-------------|------|-----------|
| API 에러 응답 구조 → 에러 컴포넌트 props | ② → ③ | api:codegen이 에러 타입 생성 → 컴포넌트가 import |
| API 응답 nullable 필드 → 컴포넌트 empty state | ② → ③ | 타입 체크에서 nullable 미처리 탐지 |

---

## 9. AI 자동화

### 9.1 자동화 항목

| 항목 | 트리거 | 동작 | 도구 |
|------|--------|------|------|
| API 변경 요약 생성 | API 스펙 변경 PR 생성 | 변경된 엔드포인트/필드 목록 + breaking 여부 요약 | Claude Code hook |
| Breaking 변경 영향 분석 | `api:breaking` 라벨 PR | FE 코드에서 영향받는 호출 지점 탐지 | Claude Code + api:diff |
| 마이그레이션 가이드 초안 | `api:breaking` 라벨 PR | before/after 코드 예시 자동 생성 | Claude Code hook |
| State Matrix 불일치 탐지 | API 스펙 변경 머지 | 에러 코드 교차 검증 → 불일치 시 이슈 생성 | CI script |
| FE 타입 갱신 알림 | API 변경 머지 | api:codegen 실행 + FE 채널에 변경 요약 알림 | CI + Slack bot |

### 9.2 AI가 하지 않는 것

* API **설계를 결정**하는 것 (엔드포인트 구조, 리소스 모델링은 개발자 판단)
* Breaking 변경의 **마이그레이션 전략을 결정**하는 것 (신규 엔드포인트 vs 동시 배포)
* Mock 서버의 **비즈니스 로직을 구현**하는 것 (스펙 기반 응답만 생성)

---

## 10. 예외 처리

### 10.1 스펙 없이 선 개발

프로토타입이나 PoC에서 스펙 없이 개발을 시작할 수 있다.

* [ ] 정식 기능 전환 시 **스펙을 반드시 소급 생성**
* [ ] 소급 시 코드에서 자동 생성 (수작업 yaml 금지)
* [ ] 태스크에 `api:spec-pending` 라벨 → 소급 완료 시 제거

### 10.2 외부 API 연동

직접 통제할 수 없는 외부 API의 경우:

* 외부 API 스펙을 `api/external/` 디렉토리에 별도 관리
* 외부 API 래퍼(wrapper) 레이어를 만들어 내부 스펙 규칙을 적용
* 외부 API 변경은 래퍼 레이어에서 흡수하고, 내부 인터페이스는 안정적으로 유지

### 10.3 긴급 보안 패치

보안 취약점으로 인한 긴급 API 변경:

* Deprecation 기간 없이 즉시 변경/삭제 가능
* [ ] 변경 후 **1영업일 이내** 스펙 업데이트 + FE 전원 통보
* [ ] 사후 보고서에 영향 범위와 조치 내용 기록

---

## 11. 점검 지표

| 지표 | 측정 방법 | 목표 |
|------|-----------|------|
| **스펙-코드 일치율** | `api:generate` 결과와 커밋된 스펙의 diff 발생 빈도 | **0건** (항상 일치) |
| **FE-BE "이거 어떻게 되는 거예요?" 빈도** | Slack #api-questions 채널 메시지 수 / 스프린트 | 도입 전 대비 **60% 감소** |
| **Breaking 변경 사전 합의율** | FE와 사전 합의 후 PR 생성 비율 | **100%** |
| **Deprecation 절차 준수율** | deprecated 표시 없이 삭제된 엔드포인트 수 | **0건** |
| **api:lint 통과율** | 첫 CI 실행에서 통과한 비율 | **90% 이상** |

---

## 12. 운영 시작 체크리스트

1. [ ] 코드 기반 스펙 생성 도구 설정 (springdoc 등)
2. [ ] `pnpm api:generate` → 레포에 `api/openapi.json` 첫 커밋
3. [ ] 공통 에러 스키마 (`ErrorResponse`) 정의 및 전체 엔드포인트 적용
4. [ ] nullable / required 전수 점검 (기존 엔드포인트 대상)
5. [ ] `pnpm api:lint` 구현 및 CI 적용
6. [ ] `pnpm api:diff` 구현 및 PR 코멘트 자동화
7. [ ] `pnpm api:codegen` 구현 (FE 타입 자동 생성)
8. [ ] `pnpm api:mock` 구현 (FE 로컬 개발용)
9. [ ] **(WebSocket 사용 시)** AsyncAPI 도입 여부 판단 (6.3 기준)
10. [ ] **(AsyncAPI 도입 시)** Springwolf 설정 + `api/asyncapi.json` 첫 커밋
11. [ ] **(AsyncAPI 미도입 시)** `api/websocket/events.md` + `types.ts` 작성
12. [ ] **(WebSocket 사용 시)** `pnpm ws:lint` 구현 및 CI 적용
13. [ ] **(WebSocket 사용 시)** `pnpm ws:codegen` 구현 (FE 이벤트 타입 자동 생성)
14. [ ] API 변경 Slack 알림 설정
15. [ ] 팀 내 Level 2 기준 소개 및 합의

---

## 변경 이력

| 버전 | 날짜 | 변경 요약 |
|------|------|-----------|
| v1.0 | 2025-03-08 | 초안 |
| v1.1 | 2025-03-08 | WebSocket 계약 관리 섹션(6절) 추가 — AsyncAPI 도입 기준, 메시지 설계 규칙, 공통 봉투, 단순 WebSocket 관리 방식, State Matrix 연결 |
