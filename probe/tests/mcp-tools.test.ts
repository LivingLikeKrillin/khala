import { describe, it, expect, vi, beforeEach } from 'vitest';
import { analyzeScope } from '../src/core/scope-analyzer.js';
import { springBootProfile } from '../src/profiles/spring-boot.js';
import { nextjsProfile } from '../src/profiles/nextjs.js';
import { lintSpec } from '../src/api/spec-linter.js';
import { diffSpecs } from '../src/api/spec-differ.js';
import { detectPrType } from '../src/review/pr-type-detector.js';
import { generateChecklist } from '../src/review/checklist-generator.js';
import { generateReviewChecklist } from '../src/core/review-checklist.js';
import type { OpenApiSpec } from '../src/api/types.js';

/**
 * MCP 도구 핸들러 테스트
 *
 * MCP 서버 자체(transport)는 테스트하지 않고,
 * 도구 핸들러가 호출하는 코어 함수의 동작을 검증한다.
 * (MCP 도구 = 코어 함수의 얇은 래퍼이므로)
 */

describe('MCP 도구 — analyzeScope', () => {
  it('파일 목록 직접 전달 시 ScopeAnalysisResult를 반환한다', () => {
    const files = [
      'src/main/kotlin/entity/User.kt',
      'src/main/kotlin/service/UserService.kt',
      'src/main/kotlin/controller/UserController.kt',
    ];

    const result = analyzeScope(files, springBootProfile, 100);

    expect(result.severity).toBe('ok');
    expect(result.totalFiles).toBe(3);
    expect(result.groups.length).toBeGreaterThan(0);
  });

  it('빈 파일 목록이면 ok를 반환한다', () => {
    const result = analyzeScope([], springBootProfile);

    expect(result.severity).toBe('ok');
    expect(result.totalFiles).toBe(0);
  });

  it('여러 관심사 혼재 시 warn/error를 반환한다', () => {
    const files = [
      'src/main/kotlin/entity/User.kt',
      'src/main/kotlin/entity/Order.kt',
      'src/main/kotlin/entity/Product.kt',
    ];

    const result = analyzeScope(files, springBootProfile, 100);

    expect(result.severity).not.toBe('ok');
    expect(result.groups.length).toBeGreaterThan(2);
  });
});

describe('MCP 도구 — lintApiSpec', () => {
  it('유효한 스펙의 린트 결과를 반환한다', () => {
    const spec: OpenApiSpec = {
      openapi: '3.0.3',
      info: { title: 'Test', version: '1.0.0' },
      paths: {},
      components: {
        schemas: {
          User: {
            type: 'object',
            required: ['id'],
            properties: {
              id: { type: 'integer', example: 1 },
              name: { type: 'string', example: 'John' },
            },
          },
        },
      },
    };

    const result = lintSpec(spec, 'api/openapi.json');

    expect(result.specPath).toBe('api/openapi.json');
    expect(result.summary).toBeDefined();
    expect(result.violations).toBeInstanceOf(Array);
  });

  it('위반이 있는 스펙의 violations을 반환한다', () => {
    const spec: OpenApiSpec = {
      openapi: '3.0.3',
      info: { title: 'Test', version: '1.0.0' },
      paths: {
        '/getUserList': {
          get: { responses: { '200': { description: 'OK' } } },
        },
      },
      components: { schemas: {} },
    };

    const result = lintSpec(spec, 'api/openapi.json');

    expect(result.violations.length).toBeGreaterThan(0);
    expect(result.violations.some((v) => v.ruleId === 'karax/path-naming')).toBe(true);
  });
});

describe('MCP 도구 — diffApiSpecs', () => {
  it('동일한 스펙이면 빈 변경 목록을 반환한다', () => {
    const spec: OpenApiSpec = {
      openapi: '3.0.3',
      info: { title: 'Test', version: '1.0.0' },
      paths: {
        '/users': {
          get: { responses: { '200': { description: 'OK' } } },
        },
      },
    };

    const result = diffSpecs(spec, spec);

    expect(result.changes.length).toBe(0);
    expect(result.suggestedLabel).toBeNull();
  });

  it('엔드포인트 추가를 감지한다', () => {
    const base: OpenApiSpec = {
      openapi: '3.0.3',
      info: { title: 'Test', version: '1.0.0' },
      paths: {},
    };
    const head: OpenApiSpec = {
      openapi: '3.0.3',
      info: { title: 'Test', version: '1.0.0' },
      paths: {
        '/users': {
          get: { responses: { '200': { description: 'OK' } } },
        },
      },
    };

    const result = diffSpecs(base, head);

    expect(result.summary.added).toBe(1);
    expect(result.suggestedLabel).toBe('api:additive');
  });
});

describe('MCP 도구 — reviewChecklist', () => {
  it('scope 분석 결과에서 체크리스트를 생성한다', () => {
    const files = [
      'src/main/kotlin/entity/User.kt',
      'src/main/kotlin/service/UserService.kt',
      'src/main/kotlin/controller/UserController.kt',
      'src/test/kotlin/service/UserServiceTest.kt',
    ];

    const scopeResult = analyzeScope(files, springBootProfile, 100);
    const checklist = generateReviewChecklist(scopeResult, files);

    expect(checklist.prType).toBe('domain-crud');
    expect(checklist.items.length).toBeGreaterThan(0);
    // 테스트 파일이 있으므로 자동 검증 통과
    const testVerified = checklist.autoVerified.find((v) => v.id === 'dc-service-test');
    expect(testVerified?.passed).toBe(true);
  });

  it('Next.js 페이지 변경은 ui-feature 체크리스트를 생성한다', () => {
    const files = [
      'app/dashboard/page.tsx',
      'app/dashboard/layout.tsx',
      'components/dashboard/StatsCard.tsx',
    ];

    const scopeResult = analyzeScope(files, nextjsProfile, 80);
    const checklist = generateReviewChecklist(scopeResult, files);

    expect(checklist.prType).toBe('ui-feature');
    // State Matrix 항목이 있는지 확인
    expect(checklist.items.some((i) => i.id === 'uf-state-matrix')).toBe(true);
  });
});

describe('MCP 도구 — detectPlatform', () => {
  it('프로파일이 올바른 구조를 가진다', () => {
    expect(springBootProfile.name).toBe('spring-boot');
    expect(springBootProfile.fileRoles.length).toBeGreaterThan(0);
    expect(springBootProfile.cohesionGroups.length).toBeGreaterThan(0);
    expect(springBootProfile.thresholds.maxFilesPerPr).toBeGreaterThan(0);
  });
});
