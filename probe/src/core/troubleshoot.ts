/**
 * 트러블슈팅 오케스트레이션 — 입력검증, 티어 결정, grounder 호출, caveat 수집
 *
 * 규정 문서: docs/superpowers/specs/2026-06-06-troubleshooting-grounding-design.md §5, §6
 */

import { NexusClient } from '../nexus/client.js';
import { localizeError, inferKind } from '../nexus/error-localizer.js';
import { groundTroubleshooting } from '../nexus/troubleshoot-grounder.js';
import type { TroubleshootInput, GroundingPack } from '../nexus/types.js';

// 티어 결정은 nexus/tier로 이전됨 (순환 방지). back-compat re-export.
import { determineTier } from '../nexus/tier.js';
export { determineTier } from '../nexus/tier.js';
export type { TierDecision } from '../nexus/tier.js';

const MAX_SIGNAL_LEN = 8_000;

/** 입력 검증 결과 */
export interface ValidatedInput {
  ok: boolean;
  signal?: string;
  reason?: string;
  caveats: string[];
}

/**
 * 입력을 검증한다 (Nexus 호출 전).
 */
export function validateInput(input: TroubleshootInput): ValidatedInput {
  const caveats: string[] = [];
  const signal = (input.signal ?? '').trim();
  if (!signal) {
    return {
      ok: false,
      reason: '입력 신호가 비어 있습니다 (Empty signal). 예: probe troubleshoot "<에러/스택트레이스>"',
      caveats,
    };
  }
  let trimmed = signal;
  if (signal.length > MAX_SIGNAL_LEN) {
    trimmed = signal.slice(0, MAX_SIGNAL_LEN);
    caveats.push(`입력이 길어 앞 ${MAX_SIGNAL_LEN}자로 절단함 (Signal truncated)`);
  }
  return { ok: true, signal: trimmed, caveats };
}

/**
 * 트러블슈팅 그라운딩 전체 실행.
 */
export async function runTroubleshoot(
  input: TroubleshootInput,
  client: NexusClient,
  changedServices?: { service: string; changedFiles: string[] }[],
): Promise<{ ok: false; reason: string } | { ok: true; pack: GroundingPack }> {
  const v = validateInput(input);
  if (!v.ok) return { ok: false, reason: v.reason! };

  const kind = input.kind ?? inferKind(v.signal!);
  const suspects = localizeError({ ...input, signal: v.signal!, kind });

  const probe = await client.getStatusProbe();
  const status = probe.ok ? probe.status : null;
  const tierDecision = determineTier(status, probe.ok ? undefined : probe.reason);

  if (suspects.length === 0) {
    return {
      ok: true,
      pack: {
        tier: tierDecision.tier,
        tierReason: tierDecision.reason,
        suspects: [],
        caveats: [...v.caveats, '의심 지점을 국소화하지 못함 — 스택트레이스/파일경로/서비스명을 포함해 다시 시도'],
      },
    };
  }

  const pack = await groundTroubleshooting(client, suspects, {
    signal: v.signal!,
    tier: tierDecision.tier,
    changedServices,
  });
  pack.tierReason = tierDecision.reason;
  pack.caveats.unshift(...v.caveats);

  const lowConf = suspects.filter((s) => s.confidence < 0.3);
  if (lowConf.length) {
    pack.caveats.push(
      `신뢰도 낮은 의심 지점 ${lowConf.length}개 — 참고만: ${lowConf.map((s) => s.entityName).join(', ')}`,
    );
  }
  if (!pack.domainInvariants) {
    pack.caveats.push('도메인 불변식 그라운딩은 Archon 미연동으로 생략됨');
  }
  if (input.kind && input.kind !== inferKind(v.signal!)) {
    pack.caveats.push(
      `입력 kind 힌트(${input.kind})가 본문 추론(${inferKind(v.signal!)})과 달라 힌트를 무시함 (kind hint overridden)`,
    );
  }

  return { ok: true, pack };
}
