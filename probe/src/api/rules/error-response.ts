/**
 * probe/error-response-schema 룰
 *
 * 4xx/5xx 응답이 ErrorResponse 스키마를 참조하는지 검사한다.
 *
 * 규정 근거: 규정 ② § 2.3.2
 */

import type { LintRule, OpenApiSpec, ApiLintViolation } from '../types.js';

const METHODS = ['get', 'post', 'put', 'patch', 'delete'] as const;

export const errorResponseSchemaRule: LintRule = {
  id: 'probe/error-response-schema',
  defaultSeverity: 'error',
  guidelineRef: '§ 2.3.2',
  description: '4xx/5xx → ErrorResponse 스키마 참조 (error responses must reference ErrorResponse schema)',

  check(spec: OpenApiSpec): ApiLintViolation[] {
    const violations: ApiLintViolation[] = [];

    if (!spec.paths) return violations;

    for (const [pathKey, pathItem] of Object.entries(spec.paths)) {
      for (const method of METHODS) {
        const operation = pathItem[method];
        if (!operation || !operation.responses) continue;

        for (const [statusCode, response] of Object.entries(operation.responses)) {
          const code = parseInt(statusCode, 10);
          if (isNaN(code) || code < 400) continue;

          const path = `paths.${pathKey}.${method}.responses.${statusCode}`;

          // content가 없으면 위반
          if (!response.content) {
            violations.push({
              ruleId: 'probe/error-response-schema',
              severity: this.defaultSeverity,
              path,
              message: `${statusCode} 응답에 content가 없습니다 (${statusCode} response missing content)`,
              fix: `ErrorResponse 스키마를 참조하는 content를 추가하세요`,
            });
            continue;
          }

          // content가 있으면 ErrorResponse 스키마 참조 확인
          const hasErrorRef = Object.values(response.content).some((mediaType) => {
            const ref = mediaType.schema?.$ref ?? '';
            return ref.includes('ErrorResponse') || ref.includes('Error');
          });

          if (!hasErrorRef) {
            violations.push({
              ruleId: 'probe/error-response-schema',
              severity: this.defaultSeverity,
              path,
              message: `${statusCode} 응답이 ErrorResponse를 참조하지 않습니다 (${statusCode} response does not reference ErrorResponse)`,
              fix: `$ref를 '#/components/schemas/ErrorResponse'로 지정하세요`,
            });
          }
        }
      }
    }

    return violations;
  },
};
