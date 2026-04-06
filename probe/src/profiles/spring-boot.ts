/**
 * Spring Boot 플랫폼 프로파일
 *
 * Spring Boot에서 하나의 논리적 변경이 통상 어떤 파일 패턴으로 나타나는지 정의.
 * 규정 문서: docs/probe-v0.1-scope.md § 2.2
 */

import type { PlatformProfile } from './types.js';

export const springBootProfile: PlatformProfile = {
  name: 'spring-boot',

  fileRoles: [
    { pattern: '**/entity/**', role: 'entity' },
    { pattern: '**/repository/**', role: 'repository' },
    { pattern: '**/service/**', role: 'service' },
    { pattern: '**/controller/**', role: 'controller' },
    { pattern: '**/dto/**', role: 'dto' },
    { pattern: '**/config/**', role: 'config' },
    { pattern: '**/exception/**', role: 'exception' },
    { pattern: '**/mapper/**', role: 'mapper' },
    { pattern: '*test*/**', role: 'test' },
    { pattern: '**/resources/db/migration/**', role: 'migration' },
    { pattern: '**/resources/application*', role: 'config' },
  ],

  cohesionGroups: [
    {
      name: 'domain-crud',
      description: '도메인 엔티티 CRUD (정상적인 단일 PR)',
      roles: ['entity', 'repository', 'service', 'controller', 'dto', 'mapper', 'exception', 'test'],
      cohesionKey: 'domainName',
      maxFiles: 15,
    },
    {
      name: 'config-change',
      description: '설정 변경',
      roles: ['config'],
      cohesionKey: 'configGroup',
      maxFiles: 5,
    },
    {
      name: 'migration',
      description: 'DB 마이그레이션',
      roles: ['migration', 'entity', 'repository'],
      cohesionKey: 'migrationGroup',
      maxFiles: 10,
    },
  ],

  thresholds: {
    maxFilesPerPr: 20,
    maxDiffLinesPerPr: 800,
    maxCohesionGroups: 2,
    mixedConcerns: [
      { roles: ['migration', 'controller'], reason: 'DB 마이그레이션과 API 변경은 분리하세요 (Separate DB migration from API changes)' },
      { roles: ['config', 'service'], reason: '설정 변경과 비즈니스 로직 변경은 분리하세요 (Separate config from business logic)' },
    ],
  },
};
