/**
 * 리뷰 체크리스트 — 코어 오케스트레이터
 *
 * v0.1의 scope 분석 결과를 받아서 PR 타입을 추론하고,
 * 해당 타입의 DoD 체크리스트를 생성한다.
 *
 * 규정 문서: docs/probe-v0.2-scope.md § 3.3
 */

import type { ScopeAnalysisResult } from './scope-analyzer.js';
import { detectPrType } from '../review/pr-type-detector.js';
import { generateChecklist } from '../review/checklist-generator.js';
import type { ReviewChecklist } from '../review/types.js';

/** 리뷰 옵션 */
export interface ReviewOptions {
  /** 비활성화할 PR 타입 체크리스트 */
  disableChecklists?: string[];

  /** 커스텀 체크리스트 항목 */
  customItems?: Record<string, Array<{ id: string; description: string }>>;

  /** API 스펙 파일 변경 여부 */
  hasApiSpecChange?: boolean;
}

/**
 * scope 분석 결과를 기반으로 리뷰 체크리스트를 생성한다.
 *
 * @param scopeResult v0.1 scope 분석 결과
 * @param changedFiles 변경된 파일 목록
 * @param options 리뷰 옵션
 * @returns 리뷰 체크리스트
 */
export function generateReviewChecklist(
  scopeResult: ScopeAnalysisResult,
  changedFiles: string[],
  options?: ReviewOptions,
): ReviewChecklist {
  // 파일 역할 추출
  const roles = scopeResult.groups.flatMap((g) =>
    g.files.map((f) => f.role),
  );

  // PR 타입 추론
  const prType = detectPrType(roles, options?.hasApiSpecChange ?? false);

  // 체크리스트 생성
  return generateChecklist(prType, {
    disableChecklists: options?.disableChecklists,
    customItems: options?.customItems,
    changedFiles,
  });
}
