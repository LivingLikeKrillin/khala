---
description: "API 계약 관련 규칙. API 코드나 스펙 변경 시 참조."
paths:
  - "**/controller/**"
  - "**/api/**"
  - "**/route*"
  - "api/openapi*"
  - "api/asyncapi*"
---

# API 계약 규칙

## 스펙 품질 최소 기준 (Level 2)
- 모든 필드에 타입 명시
- required / optional 구분 정확
- nullable 필드에 `nullable: true` 명시
- nullable과 optional을 동시에 적용하지 않는다
- 모든 4xx/5xx 응답은 공통 ErrorResponse 스키마를 따른다
- 목록 API는 페이지네이션 방식 + 파라미터를 명시한다

## 변경 분류
- 새 엔드포인트 추가, optional 필드 추가 → 호환 (additive)
- 필드 타입 변경, required↔optional 변경, 구조 변경 → 비호환 (breaking)
- 엔드포인트 제거, 필드 제거 → 비호환 (breaking)

## breaking 변경 시
- FE와 사전 합의 필수
- 마이그레이션 가이드 포함 (before/after 예시)
- Deprecation 기간 없이 즉시 삭제 금지

## 상세 규정
docs/guidelines/api-contract-guidelines.md 참조
