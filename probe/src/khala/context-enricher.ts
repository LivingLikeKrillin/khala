/**
 * 칼라 컨텍스트 보강 오케스트레이터
 *
 * PR 분석 결과에 칼라의 맥락(관련 규정, 영향 서비스, 설계-관측 갭)을 추가한다.
 * 칼라가 없으면 빈 결과를 반환한다 (graceful degradation).
 *
 * 규정 문서: docs/probe-v0.4-scope.md § 4
 */

import { KhalaClient, withKhalaFallback } from './client.js';
import { analyzeImpact } from './impact-analyzer.js';
import { logger } from '../utils/logger.js';
import type { DetectedGroup } from '../core/scope-analyzer.js';
import type {
  KhalaClientConfig,
  EnrichmentResult,
  RelevantDoc,
  DesignGap,
  ImpactAnalysis,
} from './types.js';

/** 보강 옵션 */
export interface EnrichmentOptions {
  /** 칼라 클라이언트 설정 */
  khalaConfig?: Partial<KhalaClientConfig>;
  /** 검색 결과 최대 건수 (기본: 5) */
  searchTopK?: number;
  /** 그래프 탐색 홉 수 (기본: 1) */
  graphHops?: number;
}

/** 빈 보강 결과 (칼라 미가용 시) */
const EMPTY_ENRICHMENT: EnrichmentResult = {
  relevantDocs: [],
  impactedServices: [],
  designObservationGaps: [],
  khalaAvailable: false,
};

/**
 * PR 변경에 대한 칼라 컨텍스트를 수집한다.
 *
 * 3개 조회를 병렬로 수행한다:
 * 1. 관련 규정/문서 검색
 * 2. 서비스 그래프 (영향 분석)
 * 3. 설계-관측 diff
 *
 * @param groups scope 분석에서 감지된 응집 그룹
 * @param changedFiles 변경 파일 목록
 * @param options 보강 옵션
 */
export async function enrichWithKhala(
  groups: DetectedGroup[],
  _changedFiles: string[],
  options?: EnrichmentOptions,
): Promise<EnrichmentResult> {
  const client = new KhalaClient(options?.khalaConfig);
  const topK = options?.searchTopK ?? 5;
  const hops = options?.graphHops ?? 1;

  // 칼라 가용 여부 확인
  const available = await withKhalaFallback(
    () => client.isAvailable(),
    false,
    'availability check',
  );
  if (!available) {
    logger.debug('칼라 서버 미가용 — 보강 없이 진행');
    return EMPTY_ENRICHMENT;
  }

  // 서비스/도메인명 추출
  const serviceNames = extractServiceNames(groups);
  if (serviceNames.length === 0) {
    logger.debug('서비스명 추출 실패 — 보강 없이 진행');
    return { ...EMPTY_ENRICHMENT, khalaAvailable: true };
  }

  // 3개 조회 병렬 실행
  const [relevantDocs, impact, gaps] = await Promise.all([
    searchRelevantDocs(client, serviceNames, topK),
    fetchImpact(client, serviceNames, hops),
    fetchDesignGaps(client, serviceNames),
  ]);

  return {
    relevantDocs,
    impactedServices: impact.directImpact.concat(impact.indirectImpact),
    designObservationGaps: gaps,
    khalaAvailable: true,
  };
}

/**
 * 응집 그룹에서 서비스/도메인명을 추출한다.
 *
 * cohesionKeyValue를 kebab-case 서비스명으로 변환한다.
 * 예: "Payment" → "payment-service", "user" → "user-service"
 */
export function extractServiceNames(groups: DetectedGroup[]): string[] {
  const names = new Set<string>();

  for (const group of groups) {
    const key = group.cohesionKeyValue;
    if (!key || key === 'unknown') continue;

    // cohesionKeyValue를 소문자 kebab-case로 변환
    const normalized = key
      .replace(/([a-z])([A-Z])/g, '$1-$2')
      .replace(/[_\s]+/g, '-')
      .toLowerCase();

    names.add(normalized);

    // "-service" 접미사 버전도 추가 (칼라 검색 매칭율 향상)
    if (!normalized.endsWith('-service')) {
      names.add(`${normalized}-service`);
    }
  }

  return [...names];
}

/**
 * 관련 규정/문서를 검색한다.
 */
async function searchRelevantDocs(
  client: KhalaClient,
  serviceNames: string[],
  topK: number,
): Promise<RelevantDoc[]> {
  // 서비스명을 조합해서 검색 쿼리 생성
  const query = serviceNames.slice(0, 3).join(' ') + ' 규정 가이드라인';

  const result = await withKhalaFallback(
    () => client.search(query, { topK, includeGraph: false }),
    null,
    'search relevant docs',
  );

  if (!result) return [];

  return result.results.map((hit) => ({
    docTitle: hit.doc_title,
    sectionPath: hit.section_path,
    snippet: hit.snippet,
    score: hit.score,
    classification: hit.classification,
  }));
}

/**
 * 서비스 영향 분석을 수행한다.
 */
async function fetchImpact(
  client: KhalaClient,
  serviceNames: string[],
  hops: number,
): Promise<ImpactAnalysis> {
  return analyzeImpact(client, serviceNames, { hops });
}

/**
 * 설계-관측 갭을 조회하고, 변경 서비스와 관련된 것만 필터한다.
 */
async function fetchDesignGaps(
  client: KhalaClient,
  serviceNames: string[],
): Promise<DesignGap[]> {
  const diff = await withKhalaFallback(
    () => client.getDiff(),
    null,
    'fetch design gaps',
  );

  if (!diff || diff.diffs.length === 0) return [];

  // 변경 서비스와 관련된 diff만 필터
  const nameSet = new Set(serviceNames);

  return diff.diffs
    .filter((d) => {
      const fromNorm = d.from_name.toLowerCase();
      const toNorm = d.to_name.toLowerCase();
      return [...nameSet].some((n) => fromNorm.includes(n) || toNorm.includes(n));
    })
    .map((d) => ({
      flag: d.flag,
      fromName: d.from_name,
      toName: d.to_name,
      edgeType: d.edge_type,
      detail: d.detail,
      designedEvidence: d.designed_evidence.length > 0
        ? d.designed_evidence.map((e) => e.text).join('; ')
        : undefined,
      observedEvidence: d.observed_evidence
        ? d.observed_evidence.sample_trace_ids
        : undefined,
    }));
}
