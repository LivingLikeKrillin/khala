/**
 * A2A Nexus 클라이언트 전송 (Phase 1, SPEC §5.3)
 *
 * 얇은 JSON-RPC 2.0 클라이언트: Agent Card 발견 → message/send(retrieve_grounded) →
 * task artifact를 NexusAnswerResult로 매핑. `@a2a-js/sdk`를 끌어오지 않아 Observer의
 * 의존성 2개/에어갭 기조를 유지한다. 모든 실패는 null로 강등(Nexus 선택성, Observer 원칙 #5).
 */

import { logger } from '../../utils/logger.js';
import type { NexusAnswerResult } from '../types.js';
import { mapTaskToAnswerResult } from './mapping.js';
import type { A2AAgentCard, A2ATask } from './types.js';
import { RETRIEVE_GROUNDED_SKILL } from './types.js';

/** A2A 전송 설정 */
export interface A2ATransportConfig {
  /** Nexus 호스트 base URL */
  baseUrl: string;
  /** Phase 0 정적 bearer 토큰 (gated skill용). 없으면 default-deny → null */
  token?: string;
  /** 요청 타임아웃 ms */
  timeoutMs: number;
}

const CARD_PATH = '/.well-known/agent-card.json';

/**
 * Nexus를 A2A로 소비하는 전송. card는 인스턴스 단위로 캐시한다.
 */
export class A2ANexusTransport {
  private readonly config: A2ATransportConfig;
  private cardCache: A2AAgentCard | null = null;

  constructor(config: A2ATransportConfig) {
    this.config = config;
  }

  /**
   * retrieve_grounded skill을 호출해 grounded 답변을 받는다.
   *
   * @param query 사용자 질문
   * @returns NexusAnswerResult, 또는 null(미발견/거부/실패/근거없음)
   */
  async retrieveGrounded(query: string): Promise<NexusAnswerResult | null> {
    try {
      const card = await this.discoverCard();
      if (!card) {
        return null;
      }
      if (!card.skills?.some((s) => s.id === RETRIEVE_GROUNDED_SKILL)) {
        logger.debug(`Nexus A2A: 카드에 ${RETRIEVE_GROUNDED_SKILL} skill 없음 — 건너뜀`);
        return null;
      }

      const task = await this.sendMessage(card.url, query);
      if (!task) {
        return null;
      }
      return mapTaskToAnswerResult(task);
    } catch (error) {
      logger.debug('Nexus A2A retrieveGrounded 에러:', String(error));
      return null;
    }
  }

  /** Agent Card를 발견(캐시)한다. 실패 시 null. */
  private async discoverCard(): Promise<A2AAgentCard | null> {
    if (this.cardCache) {
      return this.cardCache;
    }
    const response = await this.fetchWithTimeout(`${this.config.baseUrl}${CARD_PATH}`, { method: 'GET' });
    if (!response.ok) {
      logger.debug(`Nexus A2A: 카드 발견 실패 HTTP ${response.status}`);
      return null;
    }
    const card = (await response.json()) as A2AAgentCard;
    if (!card?.url || !Array.isArray(card.skills)) {
      logger.debug('Nexus A2A: 카드 형식 오류');
      return null;
    }
    this.cardCache = card;
    return card;
  }

  /** message/send JSON-RPC 호출. 결과 Task를 반환하거나 null. */
  private async sendMessage(rpcUrl: string, query: string): Promise<A2ATask | null> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.config.token) {
      headers.Authorization = `Bearer ${this.config.token}`;
    }

    const payload = {
      jsonrpc: '2.0',
      id: '1',
      method: 'message/send',
      params: {
        message: {
          role: 'user',
          messageId: 'observer-1',
          kind: 'message',
          parts: [{ kind: 'text', text: query }],
        },
      },
    };

    const response = await this.fetchWithTimeout(rpcUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      logger.debug(`Nexus A2A: message/send 실패 HTTP ${response.status}`);
      return null;
    }
    const body = (await response.json()) as { result?: A2ATask; error?: { code: number; message: string } };
    if (body.error || !body.result) {
      logger.debug(`Nexus A2A: JSON-RPC error ${body.error?.code} ${body.error?.message ?? ''}`);
      return null;
    }
    return body.result;
  }

  /** 타임아웃이 적용된 fetch. */
  private async fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.config.timeoutMs);
    try {
      return await fetch(url, { ...init, signal: controller.signal });
    } finally {
      clearTimeout(timeout);
    }
  }
}
