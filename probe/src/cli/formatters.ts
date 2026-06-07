/**
 * CLI 출력 포맷터
 *
 * 분석 결과를 markdown / brief / json 형식으로 변환한다.
 * 순수 함수로 구성되어 테스트 가능.
 */

import type { ScopeAnalysisResult } from '../core/scope-analyzer.js';
import type { ApiLintResult, ApiDiffResult } from '../api/types.js';
import type { ReviewChecklist } from '../review/types.js';
import type { SeverityLevel } from '../profiles/types.js';
import type { GroundingPack, ReviewGroundingPack } from '../nexus/types.js';

export const SEVERITY_ICONS: Record<SeverityLevel, string> = {
  ok: '\u2705',
  info: '\u26A0\uFE0F',
  warn: '\uD83D\uDD36',
  error: '\uD83D\uDD34',
};

export const SEVERITY_LABELS: Record<SeverityLevel, string> = {
  ok: '정상 범위',
  info: '분리 권장',
  warn: 'PR 범위 경고',
  error: '강력 경고 — PR 분할 필요',
};

/**
 * 분석 결과를 마크다운 형식으로 포맷한다.
 */
export function formatScopeMarkdown(result: ScopeAnalysisResult, checklist?: ReviewChecklist): string {
  const icon = SEVERITY_ICONS[result.severity];
  const label = SEVERITY_LABELS[result.severity];
  const lines: string[] = [];

  lines.push(`${icon} Probe \u2014 ${label}`);
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
      const groupLabel =
        group.groupName === 'unmatched' ? '기타 파일' : `${group.groupName} (${group.cohesionKeyValue})`;

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
export function formatScopeBrief(result: ScopeAnalysisResult): string {
  const icon = SEVERITY_ICONS[result.severity];
  const label = SEVERITY_LABELS[result.severity];
  return `${icon} ${label} \u2014 ${result.totalFiles}개 파일, ${result.groups.length}개 그룹, ${result.mixedConcerns.length}개 혼재 경고`;
}

/**
 * API 린트 결과를 마크다운으로 포맷한다.
 */
export function formatLintMarkdown(result: ApiLintResult): string {
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
export function formatDiffMarkdown(result: ApiDiffResult): string {
  const lines: string[] = [];

  if (result.changes.length === 0) {
    lines.push(`\u2705 API diff \u2014 변경 없음`);
    return lines.join('\n');
  }

  const icon = result.summary.hasBreaking ? '\uD83D\uDD34' : '\u2705';
  const label = result.summary.hasBreaking ? 'breaking 변경 포함' : '호환 변경';
  lines.push(`${icon} API 변경 감지 \u2014 ${label}`);
  lines.push('');
  lines.push(
    `변경 요약: ${result.summary.added}개 추가, ${result.summary.modified}개 수정, ${result.summary.removed}개 삭제`,
  );
  lines.push('');

  for (const change of result.changes) {
    const changeIcon = change.breaking
      ? '\u26A0\uFE0F'
      : change.type === 'added'
        ? '\u2705'
        : change.type === 'removed'
          ? '\uD83D\uDD34'
          : change.type === 'deprecated'
            ? '\u26A0\uFE0F'
            : '\uD83D\uDD36';

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

/** GroundingPack → markdown (근본원인 단정 없이 증거만) */
export function formatGroundingPackMarkdown(pack: GroundingPack): string {
  const lines: string[] = [];
  lines.push(`## 🔬 트러블슈팅 그라운딩 (T${pack.tier})`);
  lines.push('');
  lines.push(`> ${pack.tierReason}`);
  lines.push('> ⚠️ 이건 근거 모음이지 근본원인 판정이 아닙니다 — 추론은 분석자/Claude가 합니다.');
  lines.push('');

  lines.push('### 의심 지점');
  for (const s of pack.suspects) {
    lines.push(`- \`${s.entityName}\` (confidence ${s.confidence.toFixed(2)})`);
  }
  lines.push('');

  if (pack.designObservationGaps?.length) {
    lines.push('### ⚠️ 설계-관측 갭 (제네릭 리뷰가 구조적으로 못 보는 발견)');
    for (const g of pack.designObservationGaps) {
      lines.push(`- **${g.flag}**: ${g.fromName} → ${g.toName} (${g.edgeType}) — ${g.detail}`);
      if (g.observedEvidence?.length) lines.push(`  - trace: ${g.observedEvidence.join(', ')}`);
    }
    lines.push('');
  }

  if (pack.operationalSignals?.length) {
    lines.push('### 운영 신호');
    for (const s of pack.operationalSignals) {
      lines.push(`- ${s.fromName} → ${s.toName}: ${s.anomaly} (${s.callCount}회, p95 ${s.latencyP95}ms)`);
    }
    lines.push('');
  }

  if (pack.topology) {
    lines.push(`### 토폴로지 영향: ${pack.topology.summary}`);
    lines.push('');
  }

  if (pack.knowledge?.length) {
    lines.push('### 관련 규정/문서');
    for (const d of pack.knowledge) lines.push(`- ${d.docTitle} > ${d.sectionPath} (score ${d.score.toFixed(2)})`);
    lines.push('');
  }

  if (pack.changeCorrelation?.length) {
    lines.push('### 최근 변경 상관');
    for (const c of pack.changeCorrelation) lines.push(`- ${c.service}: ${c.changedFiles.join(', ')}`);
    lines.push('');
  }

  if (pack.domainInvariants?.length) {
    lines.push('### 도메인 불변식 (Archon)');
    for (const c of pack.domainInvariants) {
      lines.push(
        `- \`${c.boundSymbol}\` → ${c.kind} \`${c.id}\` (${c.criticality}, status=${c.status}, drift=${c.codeDrift})`,
      );
    }
    lines.push('');
  }

  if (pack.caveats.length) {
    lines.push('### 한계 (caveats)');
    for (const c of pack.caveats) lines.push(`- ${c}`);
  }

  return lines.join('\n');
}

/** GroundingPack → 한 줄 요약 */
export function formatGroundingPackBrief(pack: GroundingPack): string {
  const names = pack.suspects.map((s) => s.entityName).join(', ') || '(국소화 실패)';
  const gaps = pack.designObservationGaps?.length ?? 0;
  return `트러블슈팅 T${pack.tier}: 의심 [${names}], 설계-관측 갭 ${gaps}개`;
}

/** ReviewGroundingPack → 마크다운 (증거만, 정합 판정은 Claude) */
export function formatReviewGroundingPackMarkdown(pack: ReviewGroundingPack): string {
  const lines: string[] = [];
  lines.push(`## 🧭 리뷰 그라운딩 (T${pack.tier})`);
  lines.push('');
  lines.push(`> ${pack.tierReason}`);
  lines.push('> ⚠️ 이건 조직 컨텍스트 증거 모음입니다 — diff↔스펙/그래프/claim 정합 판정은 Claude/리뷰어가 합니다.');
  lines.push('');
  lines.push('### 변경 엔티티');
  for (const e of pack.changedEntities) {
    lines.push(
      `- \`${e.entityName}\`${e.cohesionGroup ? ` (${e.cohesionGroup})` : ''} — ${e.changedFiles.length}개 파일`,
    );
  }
  lines.push('');
  if (pack.designObservationGaps?.length) {
    lines.push('### ⚠️ 설계-관측 갭 (제네릭 리뷰가 구조적으로 못 보는 발견)');
    for (const g of pack.designObservationGaps) {
      lines.push(`- **${g.flag}**: ${g.fromName} → ${g.toName} (${g.edgeType}) — ${g.detail}`);
      if (g.observedEvidence?.length) lines.push(`  - trace: ${g.observedEvidence.join(', ')}`);
    }
    lines.push('');
  }
  if (pack.specRefs?.length) {
    lines.push('### 승인 스펙 참조 (diff를 이 스펙에 비춰 검토)');
    for (const s of pack.specRefs) {
      lines.push(`- ${s.docTitle} > ${s.sectionPath}${s.approvedHash ? ` (hash ${s.approvedHash})` : ''}`);
    }
    lines.push('');
  }
  if (pack.applicableGuidelines?.length) {
    lines.push('### 적용 규정/문서');
    for (const d of pack.applicableGuidelines)
      lines.push(`- ${d.docTitle} > ${d.sectionPath} (score ${d.score.toFixed(2)})`);
    lines.push('');
  }
  if (pack.topology) {
    lines.push(`### 토폴로지 영향: ${pack.topology.summary}`);
    lines.push('');
  }
  if (pack.claimDrift?.length) {
    lines.push('### 도메인 claim drift (Archon)');
    for (const c of pack.claimDrift) {
      lines.push(
        `- \`${c.boundSymbol}\` → ${c.kind} \`${c.id}\` (${c.criticality}, status=${c.status}, drift=${c.codeDrift})`,
      );
    }
    lines.push('');
  }
  if (pack.caveats.length) {
    lines.push('### 한계 (caveats)');
    for (const c of pack.caveats) lines.push(`- ${c}`);
  }
  return lines.join('\n');
}

/** ReviewGroundingPack → 한 줄 요약 */
export function formatReviewGroundingPackBrief(pack: ReviewGroundingPack): string {
  const names = pack.changedEntities.map((e) => e.entityName).join(', ') || '(엔티티 없음)';
  const gaps = pack.designObservationGaps?.length ?? 0;
  const specs = pack.specRefs?.length ?? 0;
  return `리뷰 그라운딩 T${pack.tier}: 엔티티 [${names}], 설계-관측 갭 ${gaps}개, 승인 스펙 ${specs}개`;
}

/**
 * 리뷰 체크리스트를 마크다운으로 포맷한다.
 */
export function formatReviewMarkdown(checklist: ReviewChecklist): string {
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
