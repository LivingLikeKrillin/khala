/**
 * 관심사 드리프트 감지
 *
 * 방금 편집한 파일이 기존 변경의 주된 관심사와 다른지 판단한다.
 * PostToolUse 훅에서 호출되어, 관심사가 달라지는 순간 알려준다.
 *
 * 예: "지금까지 User CRUD를 작업 중이었는데,
 *      방금 편집한 AppConfig.kt는 config-change 관심사입니다."
 */

import { analyzeScope } from './scope-analyzer.js';
import type { DetectedGroup } from './scope-analyzer.js';
import type { PlatformProfile } from '../profiles/types.js';

export interface DriftResult {
  /** 드리프트가 감지되었는지 */
  drifted: boolean;

  /** 주된 관심사 그룹 (파일 수 기준) */
  primaryGroup: string | null;

  /** 방금 편집한 파일이 속하는 그룹 */
  editedFileGroup: string | null;

  /** 사용자에게 보여줄 메시지 (드리프트 시에만) */
  message: string | null;
}

/**
 * 방금 편집한 파일의 관심사가 기존 변경과 다른지 감지한다.
 *
 * @param allChangedFiles 현재 브랜치에서 변경된 모든 파일
 * @param editedFile 방금 편집한 파일 경로
 * @param profile 플랫폼 프로파일
 */
export function detectConcernDrift(
  allChangedFiles: string[],
  editedFile: string,
  profile: PlatformProfile,
): DriftResult {
  const noDrift: DriftResult = {
    drifted: false,
    primaryGroup: null,
    editedFileGroup: null,
    message: null,
  };

  // 변경 파일이 2개 미만이면 드리프트 판단 불가
  if (allChangedFiles.length < 2) {
    return noDrift;
  }

  // 전체 변경을 분석
  const result = analyzeScope(allChangedFiles, profile);

  // 의미있는 그룹만 추출 (unmatched 중 파일이 있는 것도 포함)
  const meaningfulGroups = result.groups.filter(
    (g) => g.files.length > 0,
  );

  // 그룹이 1개 이하면 드리프트 없음
  if (meaningfulGroups.length <= 1) {
    return noDrift;
  }

  // 편집한 파일이 속하는 그룹 찾기
  const normalizedEdited = editedFile.replace(/\\/g, '/');
  const editedGroup = findGroupForFile(normalizedEdited, meaningfulGroups);

  if (!editedGroup) {
    return noDrift;
  }

  // 주된 관심사: 편집한 파일을 제외한 나머지에서 가장 파일 수가 많은 그룹
  const otherGroups = meaningfulGroups
    .map((g) => ({
      ...g,
      fileCount: g.files.filter((f) => f.path !== normalizedEdited).length,
    }))
    .filter((g) => g.fileCount > 0);

  if (otherGroups.length === 0) {
    return noDrift;
  }

  const primaryGroup = otherGroups.reduce((a, b) =>
    a.fileCount >= b.fileCount ? a : b,
  );

  // 같은 그룹이면 드리프트 아님
  const editedGroupKey = groupKey(editedGroup);
  const primaryGroupKey = groupKey(primaryGroup);

  if (editedGroupKey === primaryGroupKey) {
    return noDrift;
  }

  const primaryLabel = formatGroupLabel(primaryGroup);
  const editedLabel = formatGroupLabel(editedGroup);

  return {
    drifted: true,
    primaryGroup: primaryLabel,
    editedFileGroup: editedLabel,
    message: `⚠️ 현재 변경(${primaryLabel})과 다른 관심사(${editedLabel})입니다. 별도 PR로 분리할까요?`,
  };
}

/** 파일이 속하는 그룹을 찾는다. */
function findGroupForFile(filePath: string, groups: DetectedGroup[]): DetectedGroup | null {
  for (const group of groups) {
    if (group.files.some((f) => f.path === filePath)) {
      return group;
    }
  }
  return null;
}

/** 그룹의 고유 키를 생성한다. */
function groupKey(group: DetectedGroup): string {
  return `${group.groupName}:${group.cohesionKeyValue}`;
}

/** 그룹 라벨을 생성한다. */
function formatGroupLabel(group: DetectedGroup): string {
  if (group.groupName === 'unmatched') {
    return '기타 파일';
  }
  if (group.cohesionKeyValue === group.groupName ||
      group.cohesionKeyValue === 'default' ||
      group.cohesionKeyValue.endsWith('Group')) {
    return group.groupName;
  }
  return `${group.cohesionKeyValue} ${group.groupName}`;
}
