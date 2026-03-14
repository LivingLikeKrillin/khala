/**
 * Khala API 클라이언트.
 * KhalaResponse 언래핑, 에러 핸들링, SSE 스트림 파싱.
 */

const BASE = '';

/**
 * 공통 fetch 래퍼. KhalaResponse를 언래핑하고 에러를 처리한다.
 */
export async function request(method, path, body = null, params = null) {
  let url = `${BASE}${path}`;
  if (params) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== null && v !== undefined) qs.set(k, v);
    }
    const s = qs.toString();
    if (s) url += `?${s}`;
  }

  const opts = {
    method,
    headers: {},
  };
  if (body) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }

  const res = await fetch(url, opts);

  if (res.status === 503) {
    throw new ApiError('데이터베이스 연결 실패', 503);
  }

  const json = await res.json();
  if (!json.success) {
    throw new ApiError(json.error || `HTTP ${res.status}`, res.status);
  }
  return { data: json.data, meta: json.meta || {} };
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

// ── 검색 ──

export async function search(query, opts = {}) {
  return request('POST', '/search', {
    query,
    top_k: opts.top_k || 10,
    route: opts.route || 'auto',
    classification_max: opts.classification_max || 'INTERNAL',
    tenant: opts.tenant || 'default',
    include_graph: opts.include_graph !== false,
    include_evidence: opts.include_evidence !== false,
  });
}

export async function searchAnswer(query, opts = {}) {
  return request('POST', '/search/answer', {
    query,
    top_k: opts.top_k || 10,
    route: opts.route || 'auto',
    classification_max: opts.classification_max || 'INTERNAL',
    tenant: opts.tenant || 'default',
  });
}

/**
 * SSE 스트리밍 답변.
 * @param {string} query
 * @param {object} callbacks - { onEvidence, onGraph, onDelta, onDone, onError }
 * @returns {Promise<void>}
 */
export async function streamAnswer(query, callbacks, opts = {}) {
  const res = await fetch(`${BASE}/search/answer/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      top_k: opts.top_k || 10,
      route: opts.route || 'auto',
      classification_max: opts.classification_max || 'INTERNAL',
      tenant: opts.tenant || 'default',
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    callbacks.onError?.({ error: `HTTP ${res.status}: ${text}` });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop(); // 마지막 불완전 라인 보존

    let currentEvent = null;
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ') && currentEvent) {
        try {
          const data = JSON.parse(line.slice(6));
          switch (currentEvent) {
            case 'evidence': callbacks.onEvidence?.(data); break;
            case 'graph': callbacks.onGraph?.(data); break;
            case 'answer_delta': callbacks.onDelta?.(data); break;
            case 'done': callbacks.onDone?.(data); break;
            case 'error': callbacks.onError?.(data); break;
          }
        } catch {
          // JSON 파싱 실패 무시
        }
        currentEvent = null;
      }
    }
  }
}

// ── 그래프 ──

export async function getGraph(entity, opts = {}) {
  return request('GET', `/graph/${encodeURIComponent(entity)}`, null, {
    hops: opts.hops || 1,
    tenant: opts.tenant || 'default',
    include_evidence: opts.include_evidence !== false,
  });
}

// ── 엔티티 자동완성 ──

export async function suggestEntities(q, opts = {}) {
  return request('GET', '/entities/suggest', null, {
    q,
    tenant: opts.tenant || 'default',
    limit: opts.limit || 10,
  });
}

// ── 문서 ──

export async function listDocuments(opts = {}) {
  return request('GET', '/documents', null, {
    tenant: opts.tenant || 'default',
    classification_max: opts.classification_max || 'INTERNAL',
    offset: opts.offset || 0,
    limit: opts.limit || 20,
  });
}

// ── Diff ──

export async function getDiff(opts = {}) {
  return request('GET', '/diff', null, {
    tenant: opts.tenant || 'default',
    flag_filter: opts.flag_filter || null,
    entity_filter: opts.entity_filter || null,
  });
}

// ── OTel ──

export async function otelAggregate(opts = {}) {
  return request('POST', '/otel/aggregate', {
    window_minutes: opts.window_minutes || 5,
    lookback_minutes: opts.lookback_minutes || 60,
    tenant: opts.tenant || 'default',
  });
}

// ── 상태 ──

export async function getStatus() {
  return request('GET', '/status');
}

// ── 업로드 ──

export async function uploadFile(file, path = 'uploads', tenant = 'default') {
  const formData = new FormData();
  formData.append('file', file);

  const url = `${BASE}/upload?path=${encodeURIComponent(path)}&tenant=${encodeURIComponent(tenant)}`;
  const res = await fetch(url, { method: 'POST', body: formData });
  const json = await res.json();

  if (res.status === 409) {
    throw new ApiError(json.detail || '파일이 이미 존재합니다', 409);
  }
  if (!json.success) {
    throw new ApiError(json.error || json.detail || `HTTP ${res.status}`, res.status);
  }
  return { data: json.data, meta: json.meta || {} };
}
