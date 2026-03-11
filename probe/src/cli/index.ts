#!/usr/bin/env node

/**
 * Karax CLI
 *
 * Usage:
 *   karax check [--base <ref>] [--format <markdown|json|brief>] [--silent]
 *   karax version
 *
 * 규정 문서: docs/karax-v0.1-scope.md § 4.1
 */

import { execSync } from 'node:child_process';
import { analyzeScope } from '../core/scope-analyzer.js';
import { loadConfigAsync, applyConfigOverrides } from '../core/config-loader.js';
import { detectPlatform, getProfileForPlatform } from '../profiles/detector.js';
import type { ScopeAnalysisResult } from '../core/scope-analyzer.js';
import type { SeverityLevel } from '../profiles/types.js';
import { logger } from '../utils/logger.js';

type OutputFormat = 'markdown' | 'json' | 'brief';

interface CheckOptions {
  base: string;
  format: OutputFormat;
  silent: boolean;
}

// ─── CLI 인자 파싱 ───

/**
 * CLI 인자를 파싱한다.
 */
function parseArgs(args: string[]): CheckOptions {
  const options: CheckOptions = {
    base: 'origin/main',
    format: 'markdown',
    silent: false,
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--base' && args[i + 1]) {
      options.base = args[i + 1]!;
      i++;
    } else if (arg === '--format' && args[i + 1]) {
      const fmt = args[i + 1]!;
      if (fmt === 'markdown' || fmt === 'json' || fmt === 'brief') {
        options.format = fmt;
      }
      i++;
    } else if (arg === '--silent') {
      options.silent = true;
    }
  }

  return options;
}

// ─── Git 연동 ───

/**
 * git diff로 변경 파일 목록을 가져온다.
 */
function getChangedFiles(base: string): string[] {
  try {
    // 먼저 staged + unstaged 변경을 확인
    const diffOutput = execSync(`git diff --name-only ${base}...HEAD`, {
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    const files = diffOutput
      .split('\n')
      .map((f) => f.trim())
      .filter((f) => f.length > 0);

    // staged 파일도 포함
    const stagedOutput = execSync('git diff --name-only --cached', {
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    const stagedFiles = stagedOutput
      .split('\n')
      .map((f) => f.trim())
      .filter((f) => f.length > 0);

    // 중복 제거
    return [...new Set([...files, ...stagedFiles])];
  } catch {
    // HEAD가 없거나 base가 없는 경우, staged + working tree 변경만
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
 */
function getDiffLines(base: string): number {
  try {
    const output = execSync(`git diff --shortstat ${base}...HEAD`, {
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    const match = output.match(/(\d+) insertions?.*?(\d+) deletions?/);
    if (match?.[1] && match[2]) {
      return parseInt(match[1], 10) + parseInt(match[2], 10);
    }

    // insertions만 있는 경우
    const insertMatch = output.match(/(\d+) insertions?/);
    if (insertMatch?.[1]) {
      return parseInt(insertMatch[1], 10);
    }

    // deletions만 있는 경우
    const deleteMatch = output.match(/(\d+) deletions?/);
    if (deleteMatch?.[1]) {
      return parseInt(deleteMatch[1], 10);
    }

    return 0;
  } catch {
    return 0;
  }
}

// ─── 출력 포맷 ───

const SEVERITY_ICONS: Record<SeverityLevel, string> = {
  ok: '\u2705',
  info: '\u26A0\uFE0F',
  warn: '\uD83D\uDD36',
  error: '\uD83D\uDD34',
};

const SEVERITY_LABELS: Record<SeverityLevel, string> = {
  ok: '정상 범위',
  info: '분리 권장',
  warn: 'PR 범위 경고',
  error: '강력 경고 — PR 분할 필요',
};

/**
 * 분석 결과를 마크다운 형식으로 포맷한다.
 */
function formatMarkdown(result: ScopeAnalysisResult): string {
  const icon = SEVERITY_ICONS[result.severity];
  const label = SEVERITY_LABELS[result.severity];
  const lines: string[] = [];

  lines.push(`${icon} Karax — ${label}`);
  lines.push('');

  if (result.severity === 'ok') {
    const groupSummary = result.groups
      .filter((g) => g.groupName !== 'unmatched')
      .map((g) => `${g.groupName} (${g.cohesionKeyValue})`)
      .join(', ');

    lines.push(`현재 변경: ${groupSummary || '분석 완료'} (${result.totalFiles}개 파일, +${result.totalDiffLines}줄)`);
    lines.push(`응집도: 높음 (단일 관심사)`);
    lines.push(`PR 크기: 정상 범위`);
    return lines.join('\n');
  }

  lines.push(`현재 변경이 ${result.groups.length}개의 서로 다른 관심사에 걸쳐 있습니다.`);
  lines.push('');

  for (let i = 0; i < result.groups.length; i++) {
    const group = result.groups[i]!;
    const label = group.groupName === 'unmatched'
      ? '기타 파일'
      : `${group.groupName} (${group.cohesionKeyValue})`;

    lines.push(`  그룹 ${i + 1}: ${label} (${group.files.length}개 파일)`);

    for (const file of group.files) {
      lines.push(`    - ${file.path}`);
    }
    lines.push('');
  }

  if (result.mixedConcerns.length > 0) {
    lines.push('관심사 혼재 경고:');
    for (const mc of result.mixedConcerns) {
      lines.push(`  - ${mc.reason}`);
    }
    lines.push('');
  }

  if (result.splitSuggestion) {
    lines.push('제안하는 분할:');
    for (const pr of result.splitSuggestion.proposedPrs) {
      lines.push(`  PR ${pr.order}: ${pr.description}`);
      for (const file of pr.files) {
        lines.push(`    - ${file}`);
      }
    }
  }

  return lines.join('\n');
}

/**
 * 분석 결과를 간략 형식으로 포맷한다.
 */
function formatBrief(result: ScopeAnalysisResult): string {
  const icon = SEVERITY_ICONS[result.severity];
  const label = SEVERITY_LABELS[result.severity];
  return `${icon} ${label} — ${result.totalFiles}개 파일, ${result.groups.length}개 그룹, ${result.mixedConcerns.length}개 혼재 경고`;
}

// ─── 메인 ───

/**
 * check 커맨드를 실행한다.
 */
async function runCheck(args: string[]): Promise<void> {
  const options = parseArgs(args);
  const config = await loadConfigAsync();

  // 플랫폼 감지
  const configPlatform = config.platform;
  const platform = configPlatform && configPlatform !== 'custom'
    ? configPlatform
    : detectPlatform();

  const baseProfile = configPlatform === 'custom' && config.customProfile
    ? config.customProfile
    : getProfileForPlatform(platform);

  if (!baseProfile) {
    logger.warn(`플랫폼을 감지할 수 없습니다 (Platform not detected). karax.config.ts에서 platform을 지정하세요.`);
    process.exitCode = 1;
    return;
  }

  const profile = applyConfigOverrides(baseProfile, config);

  // 변경 파일 수집
  const changedFiles = getChangedFiles(options.base);

  if (changedFiles.length === 0) {
    if (!options.silent) {
      logger.info('변경 파일이 없습니다 (No changed files).');
    }
    return;
  }

  // ignore 패턴 적용
  const filteredFiles = config.ignore
    ? changedFiles.filter((f) => !config.ignore!.some((pattern) => f.includes(pattern)))
    : changedFiles;

  // diff 라인 수 수집
  const diffLines = getDiffLines(options.base);

  // 분석 실행
  const result = analyzeScope(filteredFiles, profile, diffLines);

  // 정상이고 silent이면 출력 없음
  if (result.severity === 'ok' && options.silent) {
    return;
  }

  // 최소 레벨 필터링
  if (config.severity?.minLevel) {
    const levelOrder: Record<string, number> = { ok: 0, info: 1, warn: 2, error: 3 };
    const minLevel = levelOrder[config.severity.minLevel] ?? 0;
    const currentLevel = levelOrder[result.severity] ?? 0;
    if (currentLevel < minLevel) return;
  }

  // 출력
  switch (options.format) {
    case 'json':
      logger.info(JSON.stringify(result, null, 2));
      break;
    case 'brief':
      logger.info(formatBrief(result));
      break;
    case 'markdown':
    default:
      logger.info(formatMarkdown(result));
      break;
  }

  // warn/error 시 exit code 1
  if (result.severity === 'warn' || result.severity === 'error') {
    process.exitCode = 1;
  }
}

// ─── Entry Point ───

const args = process.argv.slice(2);
const command = args[0];

switch (command) {
  case 'check':
    void runCheck(args.slice(1));
    break;
  case 'version':
    logger.info('karax v0.1.0');
    break;
  default:
    logger.info(`\u2699\uFE0F Karax \u2014 \uD504\uB85C\uB355\uD2B8 \uAC1C\uBC1C \uC6CC\uD06C\uD50C\uB85C \uC790\uB3D9 \uAC80\uC99D \uB3C4\uAD6C

Usage:
  karax check    현재 브랜치의 변경 범위를 분석합니다
  karax version  버전을 출력합니다

Options (check):
  --base <ref>     기준 브랜치 (기본: origin/main)
  --format <type>  출력 형식: markdown | json | brief
  --silent         경고 없을 때 출력 없음`);
}
