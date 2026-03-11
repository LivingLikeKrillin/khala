/**
 * 리뷰 체크리스트 타입 정의
 *
 * PR 타입 추론 및 체크리스트 생성에 사용되는 타입.
 *
 * 규정 문서: docs/karax-v0.2-scope.md § 3.3
 */

/** PR 타입 */
export type PrType =
  | 'domain-crud'
  | 'api-change'
  | 'config-change'
  | 'db-migration'
  | 'ui-feature'
  | 'ui-component'
  | 'design-system'
  | 'test-only'
  | 'docs-only'
  | 'general';

/** 리뷰 체크리스트 */
export interface ReviewChecklist {
  /** 추론된 PR 타입 */
  prType: PrType;

  /** 체크리스트 항목 */
  items: ChecklistItem[];

  /** 자동 검증된 항목 (karax가 확인 가능한 것) */
  autoVerified: VerifiedItem[];

  /** 수동 확인 필요 항목 */
  manualRequired: ChecklistItem[];
}

/** 체크리스트 항목 */
export interface ChecklistItem {
  /** 항목 ID */
  id: string;

  /** 설명 */
  description: string;

  /** 자동 검증 가능 여부 */
  automatable: boolean;

  /** 규정 근거 */
  guidelineRef?: string;

  /** 필수/권장 */
  priority: 'required' | 'recommended';
}

/** 자동 검증된 항목 */
export interface VerifiedItem {
  /** 항목 ID */
  id: string;

  /** 설명 */
  description: string;

  /** 검증 결과 */
  passed: boolean;

  /** 상세 메시지 */
  detail?: string;
}
