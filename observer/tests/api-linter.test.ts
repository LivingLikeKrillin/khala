import { describe, it, expect } from 'vitest';
import { lintSpec } from '../src/api/spec-linter.js';
import type { OpenApiSpec } from '../src/api/types.js';

/**
 * 테스트용 최소 유효 스펙을 생성한다.
 */
function makeSpec(overrides: Partial<OpenApiSpec> = {}): OpenApiSpec {
  return {
    openapi: '3.0.3',
    info: { title: 'Test', version: '1.0.0' },
    paths: {},
    components: { schemas: {} },
    ...overrides,
  };
}

describe('api-linter (내장 엔진)', () => {
  it('올바른 스펙은 에러 0건이다', () => {
    const spec = makeSpec({
      components: {
        schemas: {
          User: {
            type: 'object',
            required: ['id', 'name'],
            properties: {
              id: { type: 'integer', format: 'int64', example: 1 },
              name: { type: 'string', example: 'John' },
            },
          },
        },
      },
    });

    const result = lintSpec(spec, 'api/openapi.json');

    expect(result.summary.errors).toBe(0);
  });

  it('type 누락 필드를 탐지한다 (field-type-required)', () => {
    const spec = makeSpec({
      components: {
        schemas: {
          User: {
            type: 'object',
            properties: {
              id: { type: 'integer' },
              name: {}, // type 누락
            },
          },
        },
      },
    });

    const result = lintSpec(spec, 'api/openapi.json');

    expect(result.violations.some((v) => v.ruleId === 'probe/field-type-required')).toBe(true);
  });

  it('$ref 필드는 type 없어도 위반이 아니다', () => {
    const spec = makeSpec({
      components: {
        schemas: {
          Order: {
            type: 'object',
            properties: {
              user: { $ref: '#/components/schemas/User' },
            },
          },
        },
      },
    });

    const result = lintSpec(spec, 'api/openapi.json');
    const fieldTypeViolations = result.violations.filter((v) => v.ruleId === 'probe/field-type-required');

    expect(fieldTypeViolations.length).toBe(0);
  });

  it('nullable 미표시 필드를 탐지한다 (nullable-explicit)', () => {
    const spec = makeSpec({
      components: {
        schemas: {
          User: {
            type: 'object',
            properties: {
              nickname: { type: 'string', example: null }, // null example인데 nullable 없음
            },
          },
        },
      },
    });

    const result = lintSpec(spec, 'api/openapi.json');

    expect(result.violations.some((v) => v.ruleId === 'probe/nullable-explicit')).toBe(true);
  });

  it('nullable + optional 동시 적용을 경고한다 (no-nullable-optional)', () => {
    const spec = makeSpec({
      components: {
        schemas: {
          User: {
            type: 'object',
            required: ['id'],
            properties: {
              id: { type: 'integer' },
              nickname: { type: 'string', nullable: true }, // nullable이면서 required 아님
            },
          },
        },
      },
    });

    const result = lintSpec(spec, 'api/openapi.json');

    expect(result.violations.some((v) => v.ruleId === 'probe/no-nullable-optional')).toBe(true);
  });

  it('4xx 응답에 ErrorResponse 미참조를 탐지한다 (error-response-schema)', () => {
    const spec = makeSpec({
      paths: {
        '/users': {
          post: {
            responses: {
              '200': { description: 'OK' },
              '400': {
                description: 'Bad Request',
                content: {
                  'application/json': {
                    schema: { $ref: '#/components/schemas/User' }, // ErrorResponse가 아님
                  },
                },
              },
            },
          },
        },
      },
    });

    const result = lintSpec(spec, 'api/openapi.json');

    expect(result.violations.some((v) => v.ruleId === 'probe/error-response-schema')).toBe(true);
  });

  it('ErrorResponse 참조 4xx 응답은 위반이 아니다', () => {
    const spec = makeSpec({
      paths: {
        '/users': {
          post: {
            responses: {
              '400': {
                description: 'Bad Request',
                content: {
                  'application/json': {
                    schema: { $ref: '#/components/schemas/ErrorResponse' },
                  },
                },
              },
            },
          },
        },
      },
    });

    const result = lintSpec(spec, 'api/openapi.json');
    const errorViolations = result.violations.filter((v) => v.ruleId === 'probe/error-response-schema');

    expect(errorViolations.length).toBe(0);
  });

  it('kebab-case 위반 경로를 탐지한다 (path-naming)', () => {
    const spec = makeSpec({
      paths: {
        '/getUserList': {
          get: { responses: { '200': { description: 'OK' } } },
        },
      },
    });

    const result = lintSpec(spec, 'api/openapi.json');

    expect(result.violations.some((v) => v.ruleId === 'probe/path-naming')).toBe(true);
  });

  it('kebab-case 경로는 위반이 아니다', () => {
    const spec = makeSpec({
      paths: {
        '/user-list': {
          get: { responses: { '200': { description: 'OK' } } },
        },
      },
    });

    const result = lintSpec(spec, 'api/openapi.json');
    const pathViolations = result.violations.filter((v) => v.ruleId === 'probe/path-naming');

    expect(pathViolations.length).toBe(0);
  });

  it('camelCase 위반 필드명을 탐지한다 (property-naming)', () => {
    const spec = makeSpec({
      components: {
        schemas: {
          User: {
            type: 'object',
            properties: {
              user_name: { type: 'string' }, // snake_case
            },
          },
        },
      },
    });

    const result = lintSpec(spec, 'api/openapi.json');

    expect(result.violations.some((v) => v.ruleId === 'probe/property-naming')).toBe(true);
  });

  it('날짜 필드에 example 누락을 탐지한다 (example-required)', () => {
    const spec = makeSpec({
      components: {
        schemas: {
          User: {
            type: 'object',
            properties: {
              createdAt: { type: 'string', format: 'date-time' }, // example 없음
            },
          },
        },
      },
    });

    const result = lintSpec(spec, 'api/openapi.json');

    expect(result.violations.some((v) => v.ruleId === 'probe/example-required')).toBe(true);
  });

  it('룰 비활성화(disableRules)가 동작한다', () => {
    const spec = makeSpec({
      components: {
        schemas: {
          User: {
            type: 'object',
            properties: {
              user_name: { type: 'string' },
            },
          },
        },
      },
    });

    const result = lintSpec(spec, 'api/openapi.json', {
      disableRules: ['probe/property-naming'],
    });

    expect(result.violations.some((v) => v.ruleId === 'probe/property-naming')).toBe(false);
  });

  it('심각도 오버라이드(ruleSeverity)가 동작한다', () => {
    const spec = makeSpec({
      components: {
        schemas: {
          User: {
            type: 'object',
            properties: {
              createdAt: { type: 'string', format: 'date-time' },
            },
          },
        },
      },
    });

    const result = lintSpec(spec, 'api/openapi.json', {
      ruleSeverity: { 'probe/example-required': 'error' },
    });

    const exampleViolation = result.violations.find((v) => v.ruleId === 'probe/example-required');
    expect(exampleViolation?.severity).toBe('error');
  });

  it('off 심각도로 룰을 비활성화한다', () => {
    const spec = makeSpec({
      components: {
        schemas: {
          User: {
            type: 'object',
            properties: {
              user_name: { type: 'string' },
            },
          },
        },
      },
    });

    const result = lintSpec(spec, 'api/openapi.json', {
      ruleSeverity: { 'probe/property-naming': 'off' },
    });

    expect(result.violations.some((v) => v.ruleId === 'probe/property-naming')).toBe(false);
  });
});
