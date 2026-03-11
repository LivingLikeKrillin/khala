/**
 * MCP 도구 핸들러
 *
 * Karax 코어 엔진을 MCP 도구로 노출한다.
 * 5개 도구: analyzeScope, lintApiSpec, diffApiSpecs, reviewChecklist, detectPlatform
 *
 * 규정 문서: docs/karax-v0.3-scope.md § 3
 */

import { z } from 'zod';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { analyzeScope } from '../core/scope-analyzer.js';
import { loadConfigAsync, applyConfigOverrides } from '../core/config-loader.js';
import { detectPlatform, getProfileForPlatform } from '../profiles/detector.js';
import { generateReviewChecklist } from '../core/review-checklist.js';
import { lintSpec } from '../api/spec-linter.js';
import { diffSpecs } from '../api/spec-differ.js';
import { parseOpenApiSpec, parseOpenApiSpecFromString } from '../api/openapi-parser.js';
import { getChangedFiles, getDiffLines, getBaseFileContent } from '../utils/git.js';
import { existsSync } from 'node:fs';

/**
 * 프로파일을 resolve한다 (config + 자동감지).
 */
async function resolveProfile() {
  const config = await loadConfigAsync();
  const configPlatform = config.platform;
  const platform = configPlatform && configPlatform !== 'custom'
    ? configPlatform
    : detectPlatform();

  const baseProfile = configPlatform === 'custom' && config.customProfile
    ? config.customProfile
    : getProfileForPlatform(platform);

  if (!baseProfile) return { profile: null, config, platform };

  const profile = applyConfigOverrides(baseProfile, config);
  return { profile, config, platform };
}

/**
 * MCP 서버에 5개 도구를 등록한다.
 */
export function registerTools(server: McpServer): void {
  // ─── karax.analyzeScope ───
  server.tool(
    'karax.analyzeScope',
    '변경 파일 목록으로 PR 범위를 분석한다. 응집 그룹, 관심사 혼재, 분할 제안을 반환한다.',
    {
      base: z.string().optional().describe('기준 브랜치 (기본: origin/main)'),
      files: z.array(z.string()).optional().describe('분석할 파일 목록 (미지정 시 git diff로 자동 수집)'),
    },
    async ({ base, files }) => {
      const { profile, config } = await resolveProfile();
      if (!profile) {
        return { content: [{ type: 'text' as const, text: '플랫폼을 감지할 수 없습니다 (Platform not detected)' }] };
      }

      const baseRef = base ?? 'origin/main';
      const changedFiles = files ?? getChangedFiles(baseRef);

      const filteredFiles = config.ignore
        ? changedFiles.filter((f) => !config.ignore!.some((p) => f.includes(p)))
        : changedFiles;

      const diffLines = getDiffLines(baseRef);
      const result = analyzeScope(filteredFiles, profile, diffLines);

      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  // ─── karax.lintApiSpec ───
  server.tool(
    'karax.lintApiSpec',
    'OpenAPI 스펙 파일의 품질을 검증한다. 10개 내장 룰로 필드 타입, nullable, 에러 응답, 네이밍 규칙을 검사한다.',
    {
      specPath: z.string().optional().describe('OpenAPI 스펙 파일 경로 (기본: api/openapi.json)'),
    },
    async ({ specPath }) => {
      const config = await loadConfigAsync();
      const path = specPath ?? config.api?.specPath ?? 'api/openapi.json';

      if (!existsSync(path)) {
        return { content: [{ type: 'text' as const, text: `API 스펙 파일을 찾을 수 없습니다 (API spec not found): ${path}` }] };
      }

      const spec = parseOpenApiSpec(path);
      const result = lintSpec(spec, path, {
        disableRules: config.api?.disableRules,
        ruleSeverity: config.api?.ruleSeverity,
      });

      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  // ─── karax.diffApiSpecs ───
  server.tool(
    'karax.diffApiSpecs',
    '기준 브랜치와 현재 브랜치의 API 스펙을 비교한다. breaking 변경, additive 변경, deprecation을 분류한다.',
    {
      base: z.string().optional().describe('기준 브랜치 (기본: origin/main)'),
      specPath: z.string().optional().describe('스펙 파일 경로 (기본: api/openapi.json)'),
    },
    async ({ base, specPath }) => {
      const config = await loadConfigAsync();
      const baseRef = base ?? 'origin/main';
      const path = specPath ?? config.api?.specPath ?? 'api/openapi.json';

      if (!existsSync(path)) {
        return { content: [{ type: 'text' as const, text: `API 스펙 파일을 찾을 수 없습니다: ${path}` }] };
      }

      const baseContent = getBaseFileContent(baseRef, path);
      if (!baseContent) {
        return { content: [{ type: 'text' as const, text: `기준 브랜치에서 스펙 파일을 찾을 수 없습니다: ${baseRef}:${path}` }] };
      }

      const baseSpec = parseOpenApiSpecFromString(baseContent);
      const headSpec = parseOpenApiSpec(path);
      const result = diffSpecs(baseSpec, headSpec);

      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  // ─── karax.reviewChecklist ───
  server.tool(
    'karax.reviewChecklist',
    '변경 내용을 분석하여 PR 타입을 추론하고, 해당 타입의 리뷰 체크리스트를 생성한다.',
    {
      base: z.string().optional().describe('기준 브랜치 (기본: origin/main)'),
    },
    async ({ base }) => {
      const { profile, config } = await resolveProfile();
      if (!profile) {
        return { content: [{ type: 'text' as const, text: '플랫폼을 감지할 수 없습니다' }] };
      }

      const baseRef = base ?? 'origin/main';
      const changedFiles = getChangedFiles(baseRef);

      const filteredFiles = config.ignore
        ? changedFiles.filter((f) => !config.ignore!.some((p) => f.includes(p)))
        : changedFiles;

      const diffLines = getDiffLines(baseRef);
      const scopeResult = analyzeScope(filteredFiles, profile, diffLines);

      const specPath = config.api?.specPath ?? 'api/openapi.json';
      const hasApiSpecChange = filteredFiles.some((f) => f.includes(specPath));

      const checklist = generateReviewChecklist(scopeResult, filteredFiles, {
        hasApiSpecChange,
        disableChecklists: config.review?.disableChecklists,
        customItems: config.review?.customItems,
      });

      return { content: [{ type: 'text' as const, text: JSON.stringify(checklist, null, 2) }] };
    },
  );

  // ─── karax.detectPlatform ───
  server.tool(
    'karax.detectPlatform',
    '프로젝트 파일 구조를 분석하여 플랫폼(spring-boot, nextjs, react-spa)을 감지한다.',
    {},
    async () => {
      const { profile, platform } = await resolveProfile();

      return {
        content: [{
          type: 'text' as const,
          text: JSON.stringify({ platform, profile }, null, 2),
        }],
      };
    },
  );
}
