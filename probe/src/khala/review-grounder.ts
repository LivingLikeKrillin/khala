/**
 * 리뷰 Grounding Pack 조립 (v0.6)
 *
 * ChangedEntity[]와 KhalaClient로 §2~§6 섹션을 병렬 조립한다.
 * 각 섹션은 독립 실패해도 나머지를 막지 않는다 (withKhalaFallback).
 * Probe는 diff 소스를 의미 분석하지 않는다 — 변경 엔티티에 대한 조직 그라운딩만 모은다.
 *
 * 규정 문서: docs/superpowers/specs/2026-06-07-grounded-code-review-design.md
 */
import { KhalaClient, withKhalaFallback } from './client.js';
import { analyzeImpact } from './impact-analyzer.js';
import { fetchEntityGaps, searchDocs } from './grounding-sections.js';
import type {
  ChangedEntity, ReviewGroundingPack, SpecRef, RelevantDoc, ImpactAnalysis,
} from './types.js';

/** 승인 스펙 식별 기본 마커 (production 마커는 추후 튜닝) */
const DEFAULT_SPEC_MARKERS = ['spec', '스펙', 'adr', 'rfc'];

export interface ReviewGroundOptions {
  tier: 0 | 1 | 2 | 3;
  searchTopK?: number;
  graphHops?: number;
  /** 승인 스펙 식별 마커 (제목/섹션경로에 포함되면 specRef로 투영) */
  specMarkers?: string[];
}

/** 검색 문서를 승인 스펙(specRefs)과 일반 규정(guidelines)으로 분리한다.
 *  한 문서가 양쪽에 중복되지 않도록 배타 분배한다. */
export function partitionDocs(
  docs: RelevantDoc[], specMarkers: string[],
): { specRefs: SpecRef[]; guidelines: RelevantDoc[] } {
  const specRefs: SpecRef[] = [];
  const guidelines: RelevantDoc[] = [];
  for (const d of docs) {
    const hay = `${d.docTitle} ${d.sectionPath}`.toLowerCase();
    if (specMarkers.some((m) => hay.includes(m.toLowerCase()))) {
      specRefs.push({
        docTitle: d.docTitle, sectionPath: d.sectionPath,
        snippet: d.snippet, classification: d.classification,
      });
    } else {
      guidelines.push(d);
    }
  }
  return { specRefs, guidelines };
}

/** 변경 엔티티에 대한 Review Grounding Pack을 조립한다 (티어가 허용하는 섹션까지). */
export async function groundReview(
  client: KhalaClient,
  changedEntities: ChangedEntity[],
  options: ReviewGroundOptions,
): Promise<ReviewGroundingPack> {
  const caveats: string[] = [];
  const pack: ReviewGroundingPack = {
    tier: options.tier, tierReason: '', changedEntities, caveats,
  };
  const names = changedEntities.map((e) => e.entityName);

  // §2/§3 지식 → 규정 + 승인 스펙 분리 (T1+)
  if (options.tier >= 1 && names.length > 0) {
    const docs = await withKhalaFallback(
      () => searchDocs(client, names.join(' '), options.searchTopK ?? 5),
      null, 'search',
    );
    if (docs) {
      const { specRefs, guidelines } = partitionDocs(docs, options.specMarkers ?? DEFAULT_SPEC_MARKERS);
      if (guidelines.length) pack.applicableGuidelines = guidelines;
      if (specRefs.length) pack.specRefs = specRefs;
      else caveats.push('변경 엔티티에 대한 승인 스펙 미발견 (No approved spec found)');
    } else {
      caveats.push('지식 그라운딩(search) 조회 실패 (Knowledge grounding unavailable)');
    }
  }

  // §4 토폴로지/영향 (T2+)
  if (options.tier >= 2 && names.length > 0) {
    const topology = await withKhalaFallback<ImpactAnalysis | null>(
      () => analyzeImpact(client, names, { hops: options.graphHops ?? 2 }),
      null, 'impact',
    );
    if (topology) pack.topology = topology;
  }

  // §5 설계-관측 갭 (doc_only는 T2+, observed_only/conflict는 T3)
  if (options.tier >= 2 && names.length > 0) {
    const gaps = await withKhalaFallback(
      () => fetchEntityGaps(client, names),
      null, 'diff',
    );
    if (gaps) {
      pack.designObservationGaps = options.tier >= 3
        ? gaps
        : gaps.filter((g) => g.flag === 'doc_only');
    } else {
      caveats.push('설계-관측 갭(diff) 조회 실패 (Design-observation gap unavailable)');
    }
  }

  // §6 도메인 claim drift — Archon seam (미연동 시 생략 + caveat)
  if (!pack.claimDrift) {
    caveats.push('도메인 claim drift 그라운딩은 Archon 미연동으로 생략됨 (Archon not integrated)');
  }

  return pack;
}
