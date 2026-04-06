/**
 * 칼라(Khala) HTTP 클라이언트
 *
 * 칼라 API를 호출하는 fetch 기반 클라이언트.
 * 모든 호출에 타임아웃(기본 3초)과 graceful degradation을 적용한다.
 *
 * 규정 문서: docs/probe-v0.4-scope.md § 3
 */

import { logger } from '../utils/logger.js';
import type {
  KhalaClientConfig,
  KhalaResponse,
  KhalaSearchResult,
  KhalaAnswerResult,
  KhalaGraphResult,
  KhalaDiffResult,
} from './types.js';

/** 기본 설정 */
const DEFAULT_CONFIG: KhalaClientConfig = {
  baseUrl: 'http://localhost:8000',
  timeoutMs: 3000,
  tenant: 'default',
  classificationMax: 'INTERNAL',
};

/**
 * 칼라 API 클라이언트.
 *
 * 칼라가 없거나 장애 시 에러를 던지지 않고 null을 반환한다.
 * 호출부에서 fallback 처리를 해야 한다.
 */
export class KhalaClient {
  private readonly config: KhalaClientConfig;

  constructor(config?: Partial<KhalaClientConfig>) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  /**
   * 칼라 서버 가용 여부를 확인한다.
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
   * 하이브리드 검색 (BM25 + Vector + Graph + RRF).
   */
  async search(query: string, options?: {
    topK?: number;
    includeGraph?: boolean;
    includeEvidence?: boolean;
  }): Promise<KhalaSearchResult | null> {
    return this.post<KhalaSearchResult>('/search', {
      query,
      top_k: options?.topK ?? 5,
      route: 'auto',
      classification_max: this.config.classificationMax,
      include_graph: options?.includeGraph ?? true,
      include_evidence: options?.includeEvidence ?? true,
    }, 'search');
  }

  /**
   * 검색 + LLM 근거 기반 답변.
   */
  async searchAnswer(query: string, options?: {
    topK?: number;
  }): Promise<KhalaAnswerResult | null> {
    return this.post<KhalaAnswerResult>('/search/answer', {
      query,
      top_k: options?.topK ?? 5,
      route: 'auto',
      classification_max: this.config.classificationMax,
    }, 'searchAnswer');
  }

  /**
   * 엔티티 그래프 조회 (1~2홉 이웃).
   */
  async getGraph(entityRid: string, options?: {
    hops?: number;
  }): Promise<KhalaGraphResult | null> {
    const hops = options?.hops ?? 1;
    const params = new URLSearchParams({
      hops: String(hops),
      tenant: this.config.tenant,
    });
    return this.get<KhalaGraphResult>(
      `/graph/${encodeURIComponent(entityRid)}?${params.toString()}`,
      'getGraph',
    );
  }

  /**
   * 설계-관측 diff 보고서.
   */
  async getDiff(options?: {
    flagFilter?: string;
  }): Promise<KhalaDiffResult | null> {
    const params = new URLSearchParams({ tenant: this.config.tenant });
    if (options?.flagFilter) {
      params.set('flag_filter', options.flagFilter);
    }
    return this.get<KhalaDiffResult>(`/diff?${params.toString()}`, 'getDiff');
  }

  // ─── 내부 헬퍼 ───

  /**
   * GET 요청을 보내고 data 필드를 반환한다.
   */
  private async get<T>(path: string, context: string): Promise<T | null> {
    try {
      const response = await this.fetchWithTimeout(path, { method: 'GET' });
      if (!response.ok) {
        logger.debug(`칼라 ${context} 실패: HTTP ${response.status}`);
        return null;
      }
      const body = await response.json() as KhalaResponse<T>;
      if (!body.success) {
        logger.debug(`칼라 ${context} 실패: ${body.error}`);
        return null;
      }
      return body.data;
    } catch (error) {
      logger.debug(`칼라 ${context} 에러:`, String(error));
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
        logger.debug(`칼라 ${context} 실패: HTTP ${response.status}`);
        return null;
      }
      const data = await response.json() as KhalaResponse<T>;
      if (!data.success) {
        logger.debug(`칼라 ${context} 실패: ${data.error}`);
        return null;
      }
      return data.data;
    } catch (error) {
      logger.debug(`칼라 ${context} 에러:`, String(error));
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
 * 칼라 조회를 시도하고, 실패 시 fallback 값을 반환한다.
 *
 * 모든 칼라 연동 코드에서 이 패턴을 사용한다.
 *
 * @example
 * ```typescript
 * const docs = await withKhalaFallback(
 *   () => client.search("payment-service 규정"),
 *   null,
 *   "search",
 * );
 * ```
 */
export async function withKhalaFallback<T>(
  fn: () => Promise<T>,
  fallback: T,
  context: string,
): Promise<T> {
  try {
    return await fn();
  } catch (error) {
    logger.debug(`칼라 조회 실패 (${context}): ${error} — 기본값으로 진행`);
    return fallback;
  }
}
