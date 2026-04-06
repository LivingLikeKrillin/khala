/**
 * ui-feature PR 타입 체크리스트
 *
 * 규정 문서: docs/probe-v0.2-scope.md § 3.3
 */

import type { ChecklistItem } from '../types.js';

export const uiFeatureChecklist: ChecklistItem[] = [
  // 필수
  {
    id: 'uf-state-matrix',
    description: '4가지 필수 상태 구현: loading, empty, success, error (4 required states implemented)',
    automatable: false,
    guidelineRef: '규정 ① 필수 상태',
    priority: 'required',
  },
  {
    id: 'uf-error-ui',
    description: '에러 상태에 구체적 UI 명시 — "적절히 처리" 금지 (specific error UI defined)',
    automatable: false,
    guidelineRef: '규정 ① "적절히 처리" 금지',
    priority: 'required',
  },
  // 권장
  {
    id: 'uf-story',
    description: '스토리 파일이 존재함 (story file exists)',
    automatable: true,
    priority: 'recommended',
  },
  {
    id: 'uf-responsive',
    description: '반응형 레이아웃 확인 (responsive layout verified)',
    automatable: false,
    priority: 'recommended',
  },
];
