/**
 * 리뷰 그라운딩 오케스트레이션 (v0.6) — 변경 엔티티 빌드, 티어 결정, grounder 호출.
 *
 * Probe는 diff 소스를 의미 분석하지 않는다 — 변경 파일→엔티티 라우팅까지만.
 * 규정 문서: docs/superpowers/specs/2026-06-07-grounded-code-review-design.md
 */
import { NexusClient } from '../nexus/client.js';
import { determineTier } from '../nexus/tier.js';
import { groundReview, type ReviewGroundOptions } from '../nexus/review-grounder.js';
import { extractServiceNames, fileBelongsToService } from '../nexus/context-enricher.js';
import type { ChangedEntity, ReviewGroundingPack } from '../nexus/types.js';
import type { DetectedGroup } from './scope-analyzer.js';

/**
 * 응집 그룹 + 변경 파일에서 ChangedEntity[]를 만든다 (순수 — 소스 의미분석 없음).
 *
 * @param groups scope-analyzer가 반환한 응집 그룹 목록
 * @param changedFiles diff에서 추출한 변경 파일 경로 목록
 */
export function buildChangedEntities(groups: DetectedGroup[], changedFiles: string[]): ChangedEntity[] {
  const groupOf = new Map<string, string>(); // entityName → cohesionGroup
  for (const group of groups) {
    for (const name of extractServiceNames([group])) {
      if (!groupOf.has(name)) groupOf.set(name, group.groupName);
    }
  }
  const entities: ChangedEntity[] = [];
  for (const name of groupOf.keys()) {
    const files = changedFiles.filter((f) => fileBelongsToService(f, name));
    entities.push({ entityName: name, changedFiles: files, cohesionGroup: groupOf.get(name) });
  }
  return entities;
}

/**
 * 리뷰 그라운딩 전체 실행.
 *
 * Nexus 상태를 프로브해 티어를 결정하고, groundReview를 호출해 ReviewGroundingPack을 반환한다.
 * 변경 엔티티가 없으면 ok:false를 반환한다.
 *
 * @param changedEntities buildChangedEntities로 라우팅된 변경 엔티티
 * @param client Nexus 클라이언트
 * @param options 검색 topK·그래프 홉·스펙 마커 등 부분 옵션
 */
export async function runReviewGround(
  changedEntities: ChangedEntity[],
  client: NexusClient,
  options?: Partial<ReviewGroundOptions>,
): Promise<{ ok: false; reason: string } | { ok: true; pack: ReviewGroundingPack }> {
  if (changedEntities.length === 0) {
    return {
      ok: false,
      reason: '변경 엔티티를 귀속하지 못함 (No changed entities). 파일 경로/플랫폼 프로파일을 확인하세요.',
    };
  }

  const probe = await client.getStatusProbe();
  const status = probe.ok ? probe.status : null;
  const tierDecision = determineTier(status, probe.ok ? undefined : probe.reason);

  const pack = await groundReview(client, changedEntities, {
    tier: tierDecision.tier,
    searchTopK: options?.searchTopK,
    graphHops: options?.graphHops,
    specMarkers: options?.specMarkers,
  });
  pack.tierReason = tierDecision.reason;

  return { ok: true, pack };
}
