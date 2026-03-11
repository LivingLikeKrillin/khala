/**
 * 플랫폼 프로파일 타입 정의
 *
 * 각 프레임워크에서 "하나의 논리적 변경"이 통상 어떤 파일 패턴으로
 * 나타나는지를 정의한다. Karax의 PR 범위 판단의 핵심.
 */

/** 파일 경로 → 역할 매핑 패턴 */
export interface FileRolePattern {
  /** glob 패턴 */
  pattern: string;

  /** 이 패턴에 매칭되는 파일의 역할 */
  role: string;
}

/** 논리적 변경 단위 (응집 그룹) */
export interface CohesionGroup {
  /** 그룹 이름 (예: 'domain-crud', 'page-feature') */
  name: string;

  /** 설명 */
  description: string;

  /** 이 그룹을 구성하는 역할 목록 */
  roles: string[];

  /**
   * 응집 판단 키.
   * 파일 경로에서 이 키에 해당하는 값을 추출하여,
   * 같은 값이면 같은 그룹으로 판단한다.
   * 예: 'domainName' → User, Order 등
   * 예: 'routeSegment' → dashboard, settings 등
   */
  cohesionKey: string;

  /** 이 그룹 내 최대 허용 파일 수 */
  maxFiles: number;
}

/** 관심사 혼재 규칙 */
export interface MixedConcernRule {
  /** 이 역할 조합이 동시에 존재하면 경고 */
  roles: string[];

  /** 경고 메시지 */
  reason: string;
}

/** PR 크기 임계치 */
export interface PrThresholds {
  /** PR 당 최대 파일 수 */
  maxFilesPerPr: number;

  /** PR 당 최대 diff 라인 수 */
  maxDiffLinesPerPr: number;

  /** 최대 허용 응집 그룹 수 */
  maxCohesionGroups: number;

  /** 관심사 혼재 규칙 목록 */
  mixedConcerns: MixedConcernRule[];
}

/** 플랫폼 프로파일 */
export interface PlatformProfile {
  /** 프로파일 이름 (예: 'spring-boot', 'nextjs') */
  name: string;

  /** 파일 역할 매핑 */
  fileRoles: FileRolePattern[];

  /** 응집 그룹 정의 */
  cohesionGroups: CohesionGroup[];

  /** PR 크기 임계치 */
  thresholds: PrThresholds;
}

/** 경고 레벨 */
export type SeverityLevel = 'ok' | 'info' | 'warn' | 'error';
