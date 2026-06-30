/**
 * api-change PR 타입 체크리스트
 *
 * 규정 문서: docs/probe-v0.2-scope.md § 3.3
 */

import type { ChecklistItem } from '../types.js';

export const apiChangeChecklist: ChecklistItem[] = [
  // 필수
  {
    id: 'ac-spec-auto-generated',
    description: 'API 스펙이 코드에서 자동 생성됨 (API spec auto-generated from code)',
    automatable: false,
    guidelineRef: '규정 ② § 1.1',
    priority: 'required',
  },
  {
    id: 'ac-nullable-required',
    description: 'nullable/required 정확히 표시됨 (nullable/required correctly marked)',
    automatable: false,
    guidelineRef: '규정 ② § 2.3.1',
    priority: 'required',
  },
  {
    id: 'ac-error-response',
    description: '에러 응답이 ErrorResponse 스키마를 따름 (error responses follow ErrorResponse)',
    automatable: false,
    guidelineRef: '규정 ② § 2.3.2',
    priority: 'required',
  },
  {
    id: 'ac-breaking-agreement',
    description: '(breaking 시) FE와 사전 합의 완료 (breaking: agreed with FE)',
    automatable: false,
    guidelineRef: '규정 ② § 4.3',
    priority: 'required',
  },
  {
    id: 'ac-migration-guide',
    description: '(breaking 시) 마이그레이션 가이드 포함 (breaking: migration guide included)',
    automatable: false,
    guidelineRef: '규정 ② § 4.5',
    priority: 'required',
  },
  // 권장
  {
    id: 'ac-pr-label',
    description: 'PR 라벨: api:additive | api:breaking | api:deprecation',
    automatable: true,
    priority: 'recommended',
  },
  {
    id: 'ac-fe-impact',
    description: '영향받는 FE 코드/화면 목록 기재 (affected FE code/screens listed)',
    automatable: false,
    priority: 'recommended',
  },
];
