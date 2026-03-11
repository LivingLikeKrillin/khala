/**
 * karax/nullable-explicit, karax/no-nullable-optional 룰
 *
 * - nullable 필드에 nullable: true가 명시되어 있는지 검사
 * - nullable + optional 동시 적용 금지 검사
 *
 * 규정 근거: 규정 ② § 2.3.1
 */

import type { LintRule, OpenApiSpec, SchemaObject, ApiLintViolation } from '../types.js';

/**
 * nullable-explicit: nullable 필드에 nullable: true가 명시되어 있는지 검사.
 *
 * 이 룰은 "example에 null이 있는데 nullable: true가 없는 경우"나
 * "필드명이 nullable 패턴인데 표시가 없는 경우"를 탐지한다.
 * 내장 엔진 한계로, example에 null이 있는 경우만 탐지한다.
 */
export const nullableExplicitRule: LintRule = {
  id: 'karax/nullable-explicit',
  defaultSeverity: 'error',
  guidelineRef: '§ 2.3.1',
  description: 'nullable 필드는 nullable: true 명시 (nullable fields must declare nullable: true)',

  check(spec: OpenApiSpec): ApiLintViolation[] {
    const violations: ApiLintViolation[] = [];

    if (!spec.components?.schemas) return violations;

    for (const [schemaName, schema] of Object.entries(spec.components.schemas)) {
      checkNullableFields(schema, `components.schemas.${schemaName}`, violations, this.defaultSeverity);
    }

    return violations;
  },
};

/**
 * no-nullable-optional: nullable + optional 동시 적용 금지.
 *
 * 필드가 nullable: true이면서 required 배열에 포함되지 않은 경우 경고.
 */
export const noNullableOptionalRule: LintRule = {
  id: 'karax/no-nullable-optional',
  defaultSeverity: 'warn',
  guidelineRef: '§ 2.3.1',
  description: 'nullable + optional 동시 적용 금지 (no nullable + optional combination)',

  check(spec: OpenApiSpec): ApiLintViolation[] {
    const violations: ApiLintViolation[] = [];

    if (!spec.components?.schemas) return violations;

    for (const [schemaName, schema] of Object.entries(spec.components.schemas)) {
      checkNullableOptional(schema, `components.schemas.${schemaName}`, violations, this.defaultSeverity);
    }

    return violations;
  },
};

function checkNullableFields(
  schema: SchemaObject,
  basePath: string,
  violations: ApiLintViolation[],
  severity: 'error' | 'warn',
): void {
  if (!schema.properties) return;

  for (const [propName, propSchema] of Object.entries(schema.properties)) {
    const path = `${basePath}.properties.${propName}`;

    // example이 null인데 nullable: true가 없는 경우
    if (propSchema.example === null && !propSchema.nullable) {
      violations.push({
        ruleId: 'karax/nullable-explicit',
        severity,
        path,
        message: `nullable 필드 '${propName}'에 nullable: true가 없습니다 (nullable field '${propName}' missing nullable: true)`,
        fix: `"nullable": true를 추가하세요`,
      });
    }

    // 중첩 검사
    if (propSchema.type === 'object' && propSchema.properties) {
      checkNullableFields(propSchema, path, violations, severity);
    }
  }
}

function checkNullableOptional(
  schema: SchemaObject,
  basePath: string,
  violations: ApiLintViolation[],
  severity: 'error' | 'warn',
): void {
  if (!schema.properties) return;

  const requiredFields = schema.required ?? [];

  for (const [propName, propSchema] of Object.entries(schema.properties)) {
    const path = `${basePath}.properties.${propName}`;

    if (propSchema.nullable === true && !requiredFields.includes(propName)) {
      violations.push({
        ruleId: 'karax/no-nullable-optional',
        severity,
        path,
        message: `필드 '${propName}'이 nullable이면서 optional입니다 (field '${propName}' is both nullable and optional)`,
        fix: `nullable이면 required로, optional이면 nullable을 제거하세요`,
      });
    }

    if (propSchema.type === 'object' && propSchema.properties) {
      checkNullableOptional(propSchema, path, violations, severity);
    }
  }
}
