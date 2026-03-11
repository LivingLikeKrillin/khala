/**
 * Git 연동 유틸
 *
 * CLI와 MCP 서버에서 공용으로 사용하는 git 함수.
 * cli/index.ts에서 추출.
 */

import { execSync } from 'node:child_process';

/**
 * git diff로 변경 파일 목록을 가져온다.
 *
 * @param base 기준 브랜치 (기본: origin/main)
 * @returns 변경된 파일 경로 배열
 */
export function getChangedFiles(base: string = 'origin/main'): string[] {
  try {
    const diffOutput = execSync(`git diff --name-only ${base}...HEAD`, {
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    const files = diffOutput
      .split('\n')
      .map((f) => f.trim())
      .filter((f) => f.length > 0);

    const stagedOutput = execSync('git diff --name-only --cached', {
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    const stagedFiles = stagedOutput
      .split('\n')
      .map((f) => f.trim())
      .filter((f) => f.length > 0);

    return [...new Set([...files, ...stagedFiles])];
  } catch {
    try {
      const output = execSync('git diff --name-only HEAD', {
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe'],
      });
      return output
        .split('\n')
        .map((f) => f.trim())
        .filter((f) => f.length > 0);
    } catch {
      return [];
    }
  }
}

/**
 * 총 diff 라인 수를 가져온다.
 *
 * @param base 기준 브랜치
 * @returns diff 라인 수 (insertions + deletions)
 */
export function getDiffLines(base: string = 'origin/main'): number {
  try {
    const output = execSync(`git diff --shortstat ${base}...HEAD`, {
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    const match = output.match(/(\d+) insertions?.*?(\d+) deletions?/);
    if (match?.[1] && match[2]) {
      return parseInt(match[1], 10) + parseInt(match[2], 10);
    }

    const insertMatch = output.match(/(\d+) insertions?/);
    if (insertMatch?.[1]) return parseInt(insertMatch[1], 10);

    const deleteMatch = output.match(/(\d+) deletions?/);
    if (deleteMatch?.[1]) return parseInt(deleteMatch[1], 10);

    return 0;
  } catch {
    return 0;
  }
}

/**
 * base 브랜치의 파일 내용을 가져온다.
 *
 * @param base 기준 브랜치
 * @param filePath 파일 경로
 * @returns 파일 내용 또는 undefined
 */
export function getBaseFileContent(base: string, filePath: string): string | undefined {
  try {
    return execSync(`git show ${base}:${filePath}`, {
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
  } catch {
    return undefined;
  }
}
