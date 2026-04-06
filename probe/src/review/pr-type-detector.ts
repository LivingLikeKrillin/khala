/**
 * PR 타입 추론
 *
 * 변경 파일의 역할(role) 분포를 분석하여 PR 타입을 결정한다.
 *
 * 규정 문서: docs/probe-v0.2-scope.md § 3.3
 */

import type { PrType } from './types.js';

/** 역할 집계 */
interface RoleCount {
  role: string;
  count: number;
}

/**
 * 파일 역할 목록에서 PR 타입을 추론한다.
 *
 * @param roles 파일별 부여된 역할 목록
 * @param hasApiSpecChange API 스펙 파일이 변경되었는지 여부
 * @returns 추론된 PR 타입
 */
export function detectPrType(roles: string[], hasApiSpecChange: boolean = false): PrType {
  if (roles.length === 0) return 'general';

  const roleSet = new Set(roles);
  const roleCounts = countRoles(roles);

  // test만
  if (roles.every((r) => r === 'test')) return 'test-only';

  // docs만
  if (roles.every((r) => r === 'docs' || r === 'unknown')) {
    // unknown이지만 docs 관련 파일인지 확인
    return 'docs-only';
  }

  // db-migration
  if (roleSet.has('migration') && !roleSet.has('controller') && !roleSet.has('page')) {
    return 'db-migration';
  }

  // api-change: controller + dto + openapi 스펙 변경
  if (hasApiSpecChange && (roleSet.has('controller') || roleSet.has('dto'))) {
    return 'api-change';
  }

  // domain-crud: entity + service + controller + dto
  if (roleSet.has('entity') && roleSet.has('service')) {
    return 'domain-crud';
  }
  if (roleSet.has('entity') && roleSet.has('controller')) {
    return 'domain-crud';
  }
  if (roleSet.has('service') && roleSet.has('controller') && roleSet.has('dto')) {
    return 'domain-crud';
  }

  // config-change
  if (roleSet.has('config') && roleCounts.length <= 2) {
    return 'config-change';
  }

  // design-system
  if (roleSet.has('token') || roleSet.has('design-token')) {
    return 'design-system';
  }

  // ui-component: component + story + test
  if (roleSet.has('component') && roleSet.has('story') && !roleSet.has('page')) {
    return 'ui-component';
  }

  // ui-feature: page + component + hook
  if (roleSet.has('page') || roleSet.has('layout')) {
    return 'ui-feature';
  }

  // component 변경이 주도적이면 ui-component
  if (roleSet.has('component') && !roleSet.has('service') && !roleSet.has('entity')) {
    return 'ui-component';
  }

  return 'general';
}

/**
 * 역할별 개수를 세어 정렬된 배열로 반환한다.
 */
function countRoles(roles: string[]): RoleCount[] {
  const counts = new Map<string, number>();
  for (const role of roles) {
    counts.set(role, (counts.get(role) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([role, count]) => ({ role, count }))
    .sort((a, b) => b.count - a.count);
}
