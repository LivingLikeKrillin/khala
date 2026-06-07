/**
 * MCP 프롬프트 핸들러
 *
 * 사전 정의된 상호작용 템플릿.
 * 2개 프롬프트: prReview, splitPr
 *
 * 규정 문서: docs/probe-v0.3-scope.md § 5
 */

import { z } from 'zod';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { analyzeScope } from '../core/scope-analyzer.js';
import { loadConfigAsync, applyConfigOverrides, resolveKhalaConfig } from '../core/config-loader.js';
import { detectPlatform, getProfileForPlatform } from '../profiles/detector.js';
import { generateReviewChecklist } from '../core/review-checklist.js';
import { getChangedFiles, getDiffLines } from '../utils/git.js';
import { enrichWithKhala } from '../khala/context-enricher.js';

/**
 * MCP 서버에 프롬프트를 등록한다.
 */
export function registerPrompts(server: McpServer): void {
  // ─── probe.prReview ───
  server.prompt(
    'probe.prReview',
    '현재 변경에 대해 probe 분석 결과를 기반으로 구조화된 코드 리뷰를 수행한다.',
    { base: z.string().optional().describe('기준 브랜치 (기본: origin/main)') },
    async ({ base }) => {
      const baseRef = base ?? 'origin/main';

      const config = await loadConfigAsync();
      const configPlatform = config.platform;
      const platform = configPlatform && configPlatform !== 'custom'
        ? configPlatform
        : detectPlatform();

      const baseProfile = configPlatform === 'custom' && config.customProfile
        ? config.customProfile
        : getProfileForPlatform(platform);

      if (!baseProfile) {
        return {
          messages: [{
            role: 'user' as const,
            content: { type: 'text' as const, text: '플랫폼을 감지할 수 없어 PR 리뷰를 수행할 수 없습니다.' },
          }],
        };
      }

      const profile = applyConfigOverrides(baseProfile, config);
      const changedFiles = getChangedFiles(baseRef);
      const diffLines = getDiffLines(baseRef);
      const scopeResult = analyzeScope(changedFiles, profile, diffLines);

      const specPath = config.api?.specPath ?? 'api/openapi.json';
      const hasApiSpecChange = changedFiles.some((f) => f.includes(specPath));

      const checklist = generateReviewChecklist(scopeResult, changedFiles, {
        hasApiSpecChange,
        disableChecklists: config.review?.disableChecklists,
        customItems: config.review?.customItems,
      });

      // v0.4: 칼라 컨텍스트 보강
      const khalaConfig = resolveKhalaConfig(config);
      let khalaEnrichment = null;
      if (!khalaConfig.disabled) {
        khalaEnrichment = await enrichWithKhala(scopeResult.groups, changedFiles, {
          khalaConfig,
          searchTopK: khalaConfig.searchTopK,
          graphHops: khalaConfig.graphHops,
        });
      }

      const analysisJson = JSON.stringify({ scope: scopeResult, checklist, khalaEnrichment }, null, 2);

      // 칼라 맥락 섹션 생성
      let khalaSection = '';
      if (khalaEnrichment?.khalaAvailable) {
        const parts: string[] = [];
        if (khalaEnrichment.relevantDocs.length > 0) {
          parts.push('### 관련 규정');
          for (const doc of khalaEnrichment.relevantDocs) {
            parts.push(`- ${doc.docTitle} > ${doc.sectionPath}: "${doc.snippet.slice(0, 100)}..."`);
          }
        }
        if (khalaEnrichment.impactedServices.length > 0) {
          parts.push('### 영향 서비스');
          for (const svc of khalaEnrichment.impactedServices) {
            const obs = svc.observed ? ` (${svc.observed.callCount}회/일, error ${(svc.observed.errorRate * 100).toFixed(1)}%)` : '';
            parts.push(`- ${svc.name} [${svc.relationship}]${obs}`);
          }
        }
        if (khalaEnrichment.designObservationGaps.length > 0) {
          parts.push('### 설계-관측 갭');
          for (const gap of khalaEnrichment.designObservationGaps) {
            parts.push(`- ${gap.flag}: ${gap.fromName} → ${gap.toName} (${gap.edgeType}) — ${gap.detail}`);
          }
        }
        if (parts.length > 0) {
          khalaSection = `\n\n## 칼라 맥락 (Khala Context)\n\n${parts.join('\n')}`;
        }
      }

      return {
        messages: [{
          role: 'user' as const,
          content: {
            type: 'text' as const,
            text: `다음은 Probe가 분석한 현재 PR의 범위와 리뷰 체크리스트입니다.
이 분석 결과를 기반으로 구조화된 코드 리뷰를 수행해주세요.

## Probe 분석 결과
\`\`\`json
${analysisJson}
\`\`\`${khalaSection}

## 리뷰 지침
1. PR 타입(${checklist.prType})과 범위를 먼저 요약하세요.
2. 자동 검증된 항목은 결과만 보고하세요.
3. 수동 확인 필요 항목에 대해 코드를 읽고 판단하세요.
4. 칼라 맥락이 있으면 관련 규정 근거를 인용하세요.
5. 영향 서비스가 있으면 하위 호환성을 확인하세요.
6. 피드백을 blocker / suggestion / nit으로 분류하세요.
7. 각 피드백에 파일 경로와 라인 번호를 포함하세요.
8. 규정 근거가 있으면 명시하세요 (규정 ① ② ③).`,
          },
        }],
      };
    },
  );

  // ─── probe.splitPr ───
  server.prompt(
    'probe.splitPr',
    '현재 변경을 여러 PR로 분할하는 방법을 안내한다.',
    { base: z.string().optional().describe('기준 브랜치 (기본: origin/main)') },
    async ({ base }) => {
      const baseRef = base ?? 'origin/main';

      const config = await loadConfigAsync();
      const configPlatform = config.platform;
      const platform = configPlatform && configPlatform !== 'custom'
        ? configPlatform
        : detectPlatform();

      const baseProfile = configPlatform === 'custom' && config.customProfile
        ? config.customProfile
        : getProfileForPlatform(platform);

      if (!baseProfile) {
        return {
          messages: [{
            role: 'user' as const,
            content: { type: 'text' as const, text: '플랫폼을 감지할 수 없어 PR 분할을 안내할 수 없습니다.' },
          }],
        };
      }

      const profile = applyConfigOverrides(baseProfile, config);
      const changedFiles = getChangedFiles(baseRef);
      const diffLines = getDiffLines(baseRef);
      const scopeResult = analyzeScope(changedFiles, profile, diffLines);

      const analysisJson = JSON.stringify(scopeResult, null, 2);

      return {
        messages: [{
          role: 'user' as const,
          content: {
            type: 'text' as const,
            text: `다음은 Probe가 분석한 현재 변경의 범위입니다.
이 분석 결과를 기반으로 PR 분할 방법을 안내해주세요.

## Probe 범위 분석
\`\`\`json
${analysisJson}
\`\`\`

## 분할 안내 지침
1. 각 그룹이 어떤 관심사인지 설명하세요.
2. 분할 제안이 있으면 머지 순서를 포함하세요.
3. 의존 관계가 있는 그룹은 순서를 지켜야 합니다 (인프라 → 데이터 → 로직 → UI).
4. git 명령어 가이드를 제공하세요 (stash, cherry-pick, branch 생성).
5. 분할이 불필요하면 (severity: ok) 그대로 진행하라고 안내하세요.`,
          },
        }],
      };
    },
  );
}
