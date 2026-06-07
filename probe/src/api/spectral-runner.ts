/**
 * Spectral 래퍼
 *
 * @stoplight/spectral-cli를 래핑하여 Probe 형식의 결과를 반환한다.
 * 설치되지 않은 환경에서는 graceful하게 비활성화.
 *
 * 규정 문서: docs/probe-v0.2-scope.md § 3.1
 */

import { execSync } from 'node:child_process';
import type { ApiLintResult, ApiLintViolation } from './types.js';

/**
 * Spectral이 설치되어 있는지 확인한다.
 */
export async function isSpectralAvailable(): Promise<boolean> {
  try {
    execSync('npx spectral --version', {
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 5000,
    });
    return true;
  } catch {
    return false;
  }
}

/** Spectral JSON 출력 항목 */
interface SpectralResult {
  code: string;
  path: string[];
  message: string;
  severity: number; // 0: error, 1: warn, 2: info, 3: hint
  range: {
    start: { line: number; character: number };
    end: { line: number; character: number };
  };
}

/**
 * Spectral을 실행하고 결과를 Probe 형식으로 변환한다.
 *
 * @param specPath 스펙 파일 경로
 * @returns 린트 결과
 */
export async function runSpectral(specPath: string): Promise<ApiLintResult> {
  const output = execSync(
    `npx spectral lint "${specPath}" --format json`,
    {
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 30000,
    },
  );

  const results = JSON.parse(output) as SpectralResult[];

  const violations: ApiLintViolation[] = results
    .filter((r) => r.severity <= 1) // error, warn만
    .map((r) => ({
      ruleId: r.code,
      severity: r.severity === 0 ? 'error' as const : 'warn' as const,
      path: r.path.join('.'),
      message: r.message,
    }));

  const errors = violations.filter((v) => v.severity === 'error').length;
  const warnings = violations.filter((v) => v.severity === 'warn').length;

  return {
    specPath,
    summary: {
      errors,
      warnings,
      passed: 0, // Spectral은 passed 카운트를 제공하지 않음
    },
    violations,
  };
}
