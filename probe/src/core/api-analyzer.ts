/**
 * API 분석기 — 코어 오케스트레이터
 *
 * oasdiff(외부) 또는 내장 diff 엔진을 사용하여
 * 두 버전의 OpenAPI 스펙을 비교한다.
 *
 * 규정 문서: docs/karax-v0.2-scope.md § 3.2
 */

import { existsSync } from 'node:fs';
import { parseOpenApiSpec } from '../api/openapi-parser.js';
import { diffSpecs } from '../api/spec-differ.js';
import { runOasdiff, isOasdiffAvailable } from '../api/oasdiff-runner.js';
import type { ApiDiffResult } from '../api/types.js';
import { logger } from '../utils/logger.js';

/** API diff 옵션 */
export interface ApiDiffOptions {
  /** 기준 스펙 경로 */
  baseSpecPath: string;

  /** 현재 스펙 경로 */
  headSpecPath: string;

  /** oasdiff 사용 여부 ('auto' | true | false) */
  useOasdiff?: 'auto' | boolean;
}

/**
 * 두 API 스펙을 비교한다.
 *
 * @param options diff 옵션
 * @returns diff 결과
 */
export async function diffApiSpecs(options: ApiDiffOptions): Promise<ApiDiffResult> {
  const { baseSpecPath, headSpecPath, useOasdiff = 'auto' } = options;

  // 파일 존재 확인
  if (!existsSync(baseSpecPath) || !existsSync(headSpecPath)) {
    return {
      summary: { added: 0, modified: 0, removed: 0, deprecated: 0, hasBreaking: false },
      changes: [],
      suggestedLabel: null,
    };
  }

  // oasdiff 사용 결정
  const shouldUseOasdiff = useOasdiff === true ||
    (useOasdiff === 'auto' && await isOasdiffAvailable());

  if (shouldUseOasdiff) {
    try {
      logger.debug('oasdiff로 API diff 실행');
      return await runOasdiff(baseSpecPath, headSpecPath);
    } catch {
      logger.warn('oasdiff 실행 실패, 내장 diff 엔진으로 폴백합니다 (oasdiff failed, falling back to built-in differ)');
    }
  } else if (useOasdiff === 'auto') {
    logger.debug('oasdiff가 설치되지 않아 내장 diff 엔진을 사용합니다 (oasdiff not found, using built-in differ)');
  }

  // 내장 diff 엔진
  const baseSpec = parseOpenApiSpec(baseSpecPath);
  const headSpec = parseOpenApiSpec(headSpecPath);
  return diffSpecs(baseSpec, headSpec);
}
