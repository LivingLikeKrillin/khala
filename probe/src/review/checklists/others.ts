/**
 * config-change, db-migration, test-only, docs-only, design-system, general 체크리스트
 *
 * 규정 문서: docs/karax-v0.2-scope.md § 3.3
 */

import type { ChecklistItem } from '../types.js';

export const configChangeChecklist: ChecklistItem[] = [
  {
    id: 'cc-env-docs',
    description: '환경 변수 변경 시 문서 업데이트 (env variable changes documented)',
    automatable: false,
    priority: 'required',
  },
  {
    id: 'cc-rollback',
    description: '롤백 가능 여부 확인 (rollback plan verified)',
    automatable: false,
    priority: 'recommended',
  },
];

export const dbMigrationChecklist: ChecklistItem[] = [
  {
    id: 'dm-reversible',
    description: '마이그레이션이 되돌릴 수 있는지 확인 (migration is reversible)',
    automatable: false,
    priority: 'required',
  },
  {
    id: 'dm-data-safety',
    description: '기존 데이터 손실 없음 확인 (no data loss verified)',
    automatable: false,
    priority: 'required',
  },
  {
    id: 'dm-index',
    description: '대용량 테이블 인덱스 변경 시 영향 분석 (index change impact analyzed)',
    automatable: false,
    priority: 'recommended',
  },
];

export const testOnlyChecklist: ChecklistItem[] = [
  {
    id: 'to-coverage',
    description: '테스트가 실제 로직을 검증하는지 확인 (tests verify actual logic)',
    automatable: false,
    priority: 'required',
  },
];

export const docsOnlyChecklist: ChecklistItem[] = [
  {
    id: 'do-accuracy',
    description: '문서 내용이 현재 코드와 일치하는지 확인 (docs match current code)',
    automatable: false,
    priority: 'required',
  },
];

export const designSystemChecklist: ChecklistItem[] = [
  {
    id: 'ds-token-consistency',
    description: '토큰 변경이 기존 컴포넌트에 미치는 영향 확인 (token change impact verified)',
    automatable: false,
    priority: 'required',
  },
  {
    id: 'ds-story',
    description: '변경된 컴포넌트의 스토리가 업데이트됨 (stories updated)',
    automatable: true,
    priority: 'recommended',
  },
];

export const generalChecklist: ChecklistItem[] = [
  {
    id: 'gen-test',
    description: '변경에 대한 테스트가 있는지 확인 (tests exist for changes)',
    automatable: true,
    priority: 'recommended',
  },
];
