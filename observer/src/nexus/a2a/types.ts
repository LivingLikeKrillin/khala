/**
 * A2A 와이어 타입 (Observer가 클라이언트로서 소비하는 최소 부분집합)
 *
 * Phase 0 Nexus A2A 서버(specs/SPEC-nexus-a2a-server-phase0-spike.md)가 JSON-RPC 2.0로
 * 내보내는 Agent Card / Task / Artifact 중 Observer가 실제로 읽는 필드만 정의한다.
 * 전체 A2A 스키마를 끌어오지 않음으로써 Observer의 의존성/에어갭 기조를 유지한다(SPEC §5.3).
 */

/** A2A Part — text 또는 data(application/json) */
export interface A2APart {
  kind: string;
  text?: string;
  data?: Record<string, unknown>;
}

/** A2A Artifact — task 산출물 */
export interface A2AArtifact {
  artifactId?: string;
  name?: string;
  parts: A2APart[];
}

/** A2A Task 상태 */
export interface A2ATaskStatus {
  /** "completed" | "failed" | ... (JSON-RPC 와이어 형식, kebab/lowercase) */
  state: string;
  message?: unknown;
}

/** A2A Task — message/send 결과 */
export interface A2ATask {
  id?: string;
  contextId?: string;
  kind?: string;
  status: A2ATaskStatus;
  artifacts?: A2AArtifact[];
}

/** retrieve_grounded artifact의 data part 페이로드 (Phase 0 §5.4) */
export interface A2AGroundingData {
  evidence?: unknown[];
  provenance?: unknown;
  confidence?: string;
  route?: string;
  policy?: unknown;
}

/** Agent Card — Observer가 발견에 사용하는 최소 필드 */
export interface A2AAgentCard {
  name: string;
  url: string;
  skills: Array<{ id: string; name?: string }>;
  capabilities?: Record<string, unknown>;
}

/** retrieve_grounded skill id */
export const RETRIEVE_GROUNDED_SKILL = 'retrieve_grounded';

/** A2A failed task 상태의 JSON-RPC 와이어 값 */
export const TASK_STATE_FAILED = 'failed';

/** A2A completed task 상태의 JSON-RPC 와이어 값 */
export const TASK_STATE_COMPLETED = 'completed';
