/**
 * API 린터 — 코어 오케스트레이터
 *
 * Spectral(외부) 또는 내장 린트 엔진을 사용하여
 * OpenAPI 스펙의 품질을 검증한다.
 *
 * 규정 문서: docs/karax-v0.2-scope.md § 3.1
 */

import { existsSync } from 'node:fs';
import { parseOpenApiSpec } from '../api/openapi-parser.js';
import { lintSpec } from '../api/spec-linter.js';
import { runSpectral, isSpectralAvailable } from '../api/spectral-runner.js';
import type { ApiLintResult } from '../api/types.js';
import { logger } from '../utils/logger.js';

/** API 린트 옵션 */
export interface ApiLintOptions {
  /** OpenAPI 스펙 파일 경로 */
  specPath: string;

  /** Spectral 사용 여부 ('auto' | true | false) */
  useSpectral?: 'auto' | boolean;

  /** 비활성화할 룰 ID 목록 */
  disableRules?: string[];

  /** 룰별 심각도 오버라이드 */
  ruleSeverity?: Record<string, 'error' | 'warn' | 'off'>;
}

/**
 * API 스펙을 린트한다.
 *
 * @param options 린트 옵션
 * @returns 린트 결과
 */
export async function lintApiSpec(options: ApiLintOptions): Promise<ApiLintResult> {
  const { specPath, useSpectral = 'auto', disableRules, ruleSeverity } = options;

  // 스펙 파일 존재 확인
  if (!existsSync(specPath)) {
    return {
      specPath,
      summary: { errors: 0, warnings: 0, passed: 0 },
      violations: [],
    };
  }

  // Spectral 사용 결정
  const shouldUseSpectral = useSpectral === true ||
    (useSpectral === 'auto' && await isSpectralAvailable());

  if (shouldUseSpectral) {
    try {
      logger.debug('Spectral로 API 린트 실행');
      return await runSpectral(specPath);
    } catch {
      logger.warn('Spectral 실행 실패, 내장 린트 엔진으로 폴백합니다 (Spectral failed, falling back to built-in linter)');
    }
  } else if (useSpectral === 'auto') {
    logger.debug('Spectral이 설치되지 않아 내장 린트 엔진을 사용합니다 (Spectral not found, using built-in linter)');
  }

  // 내장 린트 엔진
  const spec = parseOpenApiSpec(specPath);
  return lintSpec(spec, specPath, { disableRules, ruleSeverity });
}
