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
import type {
  Suspect, GroundingPack, DesignGap, OperationalSignal, RelevantDoc, ImpactAnalysis,
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
      () => fetchKnowledge(client, options.signal, options.searchTopK ?? 5),
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
      () => fetchGaps(client, names),
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

  return pack;
}

/** §5: 의심 지점 + 신호로 관련 문서 검색 */
async function fetchKnowledge(
  client: KhalaClient, signal: string, topK: number,
): Promise<RelevantDoc[]> {
  // 검색 쿼리는 앞 500자만 사용 (저장 신호의 8000자 절단과는 별개 — 쿼리 품질·길이 제한용)
  const result = await client.search(signal.slice(0, 500), { topK });
  if (!result) return [];
  return result.results.map((h) => ({
    docTitle: h.doc_title, sectionPath: h.section_path,
    snippet: h.snippet, score: h.score, classification: h.classification,
  }));
}

/** §3: 각 의심 service의 diff를 합쳐 DesignGap[]으로 변환.
 *  모든 diff 조회가 null을 반환하면 에러를 던져 상위 withKhalaFallback이 caveat을 남기게 한다. */
async function fetchGaps(client: KhalaClient, names: string[]): Promise<DesignGap[]> {
  const results = await Promise.all(
    names.map((n) => client.getDiff({ entityFilter: n })),
  );
  const successResults = results.filter((r) => r !== null);
  // 모든 요청이 실패(null)하면 상위로 에러를 던진다
  if (successResults.length === 0 && names.length > 0) {
    throw new Error('diff 조회 전체 실패 (All diff lookups failed)');
  }
  const gaps: DesignGap[] = [];
  for (const r of successResults) {
    for (const d of r.diffs) {
      gaps.push({
        flag: d.flag, fromName: d.from_name, toName: d.to_name,
        edgeType: d.edge_type, detail: d.detail,
        // 기존 context-enricher.ts 패턴과 일관: 모든 설계 근거를 join
        designedEvidence: d.designed_evidence.length > 0
          ? d.designed_evidence.map((e) => e.text).join('; ')
          : undefined,
        observedEvidence: d.observed_evidence?.sample_trace_ids,
      });
    }
  }
  return gaps;
}

/** §4: 토폴로지 관측치에서 이상 신호 추출 */
function extractSignals(topology?: ImpactAnalysis): OperationalSignal[] {
  if (!topology) return [];
  const signals: OperationalSignal[] = [];
  for (const svc of [...topology.directImpact, ...topology.indirectImpact]) {
    if (svc.observed && svc.observed.errorRate >= ERROR_RATE_THRESHOLD) {
      signals.push({
        fromName: topology.changedServices[0] ?? '?',
        toName: svc.name,
        callCount: svc.observed.callCount,
        errorRate: svc.observed.errorRate,
        latencyP95: svc.observed.latencyP95,
        anomaly: `error_rate ${svc.observed.errorRate.toFixed(2)} > 임계 ${ERROR_RATE_THRESHOLD}`,
      });
    }
  }
  return signals;
}
