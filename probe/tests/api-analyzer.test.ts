import { describe, it, expect } from 'vitest';
import { diffSpecs } from '../src/api/spec-differ.js';
import type { OpenApiSpec } from '../src/api/types.js';

function makeSpec(overrides: Partial<OpenApiSpec> = {}): OpenApiSpec {
  return {
    openapi: '3.0.3',
    info: { title: 'Test', version: '1.0.0' },
    paths: {},
    components: { schemas: {} },
    ...overrides,
  };
}

describe('api-analyzer (내장 diff 엔진)', () => {
  it('엔드포인트 추가는 additive이다', () => {
    const base = makeSpec();
    const head = makeSpec({
      paths: {
        '/users': {
          get: { responses: { '200': { description: 'OK' } } },
        },
      },
    });

    const result = diffSpecs(base, head);

    expect(result.summary.added).toBe(1);
    expect(result.summary.hasBreaking).toBe(false);
    expect(result.suggestedLabel).toBe('api:additive');
  });

  it('엔드포인트 삭제는 breaking이다', () => {
    const base = makeSpec({
      paths: {
        '/users': {
          get: { responses: { '200': { description: 'OK' } } },
        },
      },
    });
    const head = makeSpec();

    const result = diffSpecs(base, head);

    expect(result.summary.removed).toBe(1);
    expect(result.summary.hasBreaking).toBe(true);
    expect(result.suggestedLabel).toBe('api:breaking');
  });

  it('optional 필드 추가는 additive이다', () => {
    const base = makeSpec({
      paths: {
        '/users': {
          get: {
            responses: {
              '200': {
                description: 'OK',
                content: {
                  'application/json': {
                    schema: {
                      type: 'object',
                      properties: {
                        id: { type: 'integer' },
                      },
                    },
                  },
                },
              },
            },
          },
        },
      },
    });

    const head = makeSpec({
      paths: {
        '/users': {
          get: {
            responses: {
              '200': {
                description: 'OK',
                content: {
                  'application/json': {
                    schema: {
                      type: 'object',
                      properties: {
                        id: { type: 'integer' },
                        name: { type: 'string' }, // 새 필드
                      },
                    },
                  },
                },
              },
            },
          },
        },
      },
    });

    const result = diffSpecs(base, head);

    expect(result.summary.hasBreaking).toBe(false);
    const change = result.changes.find((c) => c.endpoint === 'GET /users');
    expect(change?.details.some((d) => d.includes("'name'") && d.includes('추가'))).toBe(true);
  });

  it('required 필드 추가 (요청)는 breaking이다', () => {
    const base = makeSpec({
      paths: {
        '/users': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: {
                    type: 'object',
                    required: ['name'],
                    properties: {
                      name: { type: 'string' },
                    },
                  },
                },
              },
            },
            responses: { '201': { description: 'Created' } },
          },
        },
      },
    });

    const head = makeSpec({
      paths: {
        '/users': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: {
                    type: 'object',
                    required: ['name', 'email'], // email 추가
                    properties: {
                      name: { type: 'string' },
                      email: { type: 'string' },
                    },
                  },
                },
              },
            },
            responses: { '201': { description: 'Created' } },
          },
        },
      },
    });

    const result = diffSpecs(base, head);

    expect(result.summary.hasBreaking).toBe(true);
    expect(result.suggestedLabel).toBe('api:breaking');
  });

  it('필드 타입 변경은 breaking이다', () => {
    const base = makeSpec({
      paths: {
        '/users': {
          get: {
            responses: {
              '200': {
                description: 'OK',
                content: {
                  'application/json': {
                    schema: {
                      type: 'object',
                      properties: {
                        age: { type: 'integer' },
                      },
                    },
                  },
                },
              },
            },
          },
        },
      },
    });

    const head = makeSpec({
      paths: {
        '/users': {
          get: {
            responses: {
              '200': {
                description: 'OK',
                content: {
                  'application/json': {
                    schema: {
                      type: 'object',
                      properties: {
                        age: { type: 'string' }, // integer → string
                      },
                    },
                  },
                },
              },
            },
          },
        },
      },
    });

    const result = diffSpecs(base, head);

    expect(result.summary.hasBreaking).toBe(true);
  });

  it('enum 값 제거는 breaking이다', () => {
    const base = makeSpec({
      paths: {
        '/users': {
          get: {
            responses: {
              '200': {
                description: 'OK',
                content: {
                  'application/json': {
                    schema: {
                      type: 'object',
                      properties: {
                        status: { type: 'string', enum: ['active', 'inactive', 'pending'] },
                      },
                    },
                  },
                },
              },
            },
          },
        },
      },
    });

    const head = makeSpec({
      paths: {
        '/users': {
          get: {
            responses: {
              '200': {
                description: 'OK',
                content: {
                  'application/json': {
                    schema: {
                      type: 'object',
                      properties: {
                        status: { type: 'string', enum: ['active', 'inactive'] }, // pending 제거
                      },
                    },
                  },
                },
              },
            },
          },
        },
      },
    });

    const result = diffSpecs(base, head);

    expect(result.summary.hasBreaking).toBe(true);
  });

  it('deprecated 추가는 deprecation이다', () => {
    const base = makeSpec({
      paths: {
        '/users': {
          get: { responses: { '200': { description: 'OK' } } },
        },
      },
    });

    const head = makeSpec({
      paths: {
        '/users': {
          get: { deprecated: true, responses: { '200': { description: 'OK' } } },
        },
      },
    });

    const result = diffSpecs(base, head);

    expect(result.summary.deprecated).toBe(1);
    expect(result.suggestedLabel).toBe('api:deprecation');
  });

  it('변경 없으면 빈 결과를 반환한다', () => {
    const spec = makeSpec({
      paths: {
        '/users': {
          get: { responses: { '200': { description: 'OK' } } },
        },
      },
    });

    const result = diffSpecs(spec, spec);

    expect(result.changes.length).toBe(0);
    expect(result.suggestedLabel).toBeNull();
  });

  it('breaking + additive 혼재 시 hasBreaking이 true이다', () => {
    const base = makeSpec({
      paths: {
        '/users': {
          get: { responses: { '200': { description: 'OK' } } },
        },
      },
    });

    const head = makeSpec({
      paths: {
        '/orders': { // 새 경로 추가 (additive)
          get: { responses: { '200': { description: 'OK' } } },
        },
        // /users 삭제 (breaking)
      },
    });

    const result = diffSpecs(base, head);

    expect(result.summary.hasBreaking).toBe(true);
    expect(result.summary.added).toBeGreaterThan(0);
    expect(result.suggestedLabel).toBe('api:breaking');
  });

  it('응답 필드 삭제는 breaking이다', () => {
    const base = makeSpec({
      paths: {
        '/users': {
          get: {
            responses: {
              '200': {
                description: 'OK',
                content: {
                  'application/json': {
                    schema: {
                      type: 'object',
                      properties: {
                        id: { type: 'integer' },
                        name: { type: 'string' },
                      },
                    },
                  },
                },
              },
            },
          },
        },
      },
    });

    const head = makeSpec({
      paths: {
        '/users': {
          get: {
            responses: {
              '200': {
                description: 'OK',
                content: {
                  'application/json': {
                    schema: {
                      type: 'object',
                      properties: {
                        id: { type: 'integer' },
                        // name 삭제
                      },
                    },
                  },
                },
              },
            },
          },
        },
      },
    });

    const result = diffSpecs(base, head);

    expect(result.summary.hasBreaking).toBe(true);
  });
});
