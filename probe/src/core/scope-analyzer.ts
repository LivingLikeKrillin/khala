/**
 * PR 범위 + 응집 그룹 분석 엔진
 *
 * v0.1 핵심 모듈. 변경 파일 목록을 받아서:
 * 1. 플랫폼 프로파일로 각 파일에 역할(role) 부여
 * 2. 응집 그룹(Cohesion Group) 매칭
 * 3. 경고 레벨 판단 + 분할 제안 생성
 *
 * 규정 문서: docs/probe-v0.1-scope.md § 3
 */

import type { PlatformProfile, SeverityLevel } from '../profiles/types.js';
import { globMatch } from '../utils/glob-match.js';

// ─── 결과 타입 ───

export interface ScopeAnalysisResult {
  /** 경고 레벨 */
  severity: SeverityLevel;

  /** 감지된 응집 그룹 목록 */
  groups: DetectedGroup[];

  /** 관심사 혼재 경고 목록 */
  mixedConcerns: MixedConcernWarning[];

  /** 총 변경 파일 수 */
  totalFiles: number;

  /** 총 diff 라인 수 */
  totalDiffLines: number;

  /** 분할 제안 (경고 시에만) */
  splitSuggestion?: SplitSuggestion;
}

export interface DetectedGroup {
  /** 매칭된 응집 그룹 이름 */
  groupName: string;

  /** 응집 키 값 (예: 'User', 'dashboard') */
  cohesionKeyValue: string;

  /** 이 그룹에 속하는 파일 목록 */
  files: AnalyzedFile[];
}

export interface AnalyzedFile {
  /** 파일 경로 */
  path: string;

  /** 부여된 역할 */
  role: string;
}

export interface MixedConcernWarning {
  /** 충돌하는 역할 조합 */
  roles: string[];

  /** 경고 메시지 */
  reason: string;
}

export interface SplitSuggestion {
  /** 제안하는 PR 목록 */
  proposedPrs: ProposedPr[];
}

export interface ProposedPr {
  /** PR 설명 */
  description: string;

  /** 포함할 파일 목록 */
  files: string[];

  /** 머지 순서 */
  order: number;
}

// ─── 내부 타입 ───

interface RoleAssignment {
  path: string;
  role: string;
}

// ─── 파일 → 역할 매핑 ───

/**
 * 파일 경로에 역할(role)을 부여한다.
 */
function assignRoles(files: string[], profile: PlatformProfile): RoleAssignment[] {
  return files.map((filePath) => {
    const normalizedPath = filePath.replace(/\\/g, '/');

    for (const { pattern, role } of profile.fileRoles) {
      if (globMatch(normalizedPath, pattern)) {
        return { path: normalizedPath, role };
      }
    }

    return { path: normalizedPath, role: 'unknown' };
  });
}

// ─── 응집 키 추출 ───

/**
 * 파일 경로에서 응집 키 값을 추출한다.
 *
 * cohesionKey에 따라 다른 추출 전략을 사용:
 * - domainName: 파일명에서 도메인명 추출 (UserController → User)
 * - routeSegment: app/ 하위 라우트 세그먼트 추출
 * - featureName: 경로에서 기능 디렉토리명 추출
 */
function extractCohesionKey(filePath: string, cohesionKey: string): string {
  const normalized = filePath.replace(/\\/g, '/');

  switch (cohesionKey) {
    case 'domainName':
      return extractDomainName(normalized);
    case 'routeSegment':
      return extractRouteSegment(normalized);
    case 'featureName':
      return extractFeatureName(normalized);
    case 'componentName':
      return extractComponentName(normalized);
    case 'apiSegment':
      return extractApiSegment(normalized);
    // 그룹 내 모든 파일을 하나로 묶는 키
    case 'configGroup':
    case 'migrationGroup':
    case 'designGroup':
    case 'apiGroup':
      return cohesionKey;
    default:
      return 'default';
  }
}

/**
 * 파일명에서 도메인명을 추출한다.
 * 예: src/main/kotlin/controller/UserController.kt → User
 */
function extractDomainName(filePath: string): string {
  const fileName = filePath.split('/').pop() ?? '';
  const baseName = fileName.replace(/\.[^.]+$/, ''); // 확장자 제거

  // 일반적인 접미사 패턴 제거
  const suffixes = [
    'Controller', 'Service', 'Repository', 'Entity',
    'Request', 'Response', 'Dto', 'DTO', 'Mapper',
    'Config', 'Configuration', 'Exception', 'Test',
    'ServiceTest', 'ControllerTest', 'RepositoryTest',
    'Spec', 'ServiceSpec',
  ];

  // 가장 긴 접미사부터 매칭 시도
  const sorted = [...suffixes].sort((a, b) => b.length - a.length);
  for (const suffix of sorted) {
    if (baseName.endsWith(suffix) && baseName.length > suffix.length) {
      return baseName.slice(0, -suffix.length);
    }
  }

  // 마이그레이션 파일의 경우: V3__add_user_table.sql → migration
  if (/^V\d+__/.test(baseName)) {
    return 'migration';
  }

  return baseName;
}

/**
 * app/ 하위에서 라우트 세그먼트를 추출한다.
 * 예: app/dashboard/page.tsx → dashboard
 *     app/api/dashboard/route.ts → api/dashboard
 *     components/dashboard/StatsCard.tsx → dashboard
 */
function extractRouteSegment(filePath: string): string {
  // app/ 하위 경로
  const appMatch = filePath.match(/^app\/(.+?)\/[^/]+$/);
  if (appMatch?.[1]) {
    return appMatch[1];
  }

  // components/[name]/ 패턴
  const compMatch = filePath.match(/^components\/(.+?)\/[^/]+$/);
  if (compMatch?.[1]) {
    return compMatch[1];
  }

  // hooks/[name] 패턴
  const hookMatch = filePath.match(/^hooks\/(.+?)(?:\.[^.]+)*$/);
  if (hookMatch?.[1]) {
    const hookName = hookMatch[1].replace(/^use/, '').toLowerCase();
    return hookName || 'shared';
  }

  // lib/[name]/ 패턴
  const libMatch = filePath.match(/^lib\/(.+?)\/[^/]+$/);
  if (libMatch?.[1]) {
    return libMatch[1];
  }

  // middleware는 항상 'middleware' 그룹
  if (filePath.includes('middleware')) {
    return 'middleware';
  }

  return 'shared';
}

/**
 * 경로에서 기능명을 추출한다.
 * 예: src/pages/dashboard/index.tsx → dashboard
 *     src/components/UserCard/index.tsx → UserCard
 */
function extractFeatureName(filePath: string): string {
  // src/pages/[feature]/ 패턴
  const pageMatch = filePath.match(/^src\/pages\/(.+?)\/[^/]+$/);
  if (pageMatch?.[1]) {
    return pageMatch[1];
  }

  // src/components/[feature]/ 패턴
  const compMatch = filePath.match(/^src\/components\/(.+?)\/[^/]+$/);
  if (compMatch?.[1]) {
    return compMatch[1];
  }

  // src/hooks/[name] 패턴
  const hookMatch = filePath.match(/^src\/hooks\/(.+?)(?:\.[^.]+)*$/);
  if (hookMatch?.[1]) {
    return hookMatch[1];
  }

  // src/store/[name] 패턴
  const storeMatch = filePath.match(/^src\/store\/(.+?)(?:\.[^.]+)*$/);
  if (storeMatch?.[1]) {
    return storeMatch[1].replace(/Store$/, '');
  }

  // src/api/[name] 패턴
  const apiMatch = filePath.match(/^src\/api\/(.+?)(?:\.[^.]+)*$/);
  if (apiMatch?.[1]) {
    return apiMatch[1];
  }

  // design-tokens는 별도 그룹
  if (filePath.includes('design-tokens')) {
    return 'design-system';
  }

  return 'shared';
}

/**
 * 컴포넌트명을 추출한다 (Next.js shared-component용).
 * 예: components/Button/index.tsx → Button
 *     components/Card.stories.tsx → Card
 */
function extractComponentName(filePath: string): string {
  // components/[name]/ 패턴
  const dirMatch = filePath.match(/^components\/(.+?)\/[^/]+$/);
  if (dirMatch?.[1]) {
    return dirMatch[1];
  }

  // components/[name].ext 패턴 (플랫 구조)
  const fileMatch = filePath.match(/^components\/([^/.]+)/);
  if (fileMatch?.[1]) {
    return fileMatch[1];
  }

  // stories/test 파일에서 컴포넌트명 추출
  const storyMatch = filePath.match(/([^/]+?)\.(?:stories|test)\./);
  if (storyMatch?.[1]) {
    return storyMatch[1];
  }

  return 'shared';
}

/**
 * API 라우트 세그먼트를 추출한다 (Next.js api-route용).
 * 예: app/api/dashboard/route.ts → dashboard
 *     app/api/users/[id]/route.ts → users
 *     lib/api/client.ts → api
 */
function extractApiSegment(filePath: string): string {
  // app/api/[segment]/ 패턴
  const apiMatch = filePath.match(/^app\/api\/(.+?)\/[^/]+$/);
  if (apiMatch?.[1]) {
    return apiMatch[1];
  }

  // lib/[name]/ 패턴
  const libMatch = filePath.match(/^lib\/(.+?)\/[^/]+$/);
  if (libMatch?.[1]) {
    return libMatch[1];
  }

  return 'api';
}

// ─── 응집 그룹 매칭 ───

/**
 * 역할이 부여된 파일들을 응집 그룹에 매칭한다.
 */
function matchCohesionGroups(
  roleAssignments: RoleAssignment[],
  profile: PlatformProfile,
): DetectedGroup[] {
  const groups: DetectedGroup[] = [];
  const assignedFiles = new Set<string>();

  for (const group of profile.cohesionGroups) {
    // 이 그룹의 역할에 해당하는 파일들을 찾는다
    const matchingFiles = roleAssignments.filter(
      (ra) => group.roles.includes(ra.role) && !assignedFiles.has(ra.path),
    );

    if (matchingFiles.length === 0) continue;

    // 응집 키별로 그룹핑
    const keyGroups = new Map<string, AnalyzedFile[]>();
    for (const file of matchingFiles) {
      const keyValue = extractCohesionKey(file.path, group.cohesionKey);
      const existing = keyGroups.get(keyValue) ?? [];
      existing.push({ path: file.path, role: file.role });
      keyGroups.set(keyValue, existing);
    }

    for (const [keyValue, files] of keyGroups) {
      groups.push({
        groupName: group.name,
        cohesionKeyValue: keyValue,
        files,
      });
      for (const f of files) {
        assignedFiles.add(f.path);
      }
    }
  }

  // 어떤 그룹에도 속하지 않는 파일들은 'unmatched' 그룹으로
  const unmatchedFiles = roleAssignments.filter((ra) => !assignedFiles.has(ra.path));
  if (unmatchedFiles.length > 0) {
    groups.push({
      groupName: 'unmatched',
      cohesionKeyValue: 'unmatched',
      files: unmatchedFiles.map((f) => ({ path: f.path, role: f.role })),
    });
  }

  return groups;
}

// ─── 관심사 혼재 감지 ───

/**
 * mixedConcerns 규칙에 따라 관심사 혼재를 감지한다.
 */
function detectMixedConcerns(
  roleAssignments: RoleAssignment[],
  profile: PlatformProfile,
): MixedConcernWarning[] {
  const presentRoles = new Set(roleAssignments.map((ra) => ra.role));
  const warnings: MixedConcernWarning[] = [];

  for (const rule of profile.thresholds.mixedConcerns) {
    const allPresent = rule.roles.every((role) => presentRoles.has(role));
    if (allPresent) {
      warnings.push({
        roles: rule.roles,
        reason: rule.reason,
      });
    }
  }

  return warnings;
}

// ─── 경고 레벨 판단 ───

/**
 * 분석 결과를 기반으로 경고 레벨을 결정한다.
 *
 * 규정 문서: docs/probe-v0.1-scope.md § 3.2
 * - ok:    1~2개 group, 임계치 이내
 * - info:  2개 group + mixedConcerns 해당
 * - warn:  3개 이상 group 또는 파일 수 임계치 초과
 * - error: 4개 이상 group + diff 라인 임계치 초과
 */
function determineSeverity(
  groups: DetectedGroup[],
  mixedConcerns: MixedConcernWarning[],
  totalFiles: number,
  totalDiffLines: number,
  profile: PlatformProfile,
): SeverityLevel {
  const { thresholds } = profile;
  // unmatched 그룹이 비어있지 않으면 의미있는 그룹으로 카운트
  const meaningfulGroups = groups.filter((g) => g.groupName !== 'unmatched' || g.files.length > 0);
  const groupCount = meaningfulGroups.length;

  // error: maxCohesionGroups 2배 초과 + diff 라인 임계치 초과
  if (groupCount >= thresholds.maxCohesionGroups * 2 && totalDiffLines > thresholds.maxDiffLinesPerPr) {
    return 'error';
  }

  // warn: maxCohesionGroups 초과 또는 파일 수 임계치 초과
  if (groupCount > thresholds.maxCohesionGroups || totalFiles > thresholds.maxFilesPerPr) {
    return 'warn';
  }

  // info: maxCohesionGroups 도달 + mixedConcerns 해당
  if (groupCount >= thresholds.maxCohesionGroups && mixedConcerns.length > 0) {
    return 'info';
  }

  // diff 라인 수 단독 초과
  if (totalDiffLines > thresholds.maxDiffLinesPerPr) {
    return 'warn';
  }

  return 'ok';
}

// ─── 분할 제안 생성 ───

/**
 * 경고 시 분할 제안을 생성한다.
 *
 * 규정 문서: docs/probe-v0.1-scope.md § 3.3
 */
function generateSplitSuggestion(
  groups: DetectedGroup[],
  _profile: PlatformProfile,
): SplitSuggestion {
  // 머지 순서 결정: 인프라/설정 → 데이터 → 비즈니스 로직 → UI
  const priorityOrder: Record<string, number> = {
    'migration': 1,
    'config-change': 2,
    'api-layer': 3,
    'api-route': 3,
    'domain-crud': 4,
    'feature': 5,
    'page-feature': 5,
    'shared-component': 5,
    'design-system': 6,
    'unmatched': 7,
  };

  const sorted = [...groups].sort((a, b) => {
    const pa = priorityOrder[a.groupName] ?? 99;
    const pb = priorityOrder[b.groupName] ?? 99;
    return pa - pb;
  });

  const proposedPrs: ProposedPr[] = sorted.map((group, index) => ({
    description: buildPrDescription(group),
    files: group.files.map((f) => f.path),
    order: index + 1,
  }));

  return { proposedPrs };
}

/**
 * 그룹 정보로 PR 설명을 생성한다.
 */
function buildPrDescription(group: DetectedGroup): string {
  if (group.groupName === 'unmatched') {
    return `기타 변경 (${group.files.length}개 파일)`;
  }

  const keyLabel = group.cohesionKeyValue !== 'default' ? ` — ${group.cohesionKeyValue}` : '';
  return `${group.groupName}${keyLabel} (${group.files.length}개 파일)`;
}

// ─── 공개 API ───

/**
 * PR 범위를 분석한다.
 *
 * @param changedFiles 변경된 파일 경로 목록
 * @param profile 플랫폼 프로파일
 * @param diffLines 총 diff 라인 수 (선택, 기본: 0)
 */
export function analyzeScope(
  changedFiles: string[],
  profile: PlatformProfile,
  diffLines?: number,
): ScopeAnalysisResult {
  const totalDiffLines = diffLines ?? 0;

  if (changedFiles.length === 0) {
    return {
      severity: 'ok',
      groups: [],
      mixedConcerns: [],
      totalFiles: 0,
      totalDiffLines,
    };
  }

  // 1. 파일 → 역할 매핑
  const roleAssignments = assignRoles(changedFiles, profile);

  // 2. 응집 그룹 매칭
  const groups = matchCohesionGroups(roleAssignments, profile);

  // 3. 관심사 혼재 감지
  const mixedConcerns = detectMixedConcerns(roleAssignments, profile);

  // 4. 경고 레벨 판단
  const severity = determineSeverity(
    groups,
    mixedConcerns,
    changedFiles.length,
    totalDiffLines,
    profile,
  );

  // 5. 분할 제안 생성 (ok가 아닐 때만)
  const splitSuggestion = severity !== 'ok'
    ? generateSplitSuggestion(groups, profile)
    : undefined;

  return {
    severity,
    groups,
    mixedConcerns,
    totalFiles: changedFiles.length,
    totalDiffLines,
    splitSuggestion,
  };
}
