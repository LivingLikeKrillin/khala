/**
 * 내장 경량 린트 엔진
 *
 * OpenAPI JSON을 직접 파싱하여 내장 룰셋으로 검사한다.
 * Spectral이 없어도 동작하는 폴백 엔진.
 *
 * 규정 문서: docs/probe-v0.2-scope.md § 3.1
 */

import type { OpenApiSpec, ApiLintResult, ApiLintViolation } from './types.js';
import { ALL_RULES } from './rules/index.js';

/** 린트 옵션 */
export interface SpecLinterOptions {
  /** 비활성화할 룰 ID 목록 */
  disableRules?: string[];

  /** 룰별 심각도 오버라이드 */
  ruleSeverity?: Record<string, 'error' | 'warn' | 'off'>;
}

/**
 * 내장 린트 엔진으로 OpenAPI 스펙을 검사한다.
 *
 * @param spec 파싱된 OpenAPI 스펙
 * @param specPath 스펙 파일 경로 (결과 표시용)
 * @param options 린트 옵션
 * @returns 린트 결과
 */
export function lintSpec(
  spec: OpenApiSpec,
  specPath: string,
  options?: SpecLinterOptions,
): ApiLintResult {
  const disableRules = new Set(options?.disableRules ?? []);
  const ruleSeverity = options?.ruleSeverity ?? {};

  const allViolations: ApiLintViolation[] = [];
  let passedCount = 0;

  for (const rule of ALL_RULES) {
    // 비활성화된 룰 스킵
    if (disableRules.has(rule.id)) {
      passedCount++;
      continue;
    }

    // 심각도 오버라이드
    const overrideSeverity = ruleSeverity[rule.id];
    if (overrideSeverity === 'off') {
      passedCount++;
      continue;
    }

    const violations = rule.check(spec);

    if (overrideSeverity) {
      // 심각도 오버라이드 적용
      for (const v of violations) {
        v.severity = overrideSeverity;
      }
    }

    if (violations.length === 0) {
      passedCount++;
    } else {
      allViolations.push(...violations);
    }
  }

  const errors = allViolations.filter((v) => v.severity === 'error').length;
  const warnings = allViolations.filter((v) => v.severity === 'warn').length;

  return {
    specPath,
    summary: {
      errors,
      warnings,
      passed: passedCount,
    },
    violations: allViolations,
  };
}
