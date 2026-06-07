/**
 * React SPA 플랫폼 프로파일
 *
 * React SPA에서 하나의 논리적 변경이 통상 어떤 파일 패턴으로 나타나는지 정의.
 * 규정 문서: docs/probe-v0.1-scope.md § 2.4
 */

import type { PlatformProfile } from './types.js';

export const reactSpaProfile: PlatformProfile = {
  name: 'react-spa',

  fileRoles: [
    { pattern: 'src/pages/**', role: 'page' },
    { pattern: 'src/components/**', role: 'component' },
    { pattern: 'src/hooks/**', role: 'hook' },
    { pattern: 'src/api/**', role: 'api-client' },
    { pattern: 'src/store/**', role: 'store' },
    { pattern: 'src/utils/**', role: 'util' },
    { pattern: 'src/styles/**', role: 'style' },
    { pattern: 'src/design-tokens/**', role: 'token' },
    { pattern: '**/*.stories.*', role: 'story' },
    { pattern: '**/*.test.*', role: 'test' },
  ],

  cohesionGroups: [
    {
      name: 'feature',
      description: '기능 단위 (page + components + hook + store)',
      roles: ['page', 'component', 'hook', 'store', 'style', 'story', 'test'],
      cohesionKey: 'featureName',
      maxFiles: 12,
    },
    {
      name: 'design-system',
      description: '디자인 시스템 변경 (토큰 + 컴포넌트 + 스토리)',
      roles: ['token', 'component', 'story', 'style'],
      cohesionKey: 'designGroup',
      maxFiles: 10,
    },
    {
      name: 'api-layer',
      description: 'API 클라이언트 변경',
      roles: ['api-client', 'test'],
      cohesionKey: 'apiGroup',
      maxFiles: 5,
    },
  ],

  thresholds: {
    maxFilesPerPr: 15,
    maxDiffLinesPerPr: 500,
    maxCohesionGroups: 2,
    mixedConcerns: [
      { roles: ['token', 'page'], reason: '토큰 변경과 화면 변경은 분리하세요 — Additive-first (Separate token from page changes)' },
      { roles: ['store', 'component'], reason: '상태 관리 변경과 UI 변경은 분리를 권장합니다 (Separate store from UI components)' },
    ],
  },
};
