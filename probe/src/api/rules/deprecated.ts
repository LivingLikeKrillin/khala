/**
 * karax/deprecated-lifecycle 룰
 *
 * deprecated 표시 없이 삭제하면 안 된다.
 * 이 룰은 단일 스펙 린트에서는 "deprecated 필드에 설명이 있는지"만 검사한다.
 * 실제 "삭제 전 deprecated 표시" 검증은 api-analyzer (diff)에서 수행.
 *
 * 규정 근거: 규정 ② § 2.4.3
 */

import type { LintRule, OpenApiSpec, ApiLintViolation } from '../types.js';

const METHODS = ['get', 'post', 'put', 'patch', 'delete'] as const;

export const deprecatedLifecycleRule: LintRule = {
  id: 'karax/deprecated-lifecycle',
  defaultSeverity: 'error',
  guidelineRef: '§ 2.4.3',
  description: 'deprecated 표시 없이 삭제 금지 (no removal without deprecation notice)',

  check(spec: OpenApiSpec): ApiLintViolation[] {
    const violations: ApiLintViolation[] = [];

    if (!spec.paths) return violations;

    // deprecated된 오퍼레이션에 description/summary가 있는지 확인
    for (const [pathKey, pathItem] of Object.entries(spec.paths)) {
      for (const method of METHODS) {
        const operation = pathItem[method];
        if (!operation?.deprecated) continue;

        const path = `paths.${pathKey}.${method}`;

        // deprecated 오퍼레이션에 대체 안내가 있는지 확인
        const hasDeprecationNote = operation.summary?.toLowerCase().includes('deprecated') ||
          (typeof operation.description === 'string' && operation.description.toLowerCase().includes('deprecated'));

        if (!hasDeprecationNote) {
          violations.push({
            ruleId: 'karax/deprecated-lifecycle',
            severity: this.defaultSeverity,
            path,
            message: `deprecated 오퍼레이션에 폐기 안내가 없습니다 (deprecated operation missing deprecation notice)`,
            fix: `summary/description에 대체 API와 폐기 일정을 명시하세요`,
          });
        }
      }
    }

    return violations;
  },
};
