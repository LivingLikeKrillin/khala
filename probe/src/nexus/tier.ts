/**
 * 그라운딩 티어 결정 — /status 카운트와 실패 사유로 T0~T3을 판정한다.
 * v0.5(troubleshoot)와 v0.6(review)이 공유한다. nexus 레이어에 둬서 순환을 피한다.
 */
import type { NexusStatusResult } from './types.js';

export interface TierDecision {
  tier: 0 | 1 | 2 | 3;
  reason: string;
}

/**
 * /status 카운트로 그라운딩 티어를 결정한다 (스펙 §5.2).
 *
 * @param status /status 응답 (실패 시 null)
 * @param failure status가 null일 때의 실패 사유 — 'timeout'(느림/콜드스타트)과
 *   'unreachable'(미가용)을 구분해 T0 사유 문구를 다르게 남긴다.
 */
export function determineTier(
  status: NexusStatusResult | null,
  failure?: 'timeout' | 'unreachable',
): TierDecision {
  if (!status || !status.db_connected) {
    if (failure === 'timeout') {
      return {
        tier: 0,
        reason: 'Nexus 응답 시간 초과 → T0 (느림/콜드스타트 가능 — 재시도 권장, Nexus timeout)',
      };
    }
    return { tier: 0, reason: 'Nexus 미가용 → T0 (국소화·프로파일만)' };
  }
  const obs = status.observed_edges_count ?? 0;
  const edges = status.edges_count ?? 0;
  const docs = status.documents_count ?? 0;
  if (obs > 0) return { tier: 3, reason: `관측 엣지 ${obs}개 → T3 (운영신호·설계-관측 갭 포함)` };
  if (edges > 0) return { tier: 2, reason: `설계 엣지 ${edges}개, 관측 0 → T2 (토폴로지·영향)` };
  if (docs > 0) return { tier: 1, reason: `문서 ${docs}개, 엣지 0 → T1 (RAG 지식만)` };
  return { tier: 0, reason: 'Nexus 연결됐으나 인덱싱 데이터 없음 → T0' };
}
