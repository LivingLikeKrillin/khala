# 실무 템플릿 모음

> 프레임워크 부속 문서. 팀이 바로 복붙해서 쓸 수 있는 템플릿.

---

## 1. PR 템플릿 — UI 변경 (`ui:tokens | ui:components | ui:screens | ui:cleanup`)

```md
## What
- 

## Why
- 

## Evidence
- VRT: <link>
- a11y lint: ✅ passed

## Impact
### Changed tokens
- none

### Affected components
- none

### Affected screens/routes
- none

### Risk
- scope: local | wide
- breaking: no | yes
- notes: 

## Checklist

### 공통
- [ ] PR 라벨: `ui:tokens` | `ui:components` | `ui:screens` | `ui:cleanup`
- [ ] (breaking이면) `ui:breaking` 라벨 추가
- [ ] 변경 의도 1~2문장 작성
- [ ] VRT 리포트 링크 첨부
- [ ] VRT approved (light + dark)
- [ ] Impact 섹션 작성 완료

### ui:tokens (해당 시)
- [ ] `pnpm design:sync`로 산출물 최신 상태
- [ ] `pnpm lint:tokens` 통과
- [ ] Foundations 갤러리에 변경 반영 확인
- [ ] `origin: figma | code` 명시
- [ ] (삭제/rename) 마이그레이션 가이드 포함
- [ ] (deprecation) `tokens.json`에 deprecated 표시 + 삭제 예정 시점 명시

### ui:components (해당 시)
- [ ] Storybook 스토리 업데이트 (variants/state 동기화)
- [ ] `pnpm lint:a11y` 통과
- [ ] 키보드 인터랙션 확인
- [ ] 대비 기준 충족
- [ ] (breaking props) 마이그레이션 가이드 포함

### ui:screens (해당 시)
- [ ] Screen Story 최소 1개 (`src/storybook/screens/`)
- [ ] `loading` 상태 Screen Story 포함
- [ ] `empty` 또는 `error` 상태 Screen Story 포함
- [ ] mobile(375px) + desktop(1280px) VRT 스냅샷 존재

### ui:cleanup (해당 시)
- [ ] 사용처 0개 증거 첨부 (`pnpm ui:impact` 결과 또는 레포 검색 로그)
- [ ] Skeleton Story 잔존 여부 확인
```

---

## 2. PR 템플릿 — API 변경 (`api:additive | api:breaking | api:deprecation`)

```md
## What
- 

## Why
- 

## API Change

### Changed endpoints
- `METHOD /path` — 변경 내용

### Compatibility
- breaking: no | yes
- migration guide: (breaking이면 필수)

### Affected clients
- (영향받는 FE 코드/화면 목록, 없으면 none)

### State Matrix sync
- (관련 State Matrix 업데이트 여부, 없으면 N/A)

## Evidence
- api:diff: <link 또는 아래 CI 코멘트 참조>

## Checklist

### 공통
- [ ] PR 라벨: `api:additive` | `api:breaking` | `api:deprecation`
- [ ] 스펙이 코드에서 자동 생성됨 (수작업 편집 아님)
- [ ] `pnpm api:lint` 통과
- [ ] `pnpm api:diff` 리포트 PR 코멘트 확인

### 스펙 품질 (Level 2 최소 기준)
- [ ] 모든 필드에 타입 명시
- [ ] required / optional 구분 정확
- [ ] nullable 필드에 `nullable: true` 명시
- [ ] 에러 응답이 `ErrorResponse` 공통 스키마를 따름
- [ ] (목록 API) 페이지네이션 방식 + 파라미터 명시

### 스펙 품질 (Level 3 목표 기준, 해당 시)
- [ ] enum 값 명시 (유한 집합인 string 필드)
- [ ] example 제공 (날짜/금액/ID/복잡 객체)
- [ ] deprecated 표시 (폐기 예고 시)

### api:breaking (해당 시)
- [ ] FE와 사전 합의 완료
- [ ] 마이그레이션 가이드 포함 (before/after 예시)
- [ ] FE 리뷰어 승인

### api:deprecation (해당 시)
- [ ] `deprecated: true` + `x-sunset` + `x-replacement` 표시
- [ ] Sunset 기간 명시 (최소 2 스프린트)

### WebSocket 변경 (해당 시)
- [ ] `pnpm ws:lint` 통과
- [ ] 메시지 봉투(envelope) 공통 구조 준수
- [ ] eventType 네이밍 규칙 준수 (UPPER_SNAKE_CASE)
- [ ] 연결 상태 이벤트 정의 확인
```

---

## 3. PR 템플릿 — 통합 (UI + API 동시 변경 시)

```md
## What
- 

## Why
- 

---

### UI Change

#### Evidence
- VRT: <link>

#### Impact
##### Changed tokens
- none

##### Affected components
- none

##### Affected screens/routes
- none

##### Risk
- scope: local | wide
- breaking: no | yes
- notes: 

---

### API Change

#### Changed endpoints
- `METHOD /path` — 변경 내용

#### Compatibility
- breaking: no | yes
- migration guide: 

#### Affected clients
- 

---

### State Matrix sync
- (관련 State Matrix 업데이트 여부)

## Checklist
- [ ] PR 라벨: (해당 라벨 모두 선택)
- [ ] UI: VRT approved (light + dark)
- [ ] UI: `pnpm lint:a11y` 통과
- [ ] API: `pnpm api:lint` 통과
- [ ] API: `pnpm api:diff` 리포트 확인
- [ ] State Matrix 동기화 확인
```

---

## 4. State Matrix 템플릿 (`_template.md`)

```md
# State Matrix: [기능/화면 이름]

> 작성자: @
> 최종 확인일: YYYY-MM-DD
> 관련 태스크: [PROJ-0000](링크)
> 확인: 기획(  ) · 디자인(  ) · FE(  ) · BE(  )

---

## Layer 1. 데이터 상태 (필수)

| 상태 | 조건 | 화면 처리 | API 응답 | 비고 |
|------|------|-----------|----------|------|
| `loading` | | | — | |
| `empty` | | | | |
| `success` | | | | |
| `error` | | | | |

> error를 세분화할 경우 아래를 추가:
> | `error:network` | 네트워크 단절/타임아웃 | | timeout | |
> | `error:server` | 5xx 응답 | | 500 | |
> | `error:business` | 비즈니스 규칙 위반 | | 4xx + error code | |

---

## Layer 2. 권한·인증 상태

> 해당 없음 시 "N/A — 이 화면은 인증 없이 접근 가능" 으로 명시

| 상태 | 조건 | 화면 처리 | API 응답 |
|------|------|-----------|----------|
| `unauthorized` | 미로그인 | | 401 |
| `forbidden` | 로그인됨 + 권한 없음 | | 403 |
| `expired` | 세션/토큰 만료 | | 401 + code |

---

## Layer 3. 입력·인터랙션 상태

> 해당 없음 시 "N/A — 이 화면에 사용자 입력 없음" 으로 명시

| 상태 | 조건 | 화면 처리 |
|------|------|-----------|
| `pristine` | 입력 전 | |
| `dirty` | 입력 시작 | |
| `validating` | 서버 검증 중 | |
| `valid` | 검증 통과 | |
| `invalid` | 검증 실패 | |
| `submitting` | 제출 중 | |
| `submitted:success` | 제출 성공 | |
| `submitted:error` | 제출 실패 | |

> 중복 제출 방지 방법: (버튼 비활성화 / 디바운스 / 서버 멱등성)

---

## Layer 4. 비즈니스 특수 상태

> 해당 없음 시 "N/A" 로 명시
> WebSocket 사용 시 연결 상태 3종(connected/disconnected/reconnecting) 필수 포함

| 상태 | 조건 | 화면 처리 | API 응답 |
|------|------|-----------|----------|
| | | | |

---

## 상태 전이 (선택 — 상태 5개 이상 또는 비선형 흐름 시 작성)

```
(예: loading → success | error)
(예: success → loading (새로고침 시))
(예: error → loading (재시도 시))
```

---

## 구현 계획 (여러 PR로 나눌 경우)

| PR | 구현 상태 | 예상 시점 |
|----|-----------|-----------|
| PR 1 | `success` + `loading` | |
| PR 2 | `empty` + `error` | |
| PR 3 | Layer 2 (권한 분기) | |

---

## State Discovery 로그

> 개발 중 발견된 미정의 상태를 여기에 기록합니다.

| 발견일 | 상태 | 발견자 | 해결 |
|--------|------|--------|------|
| | | | |
```

---

## 5. State Discovery 코멘트 템플릿 (태스크에 붙이는 용도)

```md
## State Discovery
- **발견된 상태**: `상태명` (한 줄 설명)
- **조건**: 이 상태가 발생하는 조건
- **제안하는 화면 처리**: 
- **API 응답**: (필요 시)
- **영향**: FE만 | BE만 | FE+BE
- **cc**: @designer @pm @be-dev
```

---

## 6. 예외 PR 코멘트 템플릿

```md
## Exception
- **사유**: (2줄 이내)
- **후속 조치**: [이슈 링크](#) 에서 정상화 예정
- **기한**: YYYY-MM-DD (머지 후 2스프린트 이내)
- **누락 항목**: (VRT 미승인 / 스토리 미작성 / 스펙 미생성 등)
```
