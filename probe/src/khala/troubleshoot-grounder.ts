/**
 * 트러블슈팅 Grounding Pack 조립
 *
 * Suspect[]와 KhalaClient로 §2~§6 섹션을 병렬 조립한다.
 * 각 섹션은 독립 실패해도 나머지를 막지 않는다 (withKhalaFallback).
 * §5 지식 그라운딩은 client.search()를 직접 호출한다 (context-enricher 재사용 안 함 — 스펙 §5.1).
 *
 * 규정 문서: docs/superpowers/specs/2026-06-06-troubleshooting-grounding-design.md §2~§6
 */

import { KhalaClient, withKhalaFallback } from './client.js';
import { analyzeImpact } from './impact-analyzer.js';
import { fetchEntityGaps, searchDocs } from './grounding-sections.js';
import type {
  Suspect, GroundingPack, OperationalSignal, ImpactAnalysis,
} from './types.js';

/** 운영 신호 이상치 임계 (impact-analyzer와 동일치 재사용 — 스펙 Q3) */
const ERROR_RATE_THRESHOLD = 0.05;

export interface GroundOptions {
  signal: string;
  tier: 0 | 1 | 2 | 3;
  searchTopK?: number;
  graphHops?: number;
  /** §6 최근 변경 상관용 (Task 9에서 로직 추가; 인터페이스는 미리 선언) */
  changedServices?: { service: string; changedFiles: string[] }[];
}

/**
 * Grounding Pack을 조립한다 (티어가 허용하는 섹션까지).
 */
export async function groundTroubleshooting(
  client: KhalaClient,
  suspects: Suspect[],
  options: GroundOptions,
): Promise<GroundingPack> {
  const caveats: string[] = [];
  const pack: GroundingPack = {
    tier: options.tier,
    tierReason: '',
    suspects,
    caveats,
  };

  const names = suspects.filter((s) => s.confidence >= 0.3).map((s) => s.entityName);

  // §5 지식 (T1+)
  if (options.tier >= 1) {
    const knowledge = await withKhalaFallback(
      // 검색 쿼리는 앞 500자만 사용 (저장 신호의 8000자 절단과는 별개 — 쿼리 품질·길이 제한용)
      () => searchDocs(client, options.signal.slice(0, 500), options.searchTopK ?? 5),
      null, 'search',
    );
    if (knowledge) pack.knowledge = knowledge;
    else caveats.push('지식 그라운딩(search) 조회 실패 (Knowledge grounding unavailable)');
  }

  // §2 토폴로지/영향 (T2+)
  if (options.tier >= 2 && names.length > 0) {
    const topology = await withKhalaFallback<ImpactAnalysis | null>(
      () => analyzeImpact(client, names, { hops: options.graphHops ?? 2 }),
      null, 'impact',
    );
    if (topology) pack.topology = topology;
  }

  // §3 설계-관측 갭 (doc_only는 T2+, observed_only/conflict는 T3)
  if (options.tier >= 2 && names.length > 0) {
    const gaps = await withKhalaFallback(
      () => fetchEntityGaps(client, names),
      null, 'diff',
    );
    if (gaps) {
      pack.designObservationGaps = options.tier >= 3
        ? gaps
        : gaps.filter((g) => g.flag === 'doc_only');
      // §4 운영 신호 (T3)
      if (options.tier >= 3) {
        pack.operationalSignals = extractSignals(pack.topology);
      }
    } else {
      caveats.push('설계-관측 갭(diff) 조회 실패 (Design-observation gap unavailable)');
    }
  }

  // §6 최근 변경 상관: 변경 service ∩ 의심 service (스펙 §3.4: T2 — 설계 그래프 필요)
  if (options.tier >= 2 && options.changedServices?.length) {
    const suspectSet = new Set(names);
    pack.changeCorrelation = options.changedServices
      .filter((c) => suspectSet.has(c.service))
      .map((c) => ({ service: c.service, changedFiles: c.changedFiles, relationship: 'changed∩suspect' }));
  }

  return pack;
}

/** §4: 토폴로지 관측치에서 이상 신호 추출 */
function extractSignals(topology?: ImpactAnalysis): OperationalSignal[] {
  if (!topology) return [];
  // 변경 서비스가 단 하나일 때만 그것을 엣지 소스 후보로 쓴다(여럿이면 모호).
  const singleSource = topology.changedServices.length === 1
    ? topology.changedServices[0]
    : undefined;
  const signals: OperationalSignal[] = [];
  for (const svc of [...topology.directImpact, ...topology.indirectImpact]) {
    const o = svc.observed;
    if (!o || o.errorRate < ERROR_RATE_THRESHOLD) continue;
    // 의심 지점이 호출받는 쪽(downstream)이면 svc가 호출자(소스).
    const svcIsCaller = svc.relationship === 'called_by' || svc.relationship === 'subscribes_from';
    // 1순위: 실제 관측 엣지 방향. 2순위: 관계로 추정. 최후: svc.name (절대 '?' 누출 안 함).
    const fromName = o.fromName ?? (svcIsCaller ? svc.name : singleSource) ?? svc.name;
    const toName = o.toName ?? (svcIsCaller ? singleSource : svc.name) ?? svc.name;
    signals.push({
      fromName,
      toName,
      callCount: o.callCount,
      errorRate: o.errorRate,
      latencyP95: o.latencyP95,
      anomaly: `error_rate ${o.errorRate.toFixed(2)} > 임계 ${ERROR_RATE_THRESHOLD}`,
    });
  }
  return signals;
}
