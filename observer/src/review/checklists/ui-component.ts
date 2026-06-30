/**
 * ui-component PR 타입 체크리스트
 *
 * 규정 문서: docs/probe-v0.2-scope.md § 3.3
 */

import type { ChecklistItem } from '../types.js';

export const uiComponentChecklist: ChecklistItem[] = [
  // 필수
  {
    id: 'uc-story',
    description: '스토리 파일이 존재함 (story file exists)',
    automatable: true,
    guidelineRef: '규정 ③',
    priority: 'required',
  },
  {
    id: 'uc-variants',
    description: '주요 variant/상태가 스토리에 포함됨 (major variants included in stories)',
    automatable: false,
    priority: 'required',
  },
  // 권장
  {
    id: 'uc-a11y',
    description: '접근성 고려: 키보드 네비게이션, aria 속성 (accessibility: keyboard nav, aria)',
    automatable: false,
    priority: 'recommended',
  },
];
