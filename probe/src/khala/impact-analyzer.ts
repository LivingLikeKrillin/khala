/**
 * 칼라 기반 서비스 영향 분석
 *
 * 변경된 서비스의 upstream/downstream을 칼라 그래프에서 조회하고,
 * 영향 범위와 심각도를 판단한다.
 *
 * 규정 문서: docs/probe-v0.4-scope.md § 5
 */

import type { KhalaClient } from './client.js';
import { withKhalaFallback } from './client.js';
import { logger } from '../utils/logger.js';
import type {
  ImpactAnalysis,
  ImpactedService,
  KhalaGraphResult,
} from './types.js';

/** 영향 분석 옵션 */
export interface ImpactOptions {
  /** 그래프 탐색 홉 수 (기본: 1) */
  hops?: number;
}

/** 빈 영향 분석 결과 */
const EMPTY_IMPACT: ImpactAnalysis = {
  changedServices: [],
  directImpact: [],
  indirectImpact: [],
  summary: '영향 분석 불가 (Impact analysis unavailable)',
  severity: 'none',
};

/**
 * 서비스 영향 분석을 수행한다.
 *
 * 각 서비스명으로 칼라 그래프를 조회하여 이웃 서비스를 찾고,
 * 영향 범위와 심각도를 판단한다.
 *
 * @param client 칼라 클라이언트
 * @param serviceNames 변경된 서비스명 목록
 * @param options 분석 옵션
 */
export async function analyzeImpact(
  client: KhalaClient,
  serviceNames: string[],
  options?: ImpactOptions,
): Promise<ImpactAnalysis> {
  if (serviceNames.length === 0) return EMPTY_IMPACT;

  const hops = options?.hops ?? 1;

  // 각 서비스에 대해 그래프 조회 (병렬)
  const graphResults = await Promise.all(
    serviceNames.map((name) =>
      withKhalaFallback(
        () => client.getGraph(buildEntityRid(name), { hops }),
        null,
        `graph lookup: ${name}`,
      ),
    ),
  );

  // 유효한 결과만 수집
  const validResults = graphResults.filter(
    (r): r is KhalaGraphResult => r !== null,
  );

  if (validResults.length === 0) {
    logger.debug('칼라 그래프 조회 결과 없음');
    return {
      ...EMPTY_IMPACT,
      changedServices: serviceNames,
      summary: '칼라에서 서비스 관계를 찾을 수 없습니다 (No service relationships found)',
    };
  }

  // 영향받는 서비스 추출
  const serviceNameSet = new Set(serviceNames);
  const directImpact: ImpactedService[] = [];
  const indirectImpact: ImpactedService[] = [];
  const seen = new Set<string>();

  for (const graph of validResults) {
    // 설계 엣지에서 영향 추출
    for (const edge of graph.edges) {
      const impacted = extractImpactFromEdge(edge, serviceNameSet);
      if (impacted && !seen.has(impacted.name)) {
        seen.add(impacted.name);
        if (edge.hop <= 1) {
          directImpact.push(impacted);
        } else {
          indirectImpact.push(impacted);
        }
      }
    }

    // 관측 엣지에서 관측 데이터 보강
    for (const obs of graph.observed_edges) {
      const fromNorm = obs.from_name.toLowerCase();
      const toNorm = obs.to_name.toLowerCase();
      const isFromChanged = [...serviceNameSet].some((n) => fromNorm.includes(n));
      const isToChanged = [...serviceNameSet].some((n) => toNorm.includes(n));
      const targetName = isFromChanged ? obs.to_name : isToChanged ? obs.from_name : null;

      if (!targetName) continue;

      const existing = directImpact.find(
        (s) => s.name.toLowerCase() === targetName.toLowerCase(),
      ) ?? indirectImpact.find(
        (s) => s.name.toLowerCase() === targetName.toLowerCase(),
      );

      if (existing) {
        existing.observed = {
          callCount: obs.call_count,
          errorRate: obs.error_rate,
          latencyP95: obs.latency_p95,
        };
      }
    }
  }

  // 심각도 판단
  const severity = determineSeverity(directImpact, indirectImpact);
  const summary = buildSummary(serviceNames, directImpact, indirectImpact, severity);

  return {
    changedServices: serviceNames,
    directImpact,
    indirectImpact,
    summary,
    severity,
  };
}

/**
 * 엣지에서 영향받는 서비스 정보를 추출한다.
 */
function extractImpactFromEdge(
  edge: KhalaGraphResult['edges'][number],
  changedServiceNames: Set<string>,
): ImpactedService | null {
  const fromNorm = edge.from_name.toLowerCase();
  const toNorm = edge.to_name.toLowerCase();
  const isFromChanged = [...changedServiceNames].some((n) => fromNorm.includes(n));
  const isToChanged = [...changedServiceNames].some((n) => toNorm.includes(n));

  // 변경된 서비스가 호출하는 쪽이면, 호출받는 쪽이 영향
  if (isFromChanged && !isToChanged) {
    return {
      name: edge.to_name,
      rid: edge.to_rid,
      relationship: edgeTypeToRelationship(edge.edge_type, 'outgoing'),
      confidence: edge.confidence,
    };
  }

  // 변경된 서비스가 호출받는 쪽이면, 호출하는 쪽이 영향
  if (isToChanged && !isFromChanged) {
    return {
      name: edge.from_name,
      rid: edge.from_rid,
      relationship: edgeTypeToRelationship(edge.edge_type, 'incoming'),
      confidence: edge.confidence,
    };
  }

  return null;
}

/**
 * 엣지 타입과 방향에서 관계 유형을 결정한다.
 */
function edgeTypeToRelationship(
  edgeType: string,
  direction: 'outgoing' | 'incoming',
): ImpactedService['relationship'] {
  switch (edgeType) {
    case 'CALLS':
    case 'CALLS_OBSERVED':
      return direction === 'outgoing' ? 'calls' : 'called_by';
    case 'PUBLISHES':
      return direction === 'outgoing' ? 'publishes_to' : 'subscribes_from';
    case 'SUBSCRIBES':
      return direction === 'outgoing' ? 'subscribes_from' : 'publishes_to';
    default:
      return direction === 'outgoing' ? 'calls' : 'called_by';
  }
}

/**
 * 영향 심각도를 판단한다.
 *
 * | 심각도 | 조건 |
 * |--------|------|
 * | none   | 다른 서비스에 영향 없음 |
 * | low    | 1~2개 서비스, 하위 호환 가능 |
 * | medium | 3개 이상, 또는 error rate 높은 경로 |
 * | high   | 다수 서비스 + 높은 error rate 경로 |
 */
function determineSeverity(
  direct: ImpactedService[],
  indirect: ImpactedService[],
): ImpactAnalysis['severity'] {
  const totalImpacted = direct.length + indirect.length;

  if (totalImpacted === 0) return 'none';

  // 높은 error rate 경로 존재 여부
  const hasHighErrorRate = direct.some(
    (s) => s.observed && s.observed.errorRate > 0.05,
  );

  if (totalImpacted >= 3 && hasHighErrorRate) return 'high';
  if (totalImpacted >= 3 || hasHighErrorRate) return 'medium';
  return 'low';
}

/**
 * 영향 분석 요약 메시지를 생성한다.
 */
function buildSummary(
  changed: string[],
  direct: ImpactedService[],
  indirect: ImpactedService[],
  severity: ImpactAnalysis['severity'],
): string {
  if (direct.length === 0 && indirect.length === 0) {
    return `${changed.join(', ')}에 대한 영향받는 서비스가 없습니다`;
  }

  const parts: string[] = [];

  if (direct.length > 0) {
    const names = direct.map((s) => s.name).join(', ');
    parts.push(`직접 영향: ${names} (${direct.length}개)`);
  }

  if (indirect.length > 0) {
    const names = indirect.map((s) => s.name).join(', ');
    parts.push(`간접 영향: ${names} (${indirect.length}개)`);
  }

  const severityLabel = {
    none: '없음',
    low: '낮음',
    medium: '중간',
    high: '높음',
  }[severity];

  return `${changed.join(', ')} 변경 영향 [${severityLabel}]: ${parts.join(' / ')}`;
}

/**
 * 서비스명에서 칼라 entity RID를 생성한다.
 *
 * 칼라의 rid.py 로직과 동일하게:
 * SHA256(canonical_name)[:12]
 *
 * 단, 정확한 RID를 알 수 없으므로 칼라의 형식에 맞춰 추정한다.
 * 실제로는 칼라 검색에서 이름 매칭으로 엔티티를 찾는다.
 */
function buildEntityRid(serviceName: string): string {
  // 칼라의 entity_rid 형식: "ent_" + SHA256(tenant:entity_type:canonical_name)[:12]
  // 정확한 해시를 구하려면 crypto가 필요하지만,
  // 칼라 API는 rid로 직접 조회하므로 이름 기반 검색이 더 안정적.
  // 여기서는 일단 RID 형식으로 구성하고, 404 시 검색 fallback을 사용.
  return `ent_${serviceName}`;
}
