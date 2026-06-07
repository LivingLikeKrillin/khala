/**
 * OpenAPI JSON 파서
 *
 * JSON/YAML 파일을 읽어 OpenApiSpec 타입으로 파싱한다.
 * YAML은 JSON 변환이 필요하므로, JSON만 기본 지원.
 *
 * 규정 문서: docs/probe-v0.2-scope.md § 3.1
 */

import { readFileSync } from 'node:fs';
import type { OpenApiSpec } from './types.js';

/**
 * OpenAPI 스펙 파일을 파싱한다.
 *
 * @param specPath 스펙 파일 경로 (JSON)
 * @returns 파싱된 OpenApiSpec
 * @throws 파일이 없거나 JSON 파싱 실패 시
 */
export function parseOpenApiSpec(specPath: string): OpenApiSpec {
  const content = readFileSync(specPath, 'utf-8');
  const parsed = JSON.parse(content) as OpenApiSpec;

  if (!parsed.openapi && !parsed.info) {
    throw new Error(
      `유효한 OpenAPI 스펙이 아닙니다 (Not a valid OpenAPI spec): ${specPath}`,
    );
  }

  return parsed;
}

/**
 * JSON 문자열에서 OpenAPI 스펙을 파싱한다.
 *
 * @param json JSON 문자열
 * @returns 파싱된 OpenApiSpec
 */
export function parseOpenApiSpecFromString(json: string): OpenApiSpec {
  return JSON.parse(json) as OpenApiSpec;
}
