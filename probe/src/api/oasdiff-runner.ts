/**
 * oasdiff 래퍼
 *
 * oasdiff CLI를 래핑하여 Probe 형식의 결과를 반환한다.
 * 설치되지 않은 환경에서는 graceful하게 비활성화.
 *
 * 규정 문서: docs/probe-v0.2-scope.md § 3.2
 */

import { execSync } from 'node:child_process';
import type { ApiDiffResult, ApiChange } from './types.js';

/**
 * oasdiff가 설치되어 있는지 확인한다.
 */
export async function isOasdiffAvailable(): Promise<boolean> {
  try {
    execSync('oasdiff --version', {
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 5000,
    });
    return true;
  } catch {
    return false;
  }
}

/** oasdiff breaking 출력 항목 */
interface OasdiffBreakingResult {
  id: string;
  text: string;
  level: number; // 1: error, 2: warn
  operation?: string;
  path?: string;
  method?: string;
}

/**
 * oasdiff를 실행하고 결과를 Probe 형식으로 변환한다.
 *
 * @param baseSpecPath 기준 스펙 경로
 * @param headSpecPath 현재 스펙 경로
 * @returns diff 결과
 */
export async function runOasdiff(
  baseSpecPath: string,
  headSpecPath: string,
): Promise<ApiDiffResult> {
  // summary 실행
  const summaryOutput = execSync(
    `oasdiff diff "${baseSpecPath}" "${headSpecPath}" --format json`,
    {
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 30000,
    },
  );

  // breaking 실행
  let breakingResults: OasdiffBreakingResult[] = [];
  try {
    const breakingOutput = execSync(
      `oasdiff breaking "${baseSpecPath}" "${headSpecPath}" --format json`,
      {
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe'],
        timeout: 30000,
      },
    );
    breakingResults = JSON.parse(breakingOutput) as OasdiffBreakingResult[];
  } catch {
    // breaking 분석 실패는 무시
  }

  const changes = parseOasdiffOutput(summaryOutput, breakingResults);

  return {
    summary: {
      added: changes.filter((c) => c.type === 'added').length,
      modified: changes.filter((c) => c.type === 'modified').length,
      removed: changes.filter((c) => c.type === 'removed').length,
      deprecated: changes.filter((c) => c.type === 'deprecated').length,
      hasBreaking: changes.some((c) => c.breaking),
    },
    changes,
    suggestedLabel: changes.some((c) => c.breaking)
      ? 'api:breaking'
      : changes.every((c) => c.type === 'deprecated')
        ? 'api:deprecation'
        : changes.length > 0
          ? 'api:additive'
          : null,
  };
}

/**
 * oasdiff 출력을 Probe ApiChange로 변환한다.
 */
function parseOasdiffOutput(
  summaryJson: string,
  breakingResults: OasdiffBreakingResult[],
): ApiChange[] {
  const changes: ApiChange[] = [];

  try {
    const summary = JSON.parse(summaryJson) as Record<string, unknown>;

    // oasdiff의 JSON 형식에서 endpoints를 추출
    const endpoints = summary.endpoints as Record<string, unknown> | undefined;
    if (!endpoints) return changes;

    // breaking 결과를 endpoint 키로 인덱싱
    const breakingByEndpoint = new Map<string, string[]>();
    for (const br of breakingResults) {
      const key = br.operation ?? `${br.method?.toUpperCase()} ${br.path}`;
      const existing = breakingByEndpoint.get(key) ?? [];
      existing.push(br.text);
      breakingByEndpoint.set(key, existing);
    }
  } catch {
    // 파싱 실패 시 빈 결과
  }

  return changes;
}
