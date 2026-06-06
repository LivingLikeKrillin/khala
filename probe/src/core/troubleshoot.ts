/**
 * 트러블슈팅 오케스트레이션 — 입력검증, 티어 결정, grounder 호출, caveat 수집
 *
 * 규정 문서: docs/superpowers/specs/2026-06-06-troubleshooting-grounding-design.md §5, §6
 */

import { KhalaClient } from '../khala/client.js';
import { localizeError, inferKind } from '../khala/error-localizer.js';
import { groundTroubleshooting } from '../khala/troubleshoot-grounder.js';
import type {
  TroubleshootInput, GroundingPack, KhalaStatusResult,
} from '../khala/types.js';

const MAX_SIGNAL_LEN = 8_000;

/** 입력 검증 결과 */
export interface ValidatedInput {
  ok: boolean;
  signal?: string;
  reason?: string;
  caveats: string[];
}

/**
 * 입력을 검증한다 (Khala 호출 전).
 */
export function validateInput(input: TroubleshootInput): ValidatedInput {
  const caveats: string[] = [];
  const signal = (input.signal ?? '').trim();
  if (!signal) {
    return { ok: false, reason: '입력 신호가 비어 있습니다 (Empty signal). 예: probe troubleshoot "<에러/스택트레이스>"', caveats };
  }
  let trimmed = signal;
  if (signal.length > MAX_SIGNAL_LEN) {
    trimmed = signal.slice(0, MAX_SIGNAL_LEN);
    caveats.push(`입력이 길어 앞 ${MAX_SIGNAL_LEN}자로 절단함 (Signal truncated)`);
  }
  return { ok: true, signal: trimmed, caveats };
}

/** 티어 결정 결과 */
export interface TierDecision {
  tier: 0 | 1 | 2 | 3;
  reason: string;
}

/**
 * /status 카운트로 그라운딩 티어를 결정한다 (스펙 §5.2).
 */
export function determineTier(status: KhalaStatusResult | null): TierDecision {
  if (!status || !status.db_connected) {
    return { tier: 0, reason: 'Khala 미가용 → T0 (국소화·프로파일만)' };
  }
  const obs = status.observed_edges_count ?? 0;
  const edges = status.edges_count ?? 0;
  const docs = status.documents_count ?? 0;
  if (obs > 0) return { tier: 3, reason: `관측 엣지 ${obs}개 → T3 (운영신호·설계-관측 갭 포함)` };
  if (edges > 0) return { tier: 2, reason: `설계 엣지 ${edges}개, 관측 0 → T2 (토폴로지·영향)` };
  if (docs > 0) return { tier: 1, reason: `문서 ${docs}개, 엣지 0 → T1 (RAG 지식만)` };
  return { tier: 0, reason: 'Khala 연결됐으나 인덱싱 데이터 없음 → T0' };
}

/**
 * 트러블슈팅 그라운딩 전체 실행.
 */
export async function runTroubleshoot(
  input: TroubleshootInput,
  client: KhalaClient,
  changedServices?: { service: string; changedFiles: string[] }[],
): Promise<{ ok: false; reason: string } | { ok: true; pack: GroundingPack }> {
  const v = validateInput(input);
  if (!v.ok) return { ok: false, reason: v.reason! };

  const kind = input.kind ?? inferKind(v.signal!);
  const suspects = localizeError({ ...input, signal: v.signal!, kind });

  const status = await client.getStatus();
  const tierDecision = determineTier(status);

  if (suspects.length === 0) {
    return {
      ok: true,
      pack: {
        tier: tierDecision.tier, tierReason: tierDecision.reason, suspects: [],
        caveats: [...v.caveats, '의심 지점을 국소화하지 못함 — 스택트레이스/파일경로/서비스명을 포함해 다시 시도'],
      },
    };
  }

  const pack = await groundTroubleshooting(client, suspects, {
    signal: v.signal!, tier: tierDecision.tier, changedServices,
  });
  pack.tierReason = tierDecision.reason;
  pack.caveats.unshift(...v.caveats);

  const lowConf = suspects.filter((s) => s.confidence < 0.3);
  if (lowConf.length) {
    pack.caveats.push(`신뢰도 낮은 의심 지점 ${lowConf.length}개 — 참고만: ${lowConf.map((s) => s.entityName).join(', ')}`);
  }
  if (!pack.domainInvariants) {
    pack.caveats.push('도메인 불변식 그라운딩은 Archon 미연동으로 생략됨');
  }

  return { ok: true, pack };
}
