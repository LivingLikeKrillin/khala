#!/usr/bin/env node

/**
 * Probe CLI
 *
 * Usage:
 *   probe check    [--base <ref>] [--format <markdown|json|brief>] [--silent]
 *   probe api:lint [spec-path] [--format <markdown|json|brief>]
 *   probe api:diff [--base <ref>] [--spec <path>] [--format <markdown|json|brief>]
 *   probe review   [--base <ref>] [--format <markdown|json|brief>]
 *   probe version
 *
 * 규정 문서: docs/probe-v0.2-scope.md § 3.4
 */

import { existsSync, readFileSync } from 'node:fs';
import { analyzeScope } from '../core/scope-analyzer.js';
import { loadConfigAsync, applyConfigOverrides, resolveKhalaConfig } from '../core/config-loader.js';
import { detectPlatform, getProfileForPlatform } from '../profiles/detector.js';
import { lintApiSpec } from '../core/api-linter.js';
import { generateReviewChecklist } from '../core/review-checklist.js';
import { logger } from '../utils/logger.js';
import { getChangedFiles, getDiffLines, getBaseFileContent } from '../utils/git.js';
import { KhalaClient } from '../khala/client.js';
import { analyzeImpact } from '../khala/impact-analyzer.js';
import { runTroubleshoot } from '../core/troubleshoot.js';
import { parseArgs, parseTroubleshootArgs, parseReviewGroundArgs } from './parse-args.js';
import {
  formatScopeMarkdown,
  formatScopeBrief,
  formatLintMarkdown,
  formatDiffMarkdown,
  formatReviewMarkdown,
  formatGroundingPackMarkdown,
  formatGroundingPackBrief,
  formatReviewGroundingPackMarkdown,
  formatReviewGroundingPackBrief,
} from './formatters.js';
import { buildChangedEntities, runReviewGround } from '../core/review-ground.js';

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
    logger.warn(`플랫폼을 감지할 수 없습니다 (Platform not detected). probe.config.ts에서 platform을 지정하세요.`);
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

// ─── Khala Commands (v0.4) ───

async function runKhalaSearch(args: string[]): Promise<void> {
  const query = args.filter((a) => !a.startsWith('--')).join(' ');
  if (!query) {
    logger.error('검색 쿼리를 입력하세요 (Usage: probe khala:search <query>)');
    process.exitCode = 1;
    return;
  }

  const config = await loadConfigAsync();
  const khalaConfig = resolveKhalaConfig(config);

  if (khalaConfig.disabled) {
    logger.warn('칼라 연동이 비활성화되어 있습니다');
    return;
  }

  const client = new KhalaClient(khalaConfig);
  const available = await client.isAvailable();
  if (!available) {
    logger.error('칼라 서버에 연결할 수 없습니다 (Cannot connect to Khala)');
    process.exitCode = 1;
    return;
  }

  const result = await client.search(query, { topK: khalaConfig.searchTopK });
  if (!result || result.results.length === 0) {
    logger.info('검색 결과가 없습니다');
    return;
  }

  const format = parseArgs(args).format;
  if (format === 'json') {
    logger.info(JSON.stringify(result, null, 2));
  } else {
    logger.info(`🔍 칼라 검색 결과 (${result.results.length}건)\n`);
    for (const hit of result.results) {
      logger.info(`  📄 ${hit.doc_title} > ${hit.section_path}`);
      logger.info(`     ${hit.snippet.slice(0, 120)}...`);
      logger.info(`     score: ${hit.score.toFixed(3)} | ${hit.classification}\n`);
    }
  }
}

async function runKhalaImpact(args: string[]): Promise<void> {
  const config = await loadConfigAsync();
  const khalaConfig = resolveKhalaConfig(config);

  if (khalaConfig.disabled) {
    logger.warn('칼라 연동이 비활성화되어 있습니다');
    return;
  }

  const client = new KhalaClient(khalaConfig);
  const available = await client.isAvailable();
  if (!available) {
    logger.error('칼라 서버에 연결할 수 없습니다');
    process.exitCode = 1;
    return;
  }

  // 현재 변경에서 서비스명 추출
  const options = parseArgs(args);
  const { profile } = await resolveProfileForCli(config);
  if (!profile) {
    logger.error('플랫폼을 감지할 수 없습니다');
    process.exitCode = 1;
    return;
  }

  const changedFiles = getChangedFiles(options.base);
  const diffLines = getDiffLines(options.base);
  const scopeResult = analyzeScope(changedFiles, profile, diffLines);

  const { extractServiceNames } = await import('../khala/context-enricher.js');
  const serviceNames = extractServiceNames(scopeResult.groups);

  if (serviceNames.length === 0) {
    logger.info('변경에서 서비스명을 추출할 수 없습니다');
    return;
  }

  const impact = await analyzeImpact(client, serviceNames, { hops: khalaConfig.graphHops });

  const format = options.format;
  if (format === 'json') {
    logger.info(JSON.stringify(impact, null, 2));
  } else {
    logger.info(`📊 영향 분석: ${impact.summary}\n`);
    if (impact.directImpact.length > 0) {
      logger.info('  직접 영향:');
      for (const svc of impact.directImpact) {
        const obs = svc.observed ? ` (${svc.observed.callCount}회, error ${(svc.observed.errorRate * 100).toFixed(1)}%)` : '';
        logger.info(`    → ${svc.name} [${svc.relationship}]${obs}`);
      }
    }
    if (impact.indirectImpact.length > 0) {
      logger.info('  간접 영향:');
      for (const svc of impact.indirectImpact) {
        logger.info(`    → ${svc.name} [${svc.relationship}]`);
      }
    }
  }
}

async function runKhalaStatus(): Promise<void> {
  const config = await loadConfigAsync();
  const khalaConfig = resolveKhalaConfig(config);

  if (khalaConfig.disabled) {
    logger.info('칼라 연동: 비활성화');
    return;
  }

  logger.info(`칼라 서버: ${khalaConfig.baseUrl}`);

  const client = new KhalaClient(khalaConfig);
  const available = await client.isAvailable();

  if (available) {
    logger.info('연결 상태: ✅ 정상');
  } else {
    logger.info('연결 상태: ❌ 연결 불가');
  }
}

/**
 * troubleshoot 커맨드 — 에러/스택트레이스 → Grounding Pack
 */
async function runTroubleshootCmd(args: string[]): Promise<void> {
  const o = parseTroubleshootArgs(args);

  // 인자 우선, 없으면 stdin (파이프) fallback (스펙 Q4)
  let signal = o.signal;
  if (!signal && !process.stdin.isTTY) {
    try {
      signal = readFileSync(0, 'utf-8').trim();
    } catch {
      // stdin 읽기 실패 시 무시 (아래 빈 신호 안내로 처리)
    }
  }
  if (!signal) {
    logger.error('에러 신호를 입력하세요 (Usage: probe troubleshoot "<에러/스택트레이스>" [--kind] [--suspect] [--diff-base])');
    process.exitCode = 1;
    return;
  }

  const config = await loadConfigAsync();
  const khalaConfig = resolveKhalaConfig(config);
  const client = new KhalaClient(khalaConfig);

  let changedServices: { service: string; changedFiles: string[] }[] | undefined;
  if (o.diffBase) {
    const { profile } = await resolveProfileForCli(config);
    if (profile) {
      const changedFiles = getChangedFiles(o.diffBase);
      const scope = analyzeScope(changedFiles, profile, getDiffLines(o.diffBase));
      const { extractServiceNames, fileBelongsToService } = await import('../khala/context-enricher.js');
      changedServices = extractServiceNames(scope.groups).map((service) => ({
        service,
        changedFiles: changedFiles.filter((f) => fileBelongsToService(f, service)),
      }));
    }
  }

  const result = await runTroubleshoot(
    { signal, kind: o.kind, diffBase: o.diffBase, suspectServices: o.suspectServices },
    client,
    changedServices,
  );

  if (!result.ok) {
    logger.error(result.reason);
    process.exitCode = 1;
    return;
  }

  switch (o.format) {
    case 'json':
      logger.info(JSON.stringify(result.pack, null, 2));
      break;
    case 'brief':
      logger.info(formatGroundingPackBrief(result.pack));
      break;
    case 'markdown':
    default:
      logger.info(formatGroundingPackMarkdown(result.pack));
      break;
  }
}

/**
 * review:ground 커맨드 — git diff → Review Grounding Pack
 */
async function runReviewGroundCmd(args: string[]): Promise<void> {
  const o = parseReviewGroundArgs(args);
  const config = await loadConfigAsync();
  const { profile } = await resolveProfileForCli(config);
  if (!profile) {
    logger.error('플랫폼을 감지할 수 없습니다 (Platform not detected)');
    process.exitCode = 1;
    return;
  }

  const changedFiles = getChangedFiles(o.base);
  if (changedFiles.length === 0) {
    logger.info('변경 파일이 없습니다 (No changed files).');
    return;
  }

  const scope = analyzeScope(changedFiles, profile, getDiffLines(o.base));
  const entities = buildChangedEntities(scope.groups, changedFiles);

  const khalaConfig = resolveKhalaConfig(config);
  const client = new KhalaClient(khalaConfig);
  const result = await runReviewGround(entities, client, {
    searchTopK: khalaConfig.searchTopK, graphHops: khalaConfig.graphHops,
  });

  if (!result.ok) {
    logger.error(result.reason);
    process.exitCode = 1;
    return;
  }

  switch (o.format) {
    case 'json': logger.info(JSON.stringify(result.pack, null, 2)); break;
    case 'brief': logger.info(formatReviewGroundingPackBrief(result.pack)); break;
    case 'markdown':
    default: logger.info(formatReviewGroundingPackMarkdown(result.pack)); break;
  }
}

/**
 * CLI용 프로파일 resolve 헬퍼.
 */
async function resolveProfileForCli(config: Awaited<ReturnType<typeof loadConfigAsync>>) {
  const configPlatform = config.platform;
  const platform = configPlatform && configPlatform !== 'custom'
    ? configPlatform
    : detectPlatform();

  const baseProfile = configPlatform === 'custom' && config.customProfile
    ? config.customProfile
    : getProfileForPlatform(platform);

  if (!baseProfile) return { profile: null, platform };

  const profile = applyConfigOverrides(baseProfile, config);
  return { profile, platform };
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
  case 'khala:search':
    void runKhalaSearch(args.slice(1));
    break;
  case 'khala:impact':
    void runKhalaImpact(args.slice(1));
    break;
  case 'khala:status':
    void runKhalaStatus();
    break;
  case 'troubleshoot':
    void runTroubleshootCmd(args.slice(1));
    break;
  case 'review:ground':
    void runReviewGroundCmd(args.slice(1));
    break;
  case 'version':
    logger.info('probe v0.6.0');
    break;
  default:
    logger.info(`\u2699\uFE0F Probe \u2014 프로덕트 개발 워크플로 자동 검증 도구

Usage:
  probe check          현재 브랜치의 변경 범위 + 리뷰 체크리스트
  probe api:lint        API 스펙 린트
  probe api:diff        API 스펙 diff (breaking 변경 감지)
  probe review          리뷰 체크리스트 생성
  probe khala:search    칼라 지식베이스 검색
  probe khala:impact    서비스 영향 분석
  probe khala:status    칼라 연결 상태 확인
  probe troubleshoot    에러/스택트레이스 → 트러블슈팅 그라운딩
  probe review:ground   git diff → 리뷰 그라운딩 (설계-관측 갭·규정·토폴로지·승인 스펙)
  probe version         버전 출력

Options:
  --base <ref>       기준 브랜치 (기본: origin/main)
  --format <type>    출력 형식: markdown | json | brief
  --spec <path>      API 스펙 파일 경로
  --silent           경고 없을 때 출력 없음`);
}
