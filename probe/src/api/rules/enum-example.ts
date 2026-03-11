/**
 * karax/enum-required, karax/example-required 룰
 *
 * - 유한 집합 값은 enum 사용 권장
 * - 날짜/금액/ID에 example 필수
 *
 * 규정 근거: 규정 ② § 2.4.1, § 2.4.2
 */

import type { LintRule, OpenApiSpec, SchemaObject, ApiLintViolation } from '../types.js';

/** example이 필요한 format 패턴 */
const EXAMPLE_FORMATS = ['date', 'date-time', 'uuid', 'uri', 'email'];
const EXAMPLE_NAME_PATTERNS = [/id$/i, /at$/i, /date/i, /amount/i, /price/i, /cost/i];

export const enumRequiredRule: LintRule = {
  id: 'karax/enum-required',
  defaultSeverity: 'warn',
  guidelineRef: '§ 2.4.1',
  description: '유한 집합 값은 enum 사용 (finite value sets should use enum)',

  check(spec: OpenApiSpec): ApiLintViolation[] {
    const violations: ApiLintViolation[] = [];

    if (!spec.components?.schemas) return violations;

    for (const [schemaName, schema] of Object.entries(spec.components.schemas)) {
      checkEnumUsage(schema, `components.schemas.${schemaName}`, violations, this.defaultSeverity);
    }

    return violations;
  },
};

export const exampleRequiredRule: LintRule = {
  id: 'karax/example-required',
  defaultSeverity: 'warn',
  guidelineRef: '§ 2.4.2',
  description: '날짜/금액/ID에 example 필수 (date/amount/ID fields require example)',

  check(spec: OpenApiSpec): ApiLintViolation[] {
    const violations: ApiLintViolation[] = [];

    if (!spec.components?.schemas) return violations;

    for (const [schemaName, schema] of Object.entries(spec.components.schemas)) {
      checkExampleRequired(schema, `components.schemas.${schemaName}`, violations, this.defaultSeverity);
    }

    return violations;
  },
};

function checkEnumUsage(
  schema: SchemaObject,
  basePath: string,
  violations: ApiLintViolation[],
  severity: 'error' | 'warn',
): void {
  if (!schema.properties) return;

  for (const [propName, propSchema] of Object.entries(schema.properties)) {
    const path = `${basePath}.properties.${propName}`;

    // status, type, role, category 등 이름 패턴으로 enum 사용 여부 판단
    const enumNames = ['status', 'type', 'role', 'category', 'state', 'kind', 'level', 'priority'];
    if (propSchema.type === 'string' && enumNames.includes(propName.toLowerCase()) && !propSchema.enum) {
      violations.push({
        ruleId: 'karax/enum-required',
        severity,
        path,
        message: `필드 '${propName}'에 enum이 없습니다 (field '${propName}' should use enum)`,
        fix: `가능한 값들을 enum으로 정의하세요`,
      });
    }

    if (propSchema.type === 'object' && propSchema.properties) {
      checkEnumUsage(propSchema, path, violations, severity);
    }
  }
}

function checkExampleRequired(
  schema: SchemaObject,
  basePath: string,
  violations: ApiLintViolation[],
  severity: 'error' | 'warn',
): void {
  if (!schema.properties) return;

  for (const [propName, propSchema] of Object.entries(schema.properties)) {
    const path = `${basePath}.properties.${propName}`;

    const needsExample =
      (propSchema.format && EXAMPLE_FORMATS.includes(propSchema.format)) ||
      EXAMPLE_NAME_PATTERNS.some((pattern) => pattern.test(propName));

    if (needsExample && propSchema.example === undefined) {
      violations.push({
        ruleId: 'karax/example-required',
        severity,
        path,
        message: `필드 '${propName}'에 example이 없습니다 (field '${propName}' missing example)`,
        fix: `example 값을 추가하세요 (예: "example": "2024-01-01T00:00:00Z")`,
      });
    }

    if (propSchema.type === 'object' && propSchema.properties) {
      checkExampleRequired(propSchema, path, violations, severity);
    }
  }
}
