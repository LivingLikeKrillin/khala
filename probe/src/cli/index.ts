#!/usr/bin/env node

/**
 * Karax CLI
 *
 * Usage:
 *   karax check    [--base <ref>] [--format <markdown|json|brief>] [--silent]
 *   karax api:lint [spec-path] [--format <markdown|json|brief>]
 *   karax api:diff [--base <ref>] [--spec <path>] [--format <markdown|json|brief>]
 *   karax review   [--base <ref>] [--format <markdown|json|brief>]
 *   karax version
 *
 * 규정 문서: docs/karax-v0.2-scope.md § 3.4
 */

import { existsSync } from 'node:fs';
import { analyzeScope } from '../core/scope-analyzer.js';
import { loadConfigAsync, applyConfigOverrides } from '../core/config-loader.js';
import { detectPlatform, getProfileForPlatform } from '../profiles/detector.js';
import { lintApiSpec } from '../core/api-linter.js';
import { generateReviewChecklist } from '../core/review-checklist.js';
import type { ScopeAnalysisResult } from '../core/scope-analyzer.js';
import type { ApiLintResult } from '../api/types.js';
import type { ApiDiffResult } from '../api/types.js';
import type { ReviewChecklist } from '../review/types.js';
import type { SeverityLevel } from '../profiles/types.js';
import { logger } from '../utils/logger.js';
import { getChangedFiles, getDiffLines, getBaseFileContent } from '../utils/git.js';

type OutputFormat = 'markdown' | 'json' | 'brief';

interface CliOptions {
  base: string;
  format: OutputFormat;
  silent: boolean;
  spec: string;
}

// ─── CLI 인자 파싱 ───

/**
 * CLI 인자를 파싱한다.
 */
function parseArgs(args: string[]): CliOptions {
  const options: CliOptions = {
    base: 'origin/main',
    format: 'markdown',
    silent: false,
    spec: '',
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i]!;
    if (arg === '--base' && i + 1 < args.length) {
      options.base = args[i + 1]!;
      i++;
    } else if (arg === '--format' && i + 1 < args.length) {
      const fmt = args[i + 1]!;
      if (fmt === 'markdown' || fmt === 'json' || fmt === 'brief') {
        options.format = fmt;
      }
      i++;
    } else if (arg === '--spec' && i + 1 < args.length) {
      options.spec = args[i + 1]!;
      i++;
    } else if (arg === '--silent') {
      options.silent = true;
    } else if (!arg.startsWith('--') && !options.spec) {
      options.spec = arg;
    }
  }

  return options;
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
function formatScopeMarkdown(result: ScopeAnalysisResult, checklist?: ReviewChecklist): string {
  const icon = SEVERITY_ICONS[result.severity];
  const label = SEVERITY_LABELS[result.severity];
  const lines: string[] = [];

  lines.push(`${icon} Karax \u2014 ${label}`);
  lines.push('');

  if (result.severity === 'ok') {
    const groupSummary = result.groups
      .filter((g) => g.groupName !== 'unmatched')
      .map((g) => `${g.groupName} (${g.cohesionKeyValue})`)
      .join(', ');

    lines.push(`현재 변경: ${groupSummary || '분석 완료'} (${result.totalFiles}개 파일, +${result.totalDiffLines}줄)`);
    lines.push(`응집도: 높음 (단일 관심사)`);
    lines.push(`PR 크기: 정상 범위`);
  } else {
    lines.push(`현재 변경이 ${result.groups.length}개의 서로 다른 관심사에 걸쳐 있습니다.`);
    lines.push('');

    for (let i = 0; i < result.groups.length; i++) {
      const group = result.groups[i]!;
      const groupLabel = group.groupName === 'unmatched'
        ? '기타 파일'
        : `${group.groupName} (${group.cohesionKeyValue})`;

      lines.push(`  그룹 ${i + 1}: ${groupLabel} (${group.files.length}개 파일)`);

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
  }

  // v0.2: 리뷰 체크리스트 추가
  if (checklist && checklist.items.length > 0) {
    lines.push('');
    lines.push(`\uD83D\uDCCB 리뷰 체크리스트 (${checklist.prType}):`);

    for (const verified of checklist.autoVerified) {
      const icon = verified.passed ? '\u2705' : '\u274C';
      lines.push(`  ${icon} ${verified.description}${verified.detail ? ` (${verified.detail})` : ''}`);
    }

    for (const item of checklist.manualRequired) {
      lines.push(`  \u2B1C ${item.description} \u2014 수동 확인 필요`);
    }
  }

  return lines.join('\n');
}

/**
 * 분석 결과를 간략 형식으로 포맷한다.
 */
function formatScopeBrief(result: ScopeAnalysisResult): string {
  const icon = SEVERITY_ICONS[result.severity];
  const label = SEVERITY_LABELS[result.severity];
  return `${icon} ${label} \u2014 ${result.totalFiles}개 파일, ${result.groups.length}개 그룹, ${result.mixedConcerns.length}개 혼재 경고`;
}

/**
 * API 린트 결과를 마크다운으로 포맷한다.
 */
function formatLintMarkdown(result: ApiLintResult): string {
  const lines: string[] = [];

  if (result.summary.errors === 0 && result.summary.warnings === 0) {
    lines.push(`\u2705 API 린트 \u2014 0개 에러, 0개 경고`);
    return lines.join('\n');
  }

  const icon = result.summary.errors > 0 ? '\uD83D\uDD36' : '\u26A0\uFE0F';
  lines.push(`${icon} API 린트 \u2014 ${result.summary.errors}개 에러, ${result.summary.warnings}개 경고`);
  lines.push('');

  for (const v of result.violations) {
    const level = v.severity === 'error' ? 'ERROR' : 'WARN';
    lines.push(`  ${level} ${v.ruleId}`);
    lines.push(`    ${v.path}`);
    lines.push(`    \u2192 ${v.message}`);
    if (v.fix) {
      lines.push(`    \u2192 수정: ${v.fix}`);
    }
    lines.push('');
  }

  return lines.join('\n');
}

/**
 * API diff 결과를 마크다운으로 포맷한다.
 */
function formatDiffMarkdown(result: ApiDiffResult): string {
  const lines: string[] = [];

  if (result.changes.length === 0) {
    lines.push(`\u2705 API diff \u2014 변경 없음`);
    return lines.join('\n');
  }

  const icon = result.summary.hasBreaking ? '\uD83D\uDD34' : '\u2705';
  const label = result.summary.hasBreaking ? 'breaking 변경 포함' : '호환 변경';
  lines.push(`${icon} API 변경 감지 \u2014 ${label}`);
  lines.push('');
  lines.push(`변경 요약: ${result.summary.added}개 추가, ${result.summary.modified}개 수정, ${result.summary.removed}개 삭제`);
  lines.push('');

  for (const change of result.changes) {
    const changeIcon = change.breaking ? '\u26A0\uFE0F' :
      change.type === 'added' ? '\u2705' :
      change.type === 'removed' ? '\uD83D\uDD34' :
      change.type === 'deprecated' ? '\u26A0\uFE0F' : '\uD83D\uDD36';

    lines.push(`  ${changeIcon} ${change.endpoint}`);
    for (const detail of change.details) {
      lines.push(`    - ${detail}`);
    }
    lines.push('');
  }

  if (result.suggestedLabel) {
    lines.push(`권장 PR 라벨: ${result.suggestedLabel}`);
  }

  return lines.join('\n');
}

/**
 * 리뷰 체크리스트를 마크다운으로 포맷한다.
 */
function formatReviewMarkdown(checklist: ReviewChecklist): string {
  const lines: string[] = [];

  lines.push(`\uD83D\uDCCB 리뷰 체크리스트 (${checklist.prType})`);
  lines.push('');

  if (checklist.autoVerified.length > 0) {
    lines.push('## 자동 검증 결과');
    for (const v of checklist.autoVerified) {
      const icon = v.passed ? '\u2705' : '\u274C';
      lines.push(`- ${icon} ${v.description}${v.detail ? ` — ${v.detail}` : ''}`);
    }
    lines.push('');
  }

  const required = checklist.manualRequired.filter((i) => i.priority === 'required');
  const recommended = checklist.manualRequired.filter((i) => i.priority === 'recommended');

  if (required.length > 0) {
    lines.push('## 필수');
    for (const item of required) {
      const ref = item.guidelineRef ? ` (${item.guidelineRef})` : '';
      lines.push(`- [ ] ${item.description}${ref}`);
    }
    lines.push('');
  }

  if (recommended.length > 0) {
    lines.push('## 권장');
    for (const item of recommended) {
      const ref = item.guidelineRef ? ` (${item.guidelineRef})` : '';
      lines.push(`- [ ] ${item.description}${ref}`);
    }
  }

  return lines.join('\n');
}

// ─── 커맨드 ───

/**
 * check 커맨드 — 범위 분석 + 리뷰 체크리스트 통합
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

  // v0.1: 범위 분석
  const result = analyzeScope(filteredFiles, profile, diffLines);

  // v0.2: 리뷰 체크리스트 생성
  const specPath = config.api?.specPath ?? 'api/openapi.json';
  const hasApiSpecChange = filteredFiles.some((f) => f.includes(specPath) || f.endsWith('.json') && f.includes('openapi'));

  const checklist = generateReviewChecklist(result, filteredFiles, {
    hasApiSpecChange,
    disableChecklists: config.review?.disableChecklists,
    customItems: config.review?.customItems,
  });

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
      logger.info(JSON.stringify({ scope: result, checklist }, null, 2));
      break;
    case 'brief':
      logger.info(formatScopeBrief(result));
      break;
    case 'markdown':
    default:
      logger.info(formatScopeMarkdown(result, checklist));
      break;
  }

  // warn/error 시 exit code 1
  if (result.severity === 'warn' || result.severity === 'error') {
    process.exitCode = 1;
  }
}

/**
 * api:lint 커맨드 — API 스펙 린트
 */
async function runApiLint(args: string[]): Promise<void> {
  const options = parseArgs(args);
  const config = await loadConfigAsync();

  const specPath = options.spec || config.api?.specPath || 'api/openapi.json';

  if (!existsSync(specPath)) {
    logger.warn(`API 스펙 파일을 찾을 수 없습니다 (API spec not found): ${specPath}`);
    process.exitCode = 1;
    return;
  }

  const result = await lintApiSpec({
    specPath,
    useSpectral: config.api?.useSpectral ?? 'auto',
    disableRules: config.api?.disableRules,
    ruleSeverity: config.api?.ruleSeverity,
  });

  switch (options.format) {
    case 'json':
      logger.info(JSON.stringify(result, null, 2));
      break;
    case 'brief':
      logger.info(`API 린트: ${result.summary.errors}개 에러, ${result.summary.warnings}개 경고`);
      break;
    case 'markdown':
    default:
      logger.info(formatLintMarkdown(result));
      break;
  }

  if (result.summary.errors > 0) {
    process.exitCode = 1;
  }
}

/**
 * api:diff 커맨드 — API 스펙 diff
 */
async function runApiDiff(args: string[]): Promise<void> {
  const options = parseArgs(args);
  const config = await loadConfigAsync();

  const specPath = options.spec || config.api?.specPath || 'api/openapi.json';

  if (!existsSync(specPath)) {
    logger.warn(`API 스펙 파일을 찾을 수 없습니다 (API spec not found): ${specPath}`);
    process.exitCode = 1;
    return;
  }

  // base 브랜치의 스펙 가져오기
  const baseContent = getBaseFileContent(options.base, specPath);
  if (!baseContent) {
    logger.warn(`기준 브랜치에서 스펙 파일을 찾을 수 없습니다 (Spec not found in base): ${options.base}:${specPath}`);
    process.exitCode = 1;
    return;
  }

  // 임시 파일 없이 내장 엔진으로 직접 diff
  const { parseOpenApiSpecFromString } = await import('../api/openapi-parser.js');
  const { diffSpecs } = await import('../api/spec-differ.js');

  const baseSpec = parseOpenApiSpecFromString(baseContent);
  const { parseOpenApiSpec } = await import('../api/openapi-parser.js');
  const headSpec = parseOpenApiSpec(specPath);

  const result = diffSpecs(baseSpec, headSpec);

  switch (options.format) {
    case 'json':
      logger.info(JSON.stringify(result, null, 2));
      break;
    case 'brief': {
      const label = result.summary.hasBreaking ? 'breaking' : 'additive';
      logger.info(`API diff: ${result.changes.length}개 변경 (${label})`);
      break;
    }
    case 'markdown':
    default:
      logger.info(formatDiffMarkdown(result));
      break;
  }

  if (result.summary.hasBreaking) {
    process.exitCode = 1;
  }
}

/**
 * review 커맨드 — 리뷰 체크리스트만 생성
 */
async function runReview(args: string[]): Promise<void> {
  const options = parseArgs(args);
  const config = await loadConfigAsync();

  const configPlatform = config.platform;
  const platform = configPlatform && configPlatform !== 'custom'
    ? configPlatform
    : detectPlatform();

  const baseProfile = configPlatform === 'custom' && config.customProfile
    ? config.customProfile
    : getProfileForPlatform(platform);

  if (!baseProfile) {
    logger.warn(`플랫폼을 감지할 수 없습니다 (Platform not detected).`);
    process.exitCode = 1;
    return;
  }

  const profile = applyConfigOverrides(baseProfile, config);
  const changedFiles = getChangedFiles(options.base);

  if (changedFiles.length === 0) {
    if (!options.silent) {
      logger.info('변경 파일이 없습니다 (No changed files).');
    }
    return;
  }

  const filteredFiles = config.ignore
    ? changedFiles.filter((f) => !config.ignore!.some((pattern) => f.includes(pattern)))
    : changedFiles;

  const diffLines = getDiffLines(options.base);
  const result = analyzeScope(filteredFiles, profile, diffLines);

  const specPath = config.api?.specPath ?? 'api/openapi.json';
  const hasApiSpecChange = filteredFiles.some((f) => f.includes(specPath));

  const checklist = generateReviewChecklist(result, filteredFiles, {
    hasApiSpecChange,
    disableChecklists: config.review?.disableChecklists,
    customItems: config.review?.customItems,
  });

  switch (options.format) {
    case 'json':
      logger.info(JSON.stringify(checklist, null, 2));
      break;
    case 'brief':
      logger.info(`리뷰 체크리스트: ${checklist.prType} (${checklist.items.length}개 항목)`);
      break;
    case 'markdown':
    default:
      logger.info(formatReviewMarkdown(checklist));
      break;
  }
}

// ─── Entry Point ───

const args = process.argv.slice(2);
const command = args[0];

switch (command) {
  case 'check':
    void runCheck(args.slice(1));
    break;
  case 'api:lint':
    void runApiLint(args.slice(1));
    break;
  case 'api:diff':
    void runApiDiff(args.slice(1));
    break;
  case 'review':
    void runReview(args.slice(1));
    break;
  case 'version':
    logger.info('karax v0.3.0');
    break;
  default:
    logger.info(`\u2699\uFE0F Karax \u2014 프로덕트 개발 워크플로 자동 검증 도구

Usage:
  karax check       현재 브랜치의 변경 범위 + 리뷰 체크리스트
  karax api:lint     API 스펙 린트
  karax api:diff     API 스펙 diff (breaking 변경 감지)
  karax review       리뷰 체크리스트 생성
  karax version      버전 출력

Options:
  --base <ref>       기준 브랜치 (기본: origin/main)
  --format <type>    출력 형식: markdown | json | brief
  --spec <path>      API 스펙 파일 경로
  --silent           경고 없을 때 출력 없음`);
}
