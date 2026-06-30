import { describe, it, expect } from 'vitest';
import { mapTaskToAnswerResult } from '../src/nexus/a2a/mapping.js';
import type { A2ATask } from '../src/nexus/a2a/types.js';

/**
 * A2A task artifact → NexusAnswerResult 매핑 테스트 (Phase 1, SPEC §5.4)
 *
 * Phase 0 서버가 내보내는 artifact([TextPart(answer), DataPart(evidence packet)])의
 * 클라이언트 측 역매핑. grounding 필드(answer/evidence/provenance/route)는 무손실,
 * 근거 없음(failed) task는 null(graceful degradation).
 */

function groundedTask(): A2ATask {
  return {
    id: 't1',
    contextId: 'c1',
    kind: 'task',
    status: { state: 'completed' },
    artifacts: [
      {
        artifactId: 'a1',
        name: 'grounded_answer',
        parts: [
          { kind: 'text', text: '결제 서비스는 payment.events 토픽을 발행합니다.' },
          {
            kind: 'data',
            data: {
              evidence: [
                {
                  doc_title: 'Payment',
                  section_path: 'Topics',
                  text: 'payment.events 발행',
                  score: 0.9,
                  source_uri: 'git://docs/payment.md',
                },
              ],
              provenance: [{ source_uri: 'git://docs/payment.md', source_version: 'v2', doc_rid: 'd1' }],
              confidence: 'LOW',
              route: 'graph',
              policy: { tenant: 'acme', clearance_applied: 'INTERNAL' },
            },
          },
        ],
      },
    ],
  };
}

describe('mapTaskToAnswerResult', () => {
  it('grounded task를 NexusAnswerResult로 무손실 매핑한다', () => {
    const result = mapTaskToAnswerResult(groundedTask());

    expect(result).not.toBeNull();
    expect(result!.answer).toBe('결제 서비스는 payment.events 토픽을 발행합니다.');
    expect(result!.evidence_snippets).toHaveLength(1);
    expect((result!.evidence_snippets[0] as { source_uri: string }).source_uri).toBe('git://docs/payment.md');
    expect(result!.provenance).toEqual([{ source_uri: 'git://docs/payment.md', source_version: 'v2', doc_rid: 'd1' }]);
    expect(result!.route_used).toBe('graph');
  });

  it('근거 없음(failed) task는 null을 반환한다 (no confident answer)', () => {
    const failed: A2ATask = {
      id: 't2',
      status: { state: 'failed', message: { parts: [{ kind: 'text', text: '근거 부족' }] } },
      artifacts: [
        {
          parts: [
            { kind: 'text', text: '답변을 생성할 수 없습니다 — 근거 부족' },
            { kind: 'data', data: { evidence: [], provenance: [], route: 'vector' } },
          ],
        },
      ],
    };
    expect(mapTaskToAnswerResult(failed)).toBeNull();
  });

  it('completed지만 evidence가 비어 있으면 null을 반환한다 (근거 없는 답변 금지)', () => {
    const empty: A2ATask = {
      id: 't3',
      status: { state: 'completed' },
      artifacts: [
        {
          parts: [
            { kind: 'text', text: 'x' },
            { kind: 'data', data: { evidence: [] } },
          ],
        },
      ],
    };
    expect(mapTaskToAnswerResult(empty)).toBeNull();
  });

  it('artifact가 없으면 null을 반환한다', () => {
    expect(mapTaskToAnswerResult({ id: 't4', status: { state: 'completed' }, artifacts: [] })).toBeNull();
  });

  it('graph_findings는 Phase 1에서 null이다 (DataPart 미포함 — SPEC §5.4 decision b)', () => {
    expect(mapTaskToAnswerResult(groundedTask())!.graph_findings).toBeNull();
  });
});
