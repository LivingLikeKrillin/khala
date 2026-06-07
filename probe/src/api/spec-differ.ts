/**
 * 내장 경량 diff 엔진
 *
 * 두 OpenAPI 스펙(base, head)을 비교하여 변경 사항을 분류한다.
 * oasdiff가 없어도 동작하는 폴백 엔진.
 *
 * 탐지하는 breaking 변경:
 * - 엔드포인트 삭제
 * - 응답 필드 삭제
 * - 요청 required 필드 추가
 * - 필드 타입 변경
 * - enum 값 제거
 *
 * 규정 문서: docs/probe-v0.2-scope.md § 3.2
 */

import type {
  OpenApiSpec,
  ApiDiffResult,
  ApiChange,
  PathItem,
  OperationObject,
  SchemaObject,
} from './types.js';

const METHODS = ['get', 'post', 'put', 'patch', 'delete'] as const;

/**
 * 두 OpenAPI 스펙을 비교한다.
 *
 * @param base 기준 스펙
 * @param head 현재 스펙
 * @returns diff 결과
 */
export function diffSpecs(base: OpenApiSpec, head: OpenApiSpec): ApiDiffResult {
  const changes: ApiChange[] = [];

  const basePaths = base.paths ?? {};
  const headPaths = head.paths ?? {};

  const allPaths = new Set([...Object.keys(basePaths), ...Object.keys(headPaths)]);

  for (const pathKey of allPaths) {
    const basePath = basePaths[pathKey];
    const headPath = headPaths[pathKey];

    if (!basePath && headPath) {
      // 새 경로 추가
      addNewPathChanges(pathKey, headPath, changes);
    } else if (basePath && !headPath) {
      // 경로 삭제
      addRemovedPathChanges(pathKey, basePath, changes);
    } else if (basePath && headPath) {
      // 경로 수정
      diffPathItem(pathKey, basePath, headPath, base, head, changes);
    }
  }

  const summary = summarizeChanges(changes);
  const suggestedLabel = determineSuggestedLabel(changes);

  return { summary, changes, suggestedLabel };
}

/**
 * 새 경로의 오퍼레이션을 추가 변경으로 등록한다.
 */
function addNewPathChanges(pathKey: string, pathItem: PathItem, changes: ApiChange[]): void {
  for (const method of METHODS) {
    const operation = pathItem[method] as OperationObject | undefined;
    if (!operation) continue;

    changes.push({
      endpoint: `${method.toUpperCase()} ${pathKey}`,
      type: 'added',
      breaking: false,
      details: ['새 엔드포인트 추가 (new endpoint added)'],
    });
  }
}

/**
 * 삭제된 경로의 오퍼레이션을 삭제 변경으로 등록한다.
 */
function addRemovedPathChanges(pathKey: string, pathItem: PathItem, changes: ApiChange[]): void {
  for (const method of METHODS) {
    const operation = pathItem[method] as OperationObject | undefined;
    if (!operation) continue;

    changes.push({
      endpoint: `${method.toUpperCase()} ${pathKey}`,
      type: 'removed',
      breaking: true,
      details: ['엔드포인트 삭제 — 기존 클라이언트 실패 가능 (endpoint removed — existing clients may fail)'],
    });
  }
}

/**
 * 같은 경로의 두 버전을 비교한다.
 */
function diffPathItem(
  pathKey: string,
  basePath: PathItem,
  headPath: PathItem,
  baseSpec: OpenApiSpec,
  headSpec: OpenApiSpec,
  changes: ApiChange[],
): void {
  for (const method of METHODS) {
    const baseOp = basePath[method] as OperationObject | undefined;
    const headOp = headPath[method] as OperationObject | undefined;

    const endpoint = `${method.toUpperCase()} ${pathKey}`;

    if (!baseOp && headOp) {
      changes.push({
        endpoint,
        type: 'added',
        breaking: false,
        details: ['새 오퍼레이션 추가 (new operation added)'],
      });
    } else if (baseOp && !headOp) {
      changes.push({
        endpoint,
        type: 'removed',
        breaking: true,
        details: ['오퍼레이션 삭제 (operation removed)'],
      });
    } else if (baseOp && headOp) {
      // deprecated 변경 감지
      if (!baseOp.deprecated && headOp.deprecated) {
        changes.push({
          endpoint,
          type: 'deprecated',
          breaking: false,
          details: ['deprecated 표시 추가 (marked as deprecated)'],
        });
        continue;
      }

      // 상세 diff
      const details: string[] = [];
      let breaking = false;

      // 요청 body diff
      const reqBreaking = diffRequestBody(baseOp, headOp, baseSpec, headSpec, details);
      if (reqBreaking) breaking = true;

      // 응답 body diff
      const resBreaking = diffResponses(baseOp, headOp, baseSpec, headSpec, details);
      if (resBreaking) breaking = true;

      // 파라미터 diff
      const paramBreaking = diffParameters(baseOp, headOp, details);
      if (paramBreaking) breaking = true;

      if (details.length > 0) {
        changes.push({
          endpoint,
          type: 'modified',
          breaking,
          details,
        });
      }
    }
  }
}

/**
 * 요청 body를 비교한다.
 */
function diffRequestBody(
  baseOp: OperationObject,
  headOp: OperationObject,
  baseSpec: OpenApiSpec,
  headSpec: OpenApiSpec,
  details: string[],
): boolean {
  let breaking = false;

  const baseSchema = getRequestSchema(baseOp, baseSpec);
  const headSchema = getRequestSchema(headOp, headSpec);

  if (!baseSchema && !headSchema) return false;

  if (!baseSchema && headSchema) {
    if (headOp.requestBody?.required) {
      details.push('필수 요청 body 추가 — breaking (required request body added)');
      breaking = true;
    } else {
      details.push('요청 body 추가 (optional) (request body added)');
    }
    return breaking;
  }

  if (baseSchema && headSchema) {
    // required 필드 추가 확인
    const baseRequired = new Set(baseSchema.required ?? []);
    const headRequired = new Set(headSchema.required ?? []);

    for (const field of headRequired) {
      if (!baseRequired.has(field)) {
        details.push(`요청: '${field}' 필드가 required로 추가됨 — breaking (request: '${field}' added as required)`);
        breaking = true;
      }
    }

    // 필드 타입 변경 확인
    if (baseSchema.properties && headSchema.properties) {
      breaking = diffSchemaProperties(baseSchema, headSchema, '요청', details) || breaking;
    }
  }

  return breaking;
}

/**
 * 응답을 비교한다.
 */
function diffResponses(
  baseOp: OperationObject,
  headOp: OperationObject,
  baseSpec: OpenApiSpec,
  headSpec: OpenApiSpec,
  details: string[],
): boolean {
  let breaking = false;

  const baseResponses = baseOp.responses ?? {};
  const headResponses = headOp.responses ?? {};

  // 200 응답 스키마 비교
  const baseSchema = getResponseSchema(baseResponses['200'], baseSpec);
  const headSchema = getResponseSchema(headResponses['200'], headSpec);

  if (baseSchema && headSchema) {
    if (baseSchema.properties && headSchema.properties) {
      // 필드 삭제 확인
      for (const field of Object.keys(baseSchema.properties)) {
        if (!(field in headSchema.properties)) {
          details.push(`응답: '${field}' 필드 삭제 — breaking (response: '${field}' field removed)`);
          breaking = true;
        }
      }

      // 필드 추가 확인
      for (const field of Object.keys(headSchema.properties)) {
        if (baseSchema.properties && !(field in baseSchema.properties)) {
          const isNullable = headSchema.properties[field]?.nullable;
          const isRequired = headSchema.required?.includes(field);
          details.push(`응답: '${field}' 필드 추가${isNullable ? ' (nullable)' : ''}${isRequired ? '' : ' (optional)'} (response: '${field}' field added)`);
        }
      }

      // 타입 변경 확인
      breaking = diffSchemaProperties(baseSchema, headSchema, '응답', details) || breaking;
    }
  }

  return breaking;
}

/**
 * 파라미터를 비교한다.
 */
function diffParameters(
  baseOp: OperationObject,
  headOp: OperationObject,
  details: string[],
): boolean {
  let breaking = false;

  const baseParams = baseOp.parameters ?? [];
  const headParams = headOp.parameters ?? [];

  const baseParamMap = new Map(baseParams.map((p) => [`${p.in}:${p.name}`, p]));
  const headParamMap = new Map(headParams.map((p) => [`${p.in}:${p.name}`, p]));

  // 새 required 파라미터 추가
  for (const [key, param] of headParamMap) {
    if (!baseParamMap.has(key) && param.required) {
      details.push(`필수 파라미터 '${param.name}' 추가 — breaking (required parameter '${param.name}' added)`);
      breaking = true;
    }
  }

  // 파라미터 삭제
  for (const [key, param] of baseParamMap) {
    if (!headParamMap.has(key)) {
      details.push(`파라미터 '${param.name}' 삭제 — breaking (parameter '${param.name}' removed)`);
      breaking = true;
    }
  }

  return breaking;
}

/**
 * 스키마 properties의 타입 변경/enum 변경을 비교한다.
 */
function diffSchemaProperties(
  baseSchema: SchemaObject,
  headSchema: SchemaObject,
  context: string,
  details: string[],
): boolean {
  let breaking = false;

  if (!baseSchema.properties || !headSchema.properties) return false;

  for (const [field, baseProp] of Object.entries(baseSchema.properties)) {
    const headProp = headSchema.properties[field];
    if (!headProp) continue;

    // 타입 변경
    if (baseProp.type && headProp.type && baseProp.type !== headProp.type) {
      details.push(`${context}: '${field}' 타입 변경 ${baseProp.type} → ${headProp.type} — breaking (${context}: '${field}' type changed)`);
      breaking = true;
    }

    // enum 값 제거
    if (baseProp.enum && headProp.enum) {
      const removed = baseProp.enum.filter((v) => !headProp.enum!.includes(v));
      if (removed.length > 0) {
        details.push(`${context}: '${field}' enum 값 제거 [${removed.join(', ')}] — breaking (${context}: '${field}' enum values removed)`);
        breaking = true;
      }
    }
  }

  return breaking;
}

/**
 * 요청 body에서 스키마를 추출한다.
 */
function getRequestSchema(op: OperationObject, spec: OpenApiSpec): SchemaObject | undefined {
  const content = op.requestBody?.content;
  if (!content) return undefined;

  const mediaType = content['application/json'] ?? Object.values(content)[0];
  return resolveSchema(mediaType?.schema, spec);
}

/**
 * 응답에서 스키마를 추출한다.
 */
function getResponseSchema(
  response: { content?: Record<string, { schema?: SchemaObject }> } | undefined,
  spec: OpenApiSpec,
): SchemaObject | undefined {
  if (!response?.content) return undefined;

  const mediaType = response.content['application/json'] ?? Object.values(response.content)[0];
  return resolveSchema(mediaType?.schema, spec);
}

/**
 * $ref를 resolve한다.
 */
function resolveSchema(schema: SchemaObject | undefined, spec: OpenApiSpec): SchemaObject | undefined {
  if (!schema) return undefined;

  if (schema.$ref) {
    const match = schema.$ref.match(/^#\/components\/schemas\/(.+)$/);
    if (match?.[1]) {
      return spec.components?.schemas?.[match[1]];
    }
  }

  return schema;
}

/**
 * 변경 요약을 생성한다.
 */
function summarizeChanges(changes: ApiChange[]): ApiDiffResult['summary'] {
  return {
    added: changes.filter((c) => c.type === 'added').length,
    modified: changes.filter((c) => c.type === 'modified').length,
    removed: changes.filter((c) => c.type === 'removed').length,
    deprecated: changes.filter((c) => c.type === 'deprecated').length,
    hasBreaking: changes.some((c) => c.breaking),
  };
}

/**
 * 권장 PR 라벨을 결정한다.
 */
function determineSuggestedLabel(changes: ApiChange[]): ApiDiffResult['suggestedLabel'] {
  if (changes.length === 0) return null;

  if (changes.some((c) => c.breaking)) return 'api:breaking';
  if (changes.every((c) => c.type === 'deprecated')) return 'api:deprecation';
  return 'api:additive';
}
