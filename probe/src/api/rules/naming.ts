/**
 * karax/path-naming, karax/property-naming 룰
 *
 * - 엔드포인트 경로: kebab-case
 * - 스키마 필드명: camelCase
 *
 * 규정 근거: 규정 ② § 3.1
 */

import type { LintRule, OpenApiSpec, ApiLintViolation, SchemaObject } from '../types.js';

/** kebab-case 패턴: 소문자, 숫자, 하이픈만. 경로 변수({id})는 허용 */
const KEBAB_SEGMENT = /^[a-z0-9]+(-[a-z0-9]+)*$/;

/** camelCase 패턴 */
const CAMEL_CASE = /^[a-z][a-zA-Z0-9]*$/;

export const pathNamingRule: LintRule = {
  id: 'karax/path-naming',
  defaultSeverity: 'error',
  guidelineRef: '§ 3.1',
  description: '엔드포인트 kebab-case (endpoints must use kebab-case)',

  check(spec: OpenApiSpec): ApiLintViolation[] {
    const violations: ApiLintViolation[] = [];

    if (!spec.paths) return violations;

    for (const pathKey of Object.keys(spec.paths)) {
      const segments = pathKey.split('/').filter(Boolean);

      for (const segment of segments) {
        // 경로 변수({id}, {userId} 등)는 스킵
        if (segment.startsWith('{') && segment.endsWith('}')) continue;

        if (!KEBAB_SEGMENT.test(segment)) {
          violations.push({
            ruleId: 'karax/path-naming',
            severity: this.defaultSeverity,
            path: `paths.${pathKey}`,
            message: `경로 세그먼트 '${segment}'가 kebab-case가 아닙니다 (path segment '${segment}' is not kebab-case)`,
            fix: `'${segment}' → '${toKebabCase(segment)}'`,
          });
          break; // 경로당 하나만 보고
        }
      }
    }

    return violations;
  },
};

export const propertyNamingRule: LintRule = {
  id: 'karax/property-naming',
  defaultSeverity: 'error',
  guidelineRef: '§ 3.1',
  description: '필드명 camelCase (property names must use camelCase)',

  check(spec: OpenApiSpec): ApiLintViolation[] {
    const violations: ApiLintViolation[] = [];

    if (!spec.components?.schemas) return violations;

    for (const [schemaName, schema] of Object.entries(spec.components.schemas)) {
      checkPropertyNaming(schema, `components.schemas.${schemaName}`, violations, this.defaultSeverity);
    }

    return violations;
  },
};

function checkPropertyNaming(
  schema: SchemaObject,
  basePath: string,
  violations: ApiLintViolation[],
  severity: 'error' | 'warn',
): void {
  if (!schema.properties) return;

  for (const [propName, propSchema] of Object.entries(schema.properties)) {
    const path = `${basePath}.properties.${propName}`;

    // $로 시작하는 특수 필드, _로 시작하는 내부 필드 제외
    if (propName.startsWith('$') || propName.startsWith('_')) continue;

    if (!CAMEL_CASE.test(propName)) {
      violations.push({
        ruleId: 'karax/property-naming',
        severity,
        path,
        message: `필드명 '${propName}'이 camelCase가 아닙니다 (property '${propName}' is not camelCase)`,
        fix: `'${propName}' → '${toCamelCase(propName)}'`,
      });
    }

    if (propSchema.type === 'object' && propSchema.properties) {
      checkPropertyNaming(propSchema, path, violations, severity);
    }
  }
}

function toKebabCase(str: string): string {
  return str
    .replace(/([a-z])([A-Z])/g, '$1-$2')
    .replace(/_/g, '-')
    .toLowerCase();
}

function toCamelCase(str: string): string {
  return str
    .replace(/[-_](.)/g, (_, c: string) => c.toUpperCase())
    .replace(/^[A-Z]/, (c) => c.toLowerCase());
}
