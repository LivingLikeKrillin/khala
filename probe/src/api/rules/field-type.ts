/**
 * probe/field-type-required 룰
 *
 * 모든 스키마 필드에 type이 명시되어 있는지 검사한다.
 * $ref, allOf, oneOf, anyOf가 있는 필드는 제외.
 *
 * 규정 근거: 규정 ② § 2.2
 */

import type { LintRule, OpenApiSpec, SchemaObject, ApiLintViolation } from '../types.js';

export const fieldTypeRule: LintRule = {
  id: 'probe/field-type-required',
  defaultSeverity: 'error',
  guidelineRef: '§ 2.2',
  description: '모든 필드에 type 필수 (type required for all fields)',

  check(spec: OpenApiSpec): ApiLintViolation[] {
    const violations: ApiLintViolation[] = [];

    if (!spec.components?.schemas) return violations;

    for (const [schemaName, schema] of Object.entries(spec.components.schemas)) {
      checkSchemaProperties(schema, `components.schemas.${schemaName}`, violations, this.defaultSeverity);
    }

    return violations;
  },
};

/**
 * 스키마의 properties를 재귀 순회하며 type 누락을 검사한다.
 */
function checkSchemaProperties(
  schema: SchemaObject,
  basePath: string,
  violations: ApiLintViolation[],
  severity: 'error' | 'warn',
): void {
  if (!schema.properties) return;

  for (const [propName, propSchema] of Object.entries(schema.properties)) {
    const path = `${basePath}.properties.${propName}`;

    // $ref, allOf, oneOf, anyOf가 있으면 type 없어도 됨
    if (propSchema.$ref || propSchema.allOf || propSchema.oneOf || propSchema.anyOf) {
      continue;
    }

    if (!propSchema.type) {
      violations.push({
        ruleId: 'probe/field-type-required',
        severity,
        path,
        message: `필드 '${propName}'에 type이 없습니다 (Field '${propName}' missing type)`,
        fix: `type을 명시하세요 (예: "type": "string")`,
      });
    }

    // 중첩 객체 재귀
    if (propSchema.type === 'object' && propSchema.properties) {
      checkSchemaProperties(propSchema, path, violations, severity);
    }
  }
}
