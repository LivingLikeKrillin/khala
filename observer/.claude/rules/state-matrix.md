---
description: "State Matrix 관련 규칙. 화면/기능 개발 시 참조."
---

# State Matrix 규칙

## 필수 상태 (모든 비동기 화면)
어떤 화면이든 아래 4개 상태는 반드시 정의해야 한다.
1. `loading` — 데이터 요청 중
2. `empty` — 데이터 0건
3. `success` — 정상 수신
4. `error` — 요청 실패 (최소 1종)

## "화면 처리" 작성 기준
- "적절히 처리", "에러 표시" 같은 모호한 표현 금지
- 구체적으로: "스켈레톤 UI (카드 3개 플레이스홀더)", "인라인 에러 메시지 + 재시도 버튼"

## 개발 중 새 상태 발견 시
1. State Matrix에 상태 추가 (상태 이름 + 조건만이라도)
2. 관련 역할(디자인/FE/BE)에 24시간 이내 공유
3. 태스크 코멘트에 State Discovery 기록

## 상세 규정
docs/guidelines/state-matrix-guidelines.md 참조
