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
