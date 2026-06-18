/**
 * Nexus HTTP 클라이언트
 *
 * Nexus API를 호출하는 fetch 기반 클라이언트.
 * 모든 호출에 타임아웃(기본 10초)과 graceful degradation을 적용한다.
 *
 * 규정 문서: docs/probe-v0.4-scope.md § 3
 */

import { logger } from '../utils/logger.js';
import { A2ANexusTransport } from './a2a/transport.js';
import type {
  NexusClientConfig,
  NexusResponse,
  NexusSearchResult,
  NexusAnswerResult,
  NexusGraphResult,
  NexusDiffResult,
  NexusStatusResult,
} from './types.js';

/** 기본 설정 */
const DEFAULT_CONFIG: NexusClientConfig = {
  baseUrl: 'http://localhost:8000',
  // 콜드 스타트한 도커 Nexus는 첫 응답까지 ~8-9초가 걸린다. 3초는 너무 짧아
  // 멀쩡한 Nexus를 "미가용"으로 오판(→ T0 강등)했다. 10초로 상향.
  timeoutMs: 10_000,
  tenant: 'default',
  classificationMax: 'INTERNAL',
};

/**
 * /status 프로브 결과 — 가용성과 함께 실패 사유(느림 vs 단절)를 구분해 반환한다.
 * 단순 null 반환으로는 "타임아웃(느림)"과 "연결 불가(단절)"를 구분할 수 없어
 * 티어 강등 사유가 모호해지는 문제를 해결한다.
 */
export type NexusStatusProbe =
  | { ok: true; status: NexusStatusResult }
  | { ok: false; reason: 'timeout' | 'unreachable' };

/**
 * Nexus API 클라이언트.
 *
 * Nexus가 없거나 장애 시 에러를 던지지 않고 null을 반환한다.
 * 호출부에서 fallback 처리를 해야 한다.
 */
export class NexusClient {
  private readonly config: NexusClientConfig;

  constructor(config?: Partial<NexusClientConfig>) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  /**
   * Nexus 서버 가용 여부를 확인한다.
   */
  async isAvailable(): Promise<boolean> {
    try {
      const response = await this.fetchWithTimeout('/status', { method: 'GET' });
      return response.ok;
    } catch {
      return false;
    }
  }

  /**
   * 시스템 상태를 조회한다 (가용성·티어 진단용).
   */
  async getStatus(): Promise<NexusStatusResult | null> {
    return this.get<NexusStatusResult>('/status', 'getStatus');
  }

  /**
   * 시스템 상태를 조회하되, 실패 시 사유(timeout vs unreachable)를 함께 반환한다.
   * 티어 결정 시 "느림(콜드스타트)"과 "단절(미가용)"을 구분하기 위해 사용한다.
   */
  async getStatusProbe(): Promise<NexusStatusProbe> {
    try {
      const response = await this.fetchWithTimeout('/status', { method: 'GET' });
      if (!response.ok) {
        logger.debug(`Nexus getStatusProbe 실패: HTTP ${response.status}`);
        return { ok: false, reason: 'unreachable' };
      }
      const body = (await response.json()) as NexusResponse<NexusStatusResult>;
      if (!body.success || !body.data) {
        logger.debug(`Nexus getStatusProbe 실패: ${body.error}`);
        return { ok: false, reason: 'unreachable' };
      }
      return { ok: true, status: body.data };
    } catch (error) {
      const reason = isTimeoutError(error) ? 'timeout' : 'unreachable';
      logger.debug(`Nexus getStatusProbe 에러(${reason}):`, String(error));
      return { ok: false, reason };
    }
  }

  /**
   * 하이브리드 검색 (BM25 + Vector + Graph + RRF).
   */
  async search(
    query: string,
    options?: {
      topK?: number;
      includeGraph?: boolean;
      includeEvidence?: boolean;
    },
  ): Promise<NexusSearchResult | null> {
    return this.post<NexusSearchResult>(
      '/search',
      {
        query,
        top_k: options?.topK ?? 5,
        route: 'auto',
        classification_max: this.config.classificationMax,
        include_graph: options?.includeGraph ?? true,
        include_evidence: options?.includeEvidence ?? true,
      },
      'search',
    );
  }

  /**
   * 검색 + LLM 근거 기반 답변.
   *
   * 전송 방식은 config.transport(기본 "http") 또는 환경변수 PROBE_NEXUS_TRANSPORT로 결정한다.
   * "a2a"이면 Nexus의 A2A retrieve_grounded skill을 사용하고, 실패 시 null로 강등한다
   * (Nexus 선택성 보존 — Probe 원칙 #5). 반환 타입은 두 경로가 동일하다(drop-in).
   */
  async searchAnswer(
    query: string,
    options?: {
      topK?: number;
    },
  ): Promise<NexusAnswerResult | null> {
    if (this.resolveTransport() === 'a2a') {
      const a2a = new A2ANexusTransport({
        baseUrl: this.config.baseUrl,
        token: this.config.nexusToken ?? process.env.PROBE_NEXUS_TOKEN,
        timeoutMs: this.config.timeoutMs,
      });
      return a2a.retrieveGrounded(query);
    }
    return this.post<NexusAnswerResult>(
      '/search/answer',
      {
        query,
        top_k: options?.topK ?? 5,
        route: 'auto',
        classification_max: this.config.classificationMax,
      },
      'searchAnswer',
    );
  }

  /** searchAnswer 전송 방식 결정: config 우선, 없으면 환경변수, 기본 "http". */
  private resolveTransport(): 'http' | 'a2a' {
    if (this.config.transport) {
      return this.config.transport;
    }
    return process.env.PROBE_NEXUS_TRANSPORT === 'a2a' ? 'a2a' : 'http';
  }

  /**
   * 엔티티 그래프 조회 (1~2홉 이웃).
   */
  async getGraph(
    entityRid: string,
    options?: {
      hops?: number;
    },
  ): Promise<NexusGraphResult | null> {
    const hops = options?.hops ?? 1;
    const params = new URLSearchParams({
      hops: String(hops),
      tenant: this.config.tenant,
    });
    return this.get<NexusGraphResult>(`/graph/${encodeURIComponent(entityRid)}?${params.toString()}`, 'getGraph');
  }

  /**
   * 설계-관측 diff 보고서.
   */
  async getDiff(options?: { flagFilter?: string; entityFilter?: string }): Promise<NexusDiffResult | null> {
    const params = new URLSearchParams({ tenant: this.config.tenant });
    if (options?.flagFilter) {
      params.set('flag_filter', options.flagFilter);
    }
    if (options?.entityFilter) {
      params.set('entity_filter', options.entityFilter);
    }
    return this.get<NexusDiffResult>(`/diff?${params.toString()}`, 'getDiff');
  }

  // ─── 내부 헬퍼 ───

  /**
   * GET 요청을 보내고 data 필드를 반환한다.
   */
  private async get<T>(path: string, context: string): Promise<T | null> {
    try {
      const response = await this.fetchWithTimeout(path, { method: 'GET' });
      if (!response.ok) {
        logger.debug(`Nexus ${context} 실패: HTTP ${response.status}`);
        return null;
      }
      const body = (await response.json()) as NexusResponse<T>;
      if (!body.success) {
        logger.debug(`Nexus ${context} 실패: ${body.error}`);
        return null;
      }
      return body.data;
    } catch (error) {
      logger.debug(`Nexus ${context} 에러:`, String(error));
      return null;
    }
  }

  /**
   * POST 요청을 보내고 data 필드를 반환한다.
   */
  private async post<T>(path: string, body: unknown, context: string): Promise<T | null> {
    try {
      const response = await this.fetchWithTimeout(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        logger.debug(`Nexus ${context} 실패: HTTP ${response.status}`);
        return null;
      }
      const data = (await response.json()) as NexusResponse<T>;
      if (!data.success) {
        logger.debug(`Nexus ${context} 실패: ${data.error}`);
        return null;
      }
      return data.data;
    } catch (error) {
      logger.debug(`Nexus ${context} 에러:`, String(error));
      return null;
    }
  }

  /**
   * 타임아웃이 적용된 fetch.
   */
  private async fetchWithTimeout(path: string, init: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.config.timeoutMs);

    try {
      const url = `${this.config.baseUrl}${path}`;
      return await fetch(url, { ...init, signal: controller.signal });
    } finally {
      clearTimeout(timeout);
    }
  }
}

/**
 * 에러가 타임아웃(AbortController abort)에서 비롯됐는지 판별한다.
 * fetch가 abort되면 name이 'AbortError'인 예외를 던지고,
 * 연결 거부(ECONNREFUSED 등)는 그 외 TypeError로 떨어진다.
 */
function isTimeoutError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'name' in error &&
    (error as { name?: unknown }).name === 'AbortError'
  );
}

/**
 * Nexus 조회를 시도하고, 실패 시 fallback 값을 반환한다.
 *
 * 모든 Nexus 연동 코드에서 이 패턴을 사용한다.
 *
 * @example
 * ```typescript
 * const docs = await withNexusFallback(
 *   () => client.search("payment-service 규정"),
 *   null,
 *   "search",
 * );
 * ```
 */
export async function withNexusFallback<T>(fn: () => Promise<T>, fallback: T, context: string): Promise<T> {
  try {
    return await fn();
  } catch (error) {
    logger.debug(`Nexus 조회 실패 (${context}): ${error} — 기본값으로 진행`);
    return fallback;
  }
}
