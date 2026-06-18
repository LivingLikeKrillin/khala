/**
 * A2A task artifact → NexusAnswerResult 매핑 (Phase 1, SPEC §5.4)
 *
 * Phase 0 서버 매핑의 클라이언트 측 역연산. grounding 필드는 무손실,
 * 근거 없음(failed task 또는 evidence 0건)은 null로 강등한다 — "근거 없는 답변 금지"
 * 불변식을 소비자 측에서 그대로 지키고, Nexus 선택성(실패 시 fallback)을 보존한다.
 */

import type { NexusAnswerResult } from '../types.js';
import type { A2AGroundingData, A2APart, A2ATask } from './types.js';
import { TASK_STATE_FAILED } from './types.js';

/** parts에서 첫 text part의 텍스트를 반환한다. */
function textOf(parts: A2APart[]): string {
  const part = parts.find((p) => p.kind === 'text' && typeof p.text === 'string');
  return part?.text ?? '';
}

/** parts에서 첫 data part의 페이로드를 반환한다. */
function dataOf(parts: A2APart[]): A2AGroundingData | null {
  const part = parts.find((p) => p.kind === 'data' && p.data !== undefined);
  return (part?.data as A2AGroundingData | undefined) ?? null;
}

/**
 * A2A Task를 NexusAnswerResult로 매핑한다. 근거가 없으면 null.
 *
 * @param task message/send 결과 Task
 * @returns grounded answer, 또는 null(failed/근거없음/형식오류)
 */
export function mapTaskToAnswerResult(task: A2ATask | null | undefined): NexusAnswerResult | null {
  if (!task || task.status?.state === TASK_STATE_FAILED) {
    return null;
  }

  const artifact = task.artifacts?.[0];
  if (!artifact || !Array.isArray(artifact.parts)) {
    return null;
  }

  const data = dataOf(artifact.parts);
  const evidence = Array.isArray(data?.evidence) ? data!.evidence : [];
  // 근거 없는 confident answer 금지(Phase 0 §6.1) — 소비자 측 가드.
  if (evidence.length === 0) {
    return null;
  }

  return {
    answer: textOf(artifact.parts),
    evidence_snippets: evidence,
    // Phase 0 DataPart는 graph_findings를 포함하지 않는다 (SPEC §5.4 decision b).
    graph_findings: null,
    provenance: data?.provenance ?? [],
    route_used: typeof data?.route === 'string' ? data.route : '',
    timing_ms: {},
  };
}
