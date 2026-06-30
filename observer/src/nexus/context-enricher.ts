/**
 * Nexus 컨텍스트 보강 오케스트레이터
 *
 * PR 분석 결과에 Nexus의 맥락(관련 규정, 영향 서비스, 설계-관측 갭)을 추가한다.
 * Nexus가 없으면 빈 결과를 반환한다 (graceful degradation).
 *
 * v0.6: groundReview 위임 어댑터로 수렴.
 * EnrichmentResult 레거시 형태를 유지해 MCP scope-tool 호출부가 영향받지 않는다.
 *
 * 규정 문서: docs/probe-v0.4-scope.md § 4
 */

import { NexusClient } from './client.js';
import { determineTier } from './tier.js';
import { groundReview } from './review-grounder.js';
import { logger } from '../utils/logger.js';
import type { DetectedGroup } from '../core/scope-analyzer.js';
import type { NexusClientConfig, EnrichmentResult } from './types.js';

/** 보강 옵션 */
export interface EnrichmentOptions {
  /** Nexus 클라이언트 설정 */
  nexusConfig?: Partial<NexusClientConfig>;
  /** 검색 결과 최대 건수 (기본: 5) */
  searchTopK?: number;
  /** 그래프 탐색 홉 수 (기본: 1) */
  graphHops?: number;
}

/** 빈 보강 결과 (Nexus 미가용 시) */
const EMPTY_ENRICHMENT: EnrichmentResult = {
  relevantDocs: [],
  impactedServices: [],
  designObservationGaps: [],
  nexusAvailable: false,
};

/**
 * PR 변경에 대한 Nexus 컨텍스트를 수집한다.
 *
 * groundReview에 위임하고 결과를 레거시 EnrichmentResult 형태로 투영한다.
 * 엔티티 스코프 /diff를 사용해 글로벌 diff보다 노이즈가 적다.
 *
 * 주의: Nexus가 가용하지만 인덱싱 데이터가 부족해 티어가 T0이면(엔티티명은 있어도)
 * 빈 배열 + `nexusAvailable: true`를 반환한다 — 빈 결과를 "미가용"으로 오독하지 말 것.
 *
 * @param groups scope 분석에서 감지된 응집 그룹
 * @param changedFiles 변경 파일 목록
 * @param options 보강 옵션
 */
export async function enrichWithNexus(
  groups: DetectedGroup[],
  changedFiles: string[],
  options?: EnrichmentOptions,
): Promise<EnrichmentResult> {
  const client = new NexusClient(options?.nexusConfig);

  const probe = await client.getStatusProbe();
  if (!probe.ok) {
    logger.debug(`Nexus 미가용(${probe.reason}) — 보강 없이 진행`);
    return EMPTY_ENRICHMENT;
  }
  const tier = determineTier(probe.status).tier;

  // 변경 엔티티 빌드 (core 의존 금지 — 로컬 헬퍼 사용)
  const names = extractServiceNames(groups);
  if (names.length === 0) {
    return { ...EMPTY_ENRICHMENT, nexusAvailable: true };
  }
  const changedEntities = names.map((name) => ({
    entityName: name,
    changedFiles: changedFiles.filter((f) => fileBelongsToService(f, name)),
  }));

  const pack = await groundReview(client, changedEntities, {
    tier,
    searchTopK: options?.searchTopK,
    graphHops: options?.graphHops,
  });

  // ReviewGroundingPack → 레거시 EnrichmentResult 투영 (back-compat)
  return {
    relevantDocs: pack.applicableGuidelines ?? [],
    impactedServices: pack.topology ? pack.topology.directImpact.concat(pack.topology.indirectImpact) : [],
    designObservationGaps: pack.designObservationGaps ?? [],
    nexusAvailable: true,
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

    // "-service" 접미사 버전도 추가 (Nexus 검색 매칭율 향상)
    if (!normalized.endsWith('-service')) {
      names.add(`${normalized}-service`);
    }
  }

  return [...names];
}

/**
 * 변경 파일이 특정 서비스에 속하는지 경계(세그먼트/토큰) 기준으로 판정한다.
 *
 * 단순 substring 매칭(`f.includes(service.replace(/-/g,''))`)은 과대매칭한다.
 * 예: 서비스 "api"가 "rapid"/"therapist"에, "order-service"→"orderservice"가
 * "reorderserviceutil"에 잘못 매칭됐다. 여기서는 경로 세그먼트를 토큰화하고
 * 서비스명을 토큰 경계로만 매칭한다.
 *
 * @param file 변경 파일 경로 (예: "services/order-service/checkout.ts")
 * @param service 서비스명 (예: "order-service")
 */
export function fileBelongsToService(file: string, service: string): boolean {
  const svc = service.toLowerCase();
  const svcCompact = svc.replace(/-/g, '');
  const svcTokens = svc.split('-').filter(Boolean);
  if (svcTokens.length === 0) return false;

  for (const seg of file.split(/[/\\]/).filter(Boolean)) {
    const segLower = seg.toLowerCase();
    // 1) 세그먼트 자체가 서비스명/하이픈제거형 (order-service/ 또는 orderservice/ 디렉터리)
    if (segLower === svc || segLower === svcCompact) return true;
    // 2) 세그먼트를 토큰화(camelCase + 구분자)했을 때 서비스 토큰열이 연속 부분열로 등장
    const tokens = seg
      .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
      .split(/[._\-\s]+/)
      .map((t) => t.toLowerCase())
      .filter(Boolean);
    if (containsContiguous(tokens, svcTokens)) return true;
  }
  return false;
}

/** needle 토큰열이 haystack 토큰열에 연속 부분열로 등장하는지 확인한다. */
function containsContiguous(haystack: string[], needle: string[]): boolean {
  if (needle.length === 0 || needle.length > haystack.length) return false;
  for (let i = 0; i <= haystack.length - needle.length; i++) {
    let match = true;
    for (let j = 0; j < needle.length; j++) {
      if (haystack[i + j] !== needle[j]) {
        match = false;
        break;
      }
    }
    if (match) return true;
  }
  return false;
}
