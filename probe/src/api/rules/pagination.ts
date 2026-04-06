/**
 * probe/pagination-required 룰
 *
 * 배열 응답에 페이지네이션이 있는지 검사한다.
 * 200 응답의 schema가 array이거나, items를 포함하면 대상.
 *
 * 규정 근거: 규정 ② § 2.3.3
 */

import type { LintRule, OpenApiSpec, ApiLintViolation, SchemaObject } from '../types.js';

const METHODS = ['get'] as const; // GET만 대상
const PAGINATION_FIELDS = ['page', 'size', 'totalPages', 'totalElements', 'cursor', 'nextCursor', 'offset', 'limit', 'total'];

export const paginationRequiredRule: LintRule = {
  id: 'probe/pagination-required',
  defaultSeverity: 'warn',
  guidelineRef: '§ 2.3.3',
  description: '배열 응답에 페이지네이션 필수 (array responses must include pagination)',

  check(spec: OpenApiSpec): ApiLintViolation[] {
    const violations: ApiLintViolation[] = [];

    if (!spec.paths) return violations;

    for (const [pathKey, pathItem] of Object.entries(spec.paths)) {
      for (const method of METHODS) {
        const operation = pathItem[method];
        if (!operation?.responses) continue;

        const successResponse = operation.responses['200'];
        if (!successResponse?.content) continue;

        for (const [, mediaType] of Object.entries(successResponse.content)) {
          const schema = mediaType.schema;
          if (!schema) continue;

          const isArrayResponse = isArraySchema(schema, spec);

          if (isArrayResponse) {
            // 페이지네이션 필드가 있는지 확인
            const hasPagination = checkPaginationFields(schema, spec);
            if (!hasPagination) {
              violations.push({
                ruleId: 'probe/pagination-required',
                severity: this.defaultSeverity,
                path: `paths.${pathKey}.${method}.responses.200`,
                message: `배열 응답에 페이지네이션이 없습니다 (array response missing pagination)`,
                fix: `cursor/offset 기반 페이지네이션을 추가하세요`,
              });
            }
          }
        }
      }
    }

    return violations;
  },
};

/**
 * 스키마가 배열 응답인지 확인한다.
 */
function isArraySchema(schema: SchemaObject, spec: OpenApiSpec): boolean {
  // 직접 array type
  if (schema.type === 'array') return true;

  // object이면서 items 배열 프로퍼티가 있는 경우 (wrapper)
  if (schema.type === 'object' && schema.properties) {
    const hasArrayProp = Object.values(schema.properties).some(
      (prop) => prop.type === 'array',
    );
    if (hasArrayProp) return false; // wrapper는 이미 pagination 가능
  }

  // $ref인 경우 resolve
  if (schema.$ref) {
    const resolved = resolveRef(schema.$ref, spec);
    if (resolved) return isArraySchema(resolved, spec);
  }

  return false;
}

/**
 * 페이지네이션 관련 필드가 있는지 확인한다.
 */
function checkPaginationFields(schema: SchemaObject, spec: OpenApiSpec): boolean {
  // wrapper object의 properties에서 페이지네이션 필드 확인
  if (schema.properties) {
    const propNames = Object.keys(schema.properties);
    return propNames.some((name) => PAGINATION_FIELDS.includes(name));
  }

  // $ref인 경우 resolve
  if (schema.$ref) {
    const resolved = resolveRef(schema.$ref, spec);
    if (resolved) return checkPaginationFields(resolved, spec);
  }

  return false;
}

/**
 * $ref를 resolve한다. 간단한 내부 참조만 지원.
 */
function resolveRef(ref: string, spec: OpenApiSpec): SchemaObject | undefined {
  const match = ref.match(/^#\/components\/schemas\/(.+)$/);
  if (match?.[1]) {
    return spec.components?.schemas?.[match[1]];
  }
  return undefined;
}
