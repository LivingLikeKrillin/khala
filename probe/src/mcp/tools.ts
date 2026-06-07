/**
 * MCP 도구 핸들러
 *
 * Probe 코어 엔진을 MCP 도구로 노출한다.
 * 8개 도구: analyzeScope, lintApiSpec, diffApiSpecs, reviewChecklist, detectPlatform, queryNexus, groundTroubleshooting, groundReview
 *
 * 규정 문서: docs/probe-v0.3-scope.md § 3, docs/probe-v0.4-scope.md § 6
 */

import { z } from 'zod';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { analyzeScope } from '../core/scope-analyzer.js';
import { loadConfigAsync, applyConfigOverrides, resolveNexusConfig } from '../core/config-loader.js';
import { detectPlatform, getProfileForPlatform } from '../profiles/detector.js';
import { generateReviewChecklist } from '../core/review-checklist.js';
import { lintSpec } from '../api/spec-linter.js';
import { diffSpecs } from '../api/spec-differ.js';
import { parseOpenApiSpec, parseOpenApiSpecFromString } from '../api/openapi-parser.js';
import { getChangedFiles, getDiffLines, getBaseFileContent } from '../utils/git.js';
import { enrichWithNexus } from '../nexus/context-enricher.js';
import { NexusClient } from '../nexus/client.js';
import { runTroubleshoot } from '../core/troubleshoot.js';
import { runReviewGround, buildChangedEntities } from '../core/review-ground.js';
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
 * MCP 서버에 8개 도구를 등록한다.
 */
export function registerTools(server: McpServer): void {
  // ─── probe.analyzeScope ───
  server.tool(
    'probe.analyzeScope',
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

      // v0.4: Nexus 컨텍스트 보강
      const nexusConfig = resolveNexusConfig(config);
      let nexusEnrichment = null;
      if (!nexusConfig.disabled) {
        nexusEnrichment = await enrichWithNexus(result.groups, filteredFiles, {
          nexusConfig,
          searchTopK: nexusConfig.searchTopK,
          graphHops: nexusConfig.graphHops,
        });
      }

      return { content: [{ type: 'text' as const, text: JSON.stringify({ ...result, nexusEnrichment }, null, 2) }] };
    },
  );

  // ─── probe.lintApiSpec ───
  server.tool(
    'probe.lintApiSpec',
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

  // ─── probe.diffApiSpecs ───
  server.tool(
    'probe.diffApiSpecs',
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

  // ─── probe.reviewChecklist ───
  server.tool(
    'probe.reviewChecklist',
    '변경 내용을 분석하여 PR 타입을 추론하고, 해당 타입의 리뷰 체크리스트를 생성한다. Nexus가 가용하면 관련 규정과 영향 분석을 포함한다.',
    {
      base: z.string().optional().describe('기준 브랜치 (기본: origin/main)'),
      enrichWithNexus: z.boolean().optional().describe('Nexus 맥락 보강 여부 (기본: true)'),
    },
    async ({ base, enrichWithNexus: shouldEnrich }) => {
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

      // v0.4: Nexus 컨텍스트 보강
      const nexusConfig = resolveNexusConfig(config);
      let nexusEnrichment = null;
      if ((shouldEnrich ?? true) && !nexusConfig.disabled) {
        nexusEnrichment = await enrichWithNexus(scopeResult.groups, filteredFiles, {
          nexusConfig,
          searchTopK: nexusConfig.searchTopK,
          graphHops: nexusConfig.graphHops,
        });
      }

      return { content: [{ type: 'text' as const, text: JSON.stringify({ ...checklist, nexusEnrichment }, null, 2) }] };
    },
  );

  // ─── probe.detectPlatform ───
  server.tool(
    'probe.detectPlatform',
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

  // ─── probe.queryNexus ───
  server.tool(
    'probe.queryNexus',
    'Nexus 지식베이스에 자연어로 질의한다. 규정, 아키텍처, 서비스 관계를 검색한다.',
    {
      query: z.string().describe('검색 쿼리 (자연어, 한국어/영어)'),
      mode: z.enum(['search', 'answer', 'graph', 'diff']).optional().describe('검색 모드 (기본: search)'),
      entityName: z.string().optional().describe('그래프/diff 모드에서 대상 엔티티명'),
    },
    async ({ query, mode, entityName }) => {
      const config = await loadConfigAsync();
      const nexusConfig = resolveNexusConfig(config);

      if (nexusConfig.disabled) {
        return { content: [{ type: 'text' as const, text: 'Nexus 연동이 비활성화되어 있습니다 (Nexus integration disabled)' }] };
      }

      const client = new NexusClient({
        baseUrl: nexusConfig.baseUrl,
        timeoutMs: nexusConfig.timeoutMs,
        tenant: nexusConfig.tenant,
        classificationMax: nexusConfig.classificationMax,
      });

      const available = await client.isAvailable();
      if (!available) {
        return { content: [{ type: 'text' as const, text: 'Nexus 서버에 연결할 수 없습니다 (Cannot connect to Nexus server)' }] };
      }

      const selectedMode = mode ?? 'search';

      switch (selectedMode) {
        case 'search': {
          const result = await client.search(query, { topK: nexusConfig.searchTopK });
          return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
        }
        case 'answer': {
          const result = await client.searchAnswer(query, { topK: nexusConfig.searchTopK });
          return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
        }
        case 'graph': {
          if (!entityName) {
            return { content: [{ type: 'text' as const, text: '그래프 모드에는 entityName이 필요합니다' }] };
          }
          const result = await client.getGraph(entityName, { hops: nexusConfig.graphHops });
          return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
        }
        case 'diff': {
          const result = await client.getDiff();
          return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
        }
        default:
          return { content: [{ type: 'text' as const, text: `알 수 없는 모드: ${selectedMode as string}` }] };
      }
    },
  );

  // ─── probe.groundTroubleshooting (v0.5) ───
  server.tool(
    'probe.groundTroubleshooting',
    '에러/스택트레이스/실패 테스트를 받아 조직 컨텍스트(토폴로지·관측·설계-관측 갭·규정)를 묶은 Grounding Pack을 반환한다. 근본원인은 단정하지 않는다 — 추론은 호출자가 한다.',
    {
      signal: z.string().describe('에러 메시지 | 스택트레이스 | 실패 테스트 출력 | 인시던트 설명'),
      kind: z.enum(['stacktrace', 'error', 'test-failure', 'incident']).optional().describe('신호 종류 힌트 (생략 시 자동 추론)'),
      suspectServices: z.array(z.string()).optional().describe('사용자가 지목한 의심 서비스'),
      diffBase: z.string().optional().describe('최근 변경 상관 분석용 git base (예: origin/main)'),
    },
    async ({ signal, kind, suspectServices, diffBase }) => {
      const config = await loadConfigAsync();
      const nexusConfig = resolveNexusConfig(config);
      const client = new NexusClient(nexusConfig);
      const result = await runTroubleshoot({ signal, kind, suspectServices, diffBase }, client);
      const payload = result.ok ? result.pack : { error: result.reason };
      return { content: [{ type: 'text' as const, text: JSON.stringify(payload, null, 2) }] };
    },
  );

  // ─── probe.groundReview (v0.6) ───
  server.tool(
    'probe.groundReview',
    'git diff를 받아 변경 엔티티의 조직 컨텍스트(설계-관측 갭·규정·토폴로지·승인 스펙·claim drift)를 묶은 Review Grounding Pack을 반환한다. diff의 소스 의미 분석/정합 판정은 하지 않는다 — 그건 호출자(Claude)가 한다.',
    {
      base: z.string().optional().describe('git diff base (예: origin/main)'),
    },
    async ({ base }) => {
      const { profile, config } = await resolveProfile();
      if (!profile) {
        return { content: [{ type: 'text' as const, text: '플랫폼을 감지할 수 없습니다 (Platform not detected)' }] };
      }
      const changedFiles = getChangedFiles(base);
      if (changedFiles.length === 0) {
        return { content: [{ type: 'text' as const, text: JSON.stringify({ error: '변경 파일 없음 (No changed files)' }) }] };
      }
      const scope = analyzeScope(changedFiles, profile, getDiffLines(base));
      const entities = buildChangedEntities(scope.groups, changedFiles);
      const nexusConfig = resolveNexusConfig(config);
      const client = new NexusClient(nexusConfig);
      const result = await runReviewGround(entities, client, {
        searchTopK: nexusConfig.searchTopK, graphHops: nexusConfig.graphHops,
      });
      const payload = result.ok ? result.pack : { error: result.reason };
      return { content: [{ type: 'text' as const, text: JSON.stringify(payload, null, 2) }] };
    },
  );
}
