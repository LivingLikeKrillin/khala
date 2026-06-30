/**
 * 두 grounder(troubleshoot v0.5 / review v0.6) 공유 Nexus 섹션 헬퍼.
 * 동일 호출의 중복을 막기 위해 추출됐다 — 출력 팩 조립만 각 grounder가 한다.
 */
import type { NexusClient } from './client.js';
import type { DesignGap, RelevantDoc } from './types.js';

/** 각 엔티티의 엔티티 스코프 /diff를 합쳐 DesignGap[]로 변환한다.
 *  모든 diff 조회가 null이면 throw해 상위 withNexusFallback이 caveat을 남기게 한다. */
export async function fetchEntityGaps(client: NexusClient, names: string[]): Promise<DesignGap[]> {
  const results = await Promise.all(names.map((n) => client.getDiff({ entityFilter: n })));
  const ok = results.filter((r) => r !== null);
  if (ok.length === 0 && names.length > 0) {
    throw new Error('diff 조회 전체 실패 (All diff lookups failed)');
  }
  const gaps: DesignGap[] = [];
  for (const r of ok) {
    for (const d of r!.diffs) {
      gaps.push({
        flag: d.flag,
        fromName: d.from_name,
        toName: d.to_name,
        edgeType: d.edge_type,
        detail: d.detail,
        // 기존 context-enricher.ts 패턴과 일관: 모든 설계 근거를 join
        designedEvidence:
          d.designed_evidence.length > 0 ? d.designed_evidence.map((e) => e.text).join('; ') : undefined,
        observedEvidence: d.observed_evidence?.sample_trace_ids,
      });
    }
  }
  return gaps;
}

/** 쿼리로 문서를 검색해 RelevantDoc[]로 매핑한다. 실패 시 null.
 *  슬라이싱 없이 주어진 쿼리를 그대로 사용한다 — 호출 측에서 필요 시 자름. */
export async function searchDocs(client: NexusClient, query: string, topK: number): Promise<RelevantDoc[] | null> {
  const result = await client.search(query, { topK });
  if (!result) return null;
  return result.results.map((h) => ({
    docTitle: h.doc_title,
    sectionPath: h.section_path,
    snippet: h.snippet,
    score: h.score,
    classification: h.classification,
  }));
}
