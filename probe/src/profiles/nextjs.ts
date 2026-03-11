/**
 * Next.js 플랫폼 프로파일
 *
 * Next.js에서 하나의 논리적 변경이 통상 어떤 파일 패턴으로 나타나는지 정의.
 * 규정 문서: docs/karax-v0.1-scope.md § 2.3
 */

import type { PlatformProfile } from './types.js';

export const nextjsProfile: PlatformProfile = {
  name: 'nextjs',

  fileRoles: [
    { pattern: 'app/**/page.tsx', role: 'page' },
    { pattern: 'app/**/page.ts', role: 'page' },
    { pattern: 'app/**/layout.tsx', role: 'layout' },
    { pattern: 'app/**/layout.ts', role: 'layout' },
    { pattern: 'app/**/loading.tsx', role: 'loading' },
    { pattern: 'app/**/error.tsx', role: 'error' },
    { pattern: 'app/api/**', role: 'api-route' },
    { pattern: 'components/**', role: 'component' },
    { pattern: 'lib/**', role: 'lib' },
    { pattern: 'hooks/**', role: 'hook' },
    { pattern: 'styles/**', role: 'style' },
    { pattern: '**/*.stories.*', role: 'story' },
    { pattern: '**/*.test.*', role: 'test' },
    { pattern: '**/middleware.*', role: 'middleware' },
  ],

  cohesionGroups: [
    {
      name: 'page-feature',
      description: '페이지 단위 기능 (page + 전용 component + hook)',
      roles: ['page', 'layout', 'loading', 'error', 'component', 'hook', 'style', 'story', 'test'],
      cohesionKey: 'routeSegment',
      maxFiles: 12,
    },
    {
      name: 'shared-component',
      description: '공유 컴포넌트 변경',
      roles: ['component', 'story', 'test', 'style'],
      cohesionKey: 'componentName',
      maxFiles: 6,
    },
    {
      name: 'api-route',
      description: 'API 라우트',
      roles: ['api-route', 'lib', 'test'],
      cohesionKey: 'apiSegment',
      maxFiles: 5,
    },
  ],

  thresholds: {
    maxFilesPerPr: 15,
    maxDiffLinesPerPr: 600,
    maxCohesionGroups: 2,
    mixedConcerns: [
      { roles: ['api-route', 'page'], reason: 'API 라우트와 페이지 UI 변경은 분리를 권장합니다 (Separate API routes from page UI)' },
      { roles: ['middleware', 'component'], reason: '인증/미들웨어와 UI 컴포넌트는 분리하세요 (Separate middleware from UI components)' },
      { roles: ['lib', 'page'], reason: '공유 라이브러리 변경과 페이지 변경은 분리를 권장합니다 (Separate shared libs from page changes)' },
    ],
  },
};
