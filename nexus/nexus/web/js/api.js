/**
 * Nexus API 클라이언트.
 * NexusResponse 언래핑, 에러 핸들링, SSE 스트림 파싱.
 */

const BASE = '';

// ── 로컬 dev 온램프 ──
// 서버가 NEXUS_DEV_TOKEN(override 의 로컬 편의 자격)을 노출하면 그 토큰을 Bearer 로 자동 첨부한다.
// → 신규 `task up` 사용자가 토큰을 직접 발급/붙여넣기 없이 검색이 동작. prod(env 미설정)에선
// token=null 이라 헤더 없이 호출 → enforced 정책 그대로(401). 한 번 받아 캐시한다.
let _authToken; // undefined=미로딩, null=없음, string=토큰

async function _ensureAuthToken() {
  if (_authToken !== undefined) return _authToken;
  try {
    const res = await fetch(`${BASE}/auth/dev-token`); // 비-게이트 — 인증 헤더 없이 호출
    const json = await res.json();
    _authToken = (json && json.success && json.data && json.data.token) || null;
  } catch {
    _authToken = null;
  }
  return _authToken;
}

async function authHeaders() {
  const t = await _ensureAuthToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

/**
 * 공통 fetch 래퍼. NexusResponse를 언래핑하고 에러를 처리한다.
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
    headers: { ...(await authHeaders()) },
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
  if (!res.ok || !json.success) {
    // FastAPI 의 HTTPException 은 {detail} 로 온다(봉투가 아니다). 이걸 읽지 않으면
    // 403/409/400 이 전부 "HTTP 403" 이 되어, 사용자는 왜 막혔는지 알 수 없다.
    throw new ApiError(json.error || json.detail || `HTTP ${res.status}`, res.status);
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
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
    body: JSON.stringify({
      query,
      // 대화 이력 — 서버는 U2 에서 받아서 버린다(상한만 건다). 자르기는 호출자가 이미 했다
      // (js/history.js: forRequest). 여기서 조용히 더 자르면 어디서 잘렸는지 알 수 없어진다.
      history: opts.history || [],
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
    q: opts.q || '',
    status: opts.status || 'active',
    origin: opts.origin || '',
    offset: opts.offset || 0,
    limit: opts.limit || 20,
  });
}

// ── 문서 생애주기 ──
// 모든 파괴적 행위에는 역이 있다 (SPEC-nexus-document-lifecycle).

export async function hideDocument(rid) {
  return request('POST', `/documents/${encodeURIComponent(rid)}/hide`);
}

export async function restoreDocument(rid) {
  return request('POST', `/documents/${encodeURIComponent(rid)}/restore`);
}

/** supersession 취소 — 사유가 필수다. 되돌리면 최신본과 공존할 수 있다. */
export async function unsupersedeDocument(rid, reason) {
  return request('POST', `/documents/${encodeURIComponent(rid)}/unsupersede`, { reason });
}

// ── Diff ──

export async function getDiff(opts = {}) {
  return request('GET', '/diff', null, {
    tenant: opts.tenant || 'default',
    flag_filter: opts.flag_filter || null,
    entity_filter: opts.entity_filter || null,
  });
}

// OTel 집계는 운영자 도구(nexus otel-aggregate CLI / POST /otel/aggregate)다. 여기 있던
// otelAggregate() 클라이언트는 어느 뷰도 부르지 않는 죽은 코드였다 — 웹은 OTel 집계를
// 트리거하는 표면이 아니다. 엔드포인트는 그대로 있고, 필요해지면 그때 되살린다.

// ── 상태 ──

export async function getStatus() {
  return request('GET', '/status');
}

// ── 업로드 ──

export async function uploadFile(file, path = 'uploads', tenant = 'default') {
  const formData = new FormData();
  formData.append('file', file);

  const url = `${BASE}/upload?path=${encodeURIComponent(path)}&tenant=${encodeURIComponent(tenant)}`;
  const res = await fetch(url, { method: 'POST', body: formData, headers: { ...(await authHeaders()) } });
  const json = await res.json();

  if (res.status === 409) {
    throw new ApiError(json.detail || '파일이 이미 존재합니다', 409);
  }
  if (!json.success) {
    throw new ApiError(json.error || json.detail || `HTTP ${res.status}`, res.status);
  }
  return { data: json.data, meta: json.meta || {} };
}

// ── 소스 (Notion) ──
// 엔드포인트가 정본이다. 이 함수들은 그 위의 얇은 래퍼일 뿐이다.
// (SPEC-nexus-notion-source-console §4.6)

export async function listSources() {
  return request('GET', '/sources/notion/roots');
}

/** Notion 에게 직접 묻는다: 토큰이 유효한가, 각 root 에 닿는가. 느릴 수 있다(외부 API). */
export async function sourcesHealth() {
  return request('GET', '/sources/notion/health');
}

export async function addSource(urlOrId, label = '') {
  return request('POST', '/sources/notion/roots', { url_or_id: urlOrId, label });
}

export async function removeSource(rootId) {
  return request('DELETE', `/sources/notion/roots/${encodeURIComponent(rootId)}`);
}

/** 동기화 시작. 즉시 run_id 를 돌려준다 — 진행은 getSyncRun 으로 폴링. */
export async function startSync({ reconcile = false, dryRun = false, confirmPlan = null } = {}) {
  const body = confirmPlan ? { confirm_plan: confirmPlan } : { reconcile, dry_run: dryRun };
  return request('POST', '/sources/notion/sync', body);
}

export async function getSyncRun(runId) {
  return request('GET', `/sources/notion/sync/${encodeURIComponent(runId)}`);
}

export async function getLatestSync() {
  return request('GET', '/sources/notion/sync/latest');
}
