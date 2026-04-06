/**
 * 체크리스트 생성기
 *
 * PR 타입을 기반으로 DoD 체크리스트를 생성하고,
 * 자동 검증 가능한 항목은 검증 결과를 제공한다.
 *
 * 규정 문서: docs/probe-v0.2-scope.md § 3.3
 */

import type { PrType, ReviewChecklist, ChecklistItem, VerifiedItem } from './types.js';
import { CHECKLISTS } from './checklists/index.js';

/** 체크리스트 생성 옵션 */
export interface ChecklistOptions {
  /** 비활성화할 PR 타입 (해당 타입은 체크리스트 미생성) */
  disableChecklists?: string[];

  /** 커스텀 체크리스트 항목 추가 */
  customItems?: Record<string, Array<{ id: string; description: string }>>;

  /** 변경된 파일 경로 목록 (자동 검증용) */
  changedFiles?: string[];
}

/**
 * PR 타입에 맞는 리뷰 체크리스트를 생성한다.
 *
 * @param prType PR 타입
 * @param options 체크리스트 옵션
 * @returns 리뷰 체크리스트
 */
export function generateChecklist(
  prType: PrType,
  options?: ChecklistOptions,
): ReviewChecklist {
  const disabled = new Set(options?.disableChecklists ?? []);

  if (disabled.has(prType)) {
    return {
      prType,
      items: [],
      autoVerified: [],
      manualRequired: [],
    };
  }

  // 기본 체크리스트 가져오기
  const baseItems = [...(CHECKLISTS[prType] ?? [])];

  // 커스텀 항목 추가
  const customItems = options?.customItems?.[prType] ?? [];
  for (const custom of customItems) {
    baseItems.push({
      id: custom.id,
      description: custom.description,
      automatable: false,
      priority: 'required',
    });
  }

  // 자동 검증 수행
  const autoVerified = runAutoVerification(baseItems, prType, options?.changedFiles ?? []);

  // 수동 확인 필요 항목 분류
  const verifiedIds = new Set(autoVerified.map((v) => v.id));
  const manualRequired = baseItems.filter((item) => !item.automatable || !verifiedIds.has(item.id));

  return {
    prType,
    items: baseItems,
    autoVerified,
    manualRequired,
  };
}

/**
 * 자동 검증 가능한 항목을 검증한다.
 */
function runAutoVerification(
  items: ChecklistItem[],
  prType: PrType,
  changedFiles: string[],
): VerifiedItem[] {
  const verified: VerifiedItem[] = [];
  const automatableItems = items.filter((item) => item.automatable);

  for (const item of automatableItems) {
    const result = verifyItem(item, prType, changedFiles);
    if (result) {
      verified.push(result);
    }
  }

  return verified;
}

/**
 * 개별 항목을 검증한다.
 */
function verifyItem(
  item: ChecklistItem,
  _prType: PrType,
  changedFiles: string[],
): VerifiedItem | undefined {
  switch (item.id) {
    case 'dc-service-test':
    case 'dc-controller-test':
    case 'gen-test': {
      const hasTestFile = changedFiles.some((f) =>
        f.includes('test') || f.includes('Test') || f.includes('spec') || f.includes('Spec'),
      );
      return {
        id: item.id,
        description: item.description,
        passed: hasTestFile,
        detail: hasTestFile
          ? `테스트 파일 발견 (test file found)`
          : `테스트 파일 없음 (no test file found)`,
      };
    }

    case 'uf-story':
    case 'uc-story':
    case 'ds-story': {
      const hasStory = changedFiles.some((f) =>
        f.includes('.stories.') || f.includes('.story.'),
      );
      return {
        id: item.id,
        description: item.description,
        passed: hasStory,
        detail: hasStory
          ? `스토리 파일 발견 (story file found)`
          : `스토리 파일 없음 (no story file found)`,
      };
    }

    default:
      return undefined;
  }
}
