-- ============================================================
-- Nexus DB Schema (PostgreSQL 16 + pgvector + pg_trgm)
-- Canonical Resource Model (CRM) 기반
-- nexus-mvp-design.md 4장과 동기화
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TYPE classification_level AS ENUM ('PUBLIC', 'INTERNAL', 'RESTRICTED');
CREATE TYPE resource_status AS ENUM ('active', 'superseded', 'soft_deleted');
CREATE TYPE source_kind AS ENUM ('git', 'wiki', 'file', 'otel', 'manual');

-- ============================================================
-- 1. documents
-- ============================================================
CREATE TABLE documents (
    -- CRM 공통
    rid             TEXT PRIMARY KEY,
    rtype           TEXT NOT NULL DEFAULT 'document',
    tenant          TEXT NOT NULL DEFAULT 'default',
    classification  classification_level NOT NULL DEFAULT 'INTERNAL',
    owner           TEXT NOT NULL DEFAULT 'unknown',
    source_uri      TEXT NOT NULL,
    source_version  TEXT NOT NULL DEFAULT '',
    source_kind     source_kind NOT NULL DEFAULT 'git',
    hash            TEXT NOT NULL,
    labels          TEXT[] DEFAULT '{}',
    is_quarantined  BOOLEAN NOT NULL DEFAULT false,
    quality_flags   TEXT[] DEFAULT '{}',
    status          resource_status NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    prov_pipeline   TEXT NOT NULL DEFAULT 'indexer-v1',
    prov_inputs     TEXT[] DEFAULT '{}',
    prov_transform  TEXT NOT NULL DEFAULT '',
    -- 문서 고유
    title           TEXT NOT NULL DEFAULT '',
    doc_type        TEXT NOT NULL DEFAULT 'markdown',
    language        TEXT NOT NULL DEFAULT 'ko',
    content_hash    TEXT NOT NULL DEFAULT '',
    -- accountable-review stamp from an upstream governance tool (Arbiter content_hash);
    -- distinct from content_hash (nexus's own change-detection hash). '' for non-governed docs.
    approved_hash   TEXT NOT NULL DEFAULT '',
    CONSTRAINT chk_doc_rtype CHECK (rtype = 'document')
);

CREATE INDEX idx_doc_tenant_class ON documents (tenant, classification)
    WHERE status = 'active' AND is_quarantined = false;
CREATE INDEX idx_doc_hash ON documents (content_hash);
CREATE INDEX idx_doc_type ON documents (doc_type);

-- ============================================================
-- 2. chunks
-- ============================================================
-- search_text: 검색/임베딩에 사용되는 가공된 텍스트
-- chunk_text와 분리하여 2.0 Contextual Enrichment 대비
CREATE TABLE chunks (
    -- CRM 공통
    rid             TEXT PRIMARY KEY,
    rtype           TEXT NOT NULL DEFAULT 'chunk',
    tenant          TEXT NOT NULL DEFAULT 'default',
    classification  classification_level NOT NULL DEFAULT 'INTERNAL',
    owner           TEXT NOT NULL DEFAULT 'unknown',
    source_uri      TEXT NOT NULL,
    source_version  TEXT NOT NULL DEFAULT '',
    source_kind     source_kind NOT NULL DEFAULT 'git',
    hash            TEXT NOT NULL DEFAULT '',
    labels          TEXT[] DEFAULT '{}',
    is_quarantined  BOOLEAN NOT NULL DEFAULT false,
    quality_flags   TEXT[] DEFAULT '{}',
    status          resource_status NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    prov_pipeline   TEXT NOT NULL DEFAULT 'indexer-v1',
    prov_inputs     TEXT[] DEFAULT '{}',
    prov_transform  TEXT NOT NULL DEFAULT '',
    -- 청크 고유
    doc_rid         TEXT NOT NULL REFERENCES documents(rid) ON DELETE CASCADE,
    section_path    TEXT NOT NULL DEFAULT '',
    chunk_text      TEXT NOT NULL,
    context_prefix  TEXT DEFAULT NULL,
    -- search_text: get_search_text()의 DB 레벨 대응
    -- 1.0: "[section_path] chunk_text"
    -- 2.0: context_prefix에 LLM enrichment 결과를 넣으면 자동 반영
    search_text     TEXT GENERATED ALWAYS AS (
        COALESCE(context_prefix, '[' || section_path || ']') || ' ' || chunk_text
    ) STORED,
    embedding       vector(768),
    tsvector_ko     tsvector,
    chunk_index     INT NOT NULL DEFAULT 0,
    -- 역사적 컬럼. 아무도 쓰지 않고 아무도 읽지 않는다 (027). 행당 한 칸이라 벡터 컬럼
    -- 둘을 설명하지 못했다 — 컬럼별 출처의 정본은 chunk_vector_provenance (025).
    embed_model     TEXT,
    metadata        JSONB DEFAULT '{}',
    CONSTRAINT chk_chunk_rtype CHECK (rtype = 'chunk')
);

-- BM25: search_text 기반 tsvector에 GIN
CREATE INDEX idx_chunk_bm25 ON chunks USING gin (tsvector_ko)
    WHERE status = 'active' AND is_quarantined = false;

-- Vector: embedding에 IVFFlat (데이터 많아지면 HNSW로 전환)
CREATE INDEX idx_chunk_vector ON chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100)
    WHERE status = 'active' AND is_quarantined = false AND embedding IS NOT NULL;

-- pg_trgm: search_text 기반 3-gram fallback
CREATE INDEX idx_chunk_trgm ON chunks USING gin (search_text gin_trgm_ops)
    WHERE status = 'active' AND is_quarantined = false;

CREATE INDEX idx_chunk_doc ON chunks (doc_rid);
CREATE INDEX idx_chunk_tenant_class ON chunks (tenant, classification)
    WHERE status = 'active' AND is_quarantined = false;

-- ============================================================
-- 3. entities
-- ============================================================
CREATE TABLE entities (
    -- CRM 공통
    rid             TEXT PRIMARY KEY,
    rtype           TEXT NOT NULL DEFAULT 'entity',
    tenant          TEXT NOT NULL DEFAULT 'default',
    classification  classification_level NOT NULL DEFAULT 'INTERNAL',
    owner           TEXT NOT NULL DEFAULT 'unknown',
    source_uri      TEXT NOT NULL DEFAULT '',
    source_version  TEXT NOT NULL DEFAULT '',
    source_kind     source_kind NOT NULL DEFAULT 'manual',
    hash            TEXT NOT NULL DEFAULT '',
    labels          TEXT[] DEFAULT '{}',
    is_quarantined  BOOLEAN NOT NULL DEFAULT false,
    quality_flags   TEXT[] DEFAULT '{}',
    status          resource_status NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    prov_pipeline   TEXT NOT NULL DEFAULT 'manual',
    prov_inputs     TEXT[] DEFAULT '{}',
    prov_transform  TEXT NOT NULL DEFAULT '',
    -- Entity 고유
    entity_type     TEXT NOT NULL,
    name            TEXT NOT NULL,
    aliases         TEXT[] DEFAULT '{}',
    description     TEXT DEFAULT '',
    CONSTRAINT chk_ent_rtype CHECK (rtype = 'entity'),
    CONSTRAINT uq_ent_name UNIQUE (tenant, entity_type, name)
);

CREATE INDEX idx_ent_name ON entities (name);
CREATE INDEX idx_ent_aliases ON entities USING gin (aliases);
CREATE INDEX idx_ent_type ON entities (entity_type);

-- ============================================================
-- 4. edges (설계 기반)
-- ============================================================
CREATE TABLE edges (
    -- CRM 공통
    rid             TEXT PRIMARY KEY,
    rtype           TEXT NOT NULL DEFAULT 'edge',
    tenant          TEXT NOT NULL DEFAULT 'default',
    classification  classification_level NOT NULL DEFAULT 'INTERNAL',
    owner           TEXT NOT NULL DEFAULT 'unknown',
    source_uri      TEXT NOT NULL DEFAULT '',
    source_version  TEXT NOT NULL DEFAULT '',
    source_kind     source_kind NOT NULL DEFAULT 'git',
    hash            TEXT NOT NULL DEFAULT '',
    labels          TEXT[] DEFAULT '{}',
    is_quarantined  BOOLEAN NOT NULL DEFAULT false,
    quality_flags   TEXT[] DEFAULT '{}',
    status          resource_status NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    prov_pipeline   TEXT NOT NULL DEFAULT 'indexer-v1',
    prov_inputs     TEXT[] DEFAULT '{}',
    prov_transform  TEXT NOT NULL DEFAULT '',
    -- Edge 고유
    edge_type       TEXT NOT NULL,
    from_rid        TEXT NOT NULL REFERENCES entities(rid),
    to_rid          TEXT NOT NULL REFERENCES entities(rid),
    confidence      FLOAT NOT NULL DEFAULT 0.5,
    source_category TEXT NOT NULL DEFAULT 'DESIGNED',
    CONSTRAINT chk_edge_rtype CHECK (rtype = 'edge'),
    CONSTRAINT chk_edge_type CHECK (edge_type IN ('CALLS', 'PUBLISHES', 'SUBSCRIBES')),
    CONSTRAINT chk_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

CREATE INDEX idx_edge_from ON edges (from_rid) WHERE status = 'active';
CREATE INDEX idx_edge_to ON edges (to_rid) WHERE status = 'active';
CREATE INDEX idx_edge_type ON edges (edge_type);
CREATE INDEX idx_edge_quality ON edges USING gin (quality_flags) WHERE status = 'active';

-- ============================================================
-- 5. observed_edges (OTel 관측 기반)
-- ============================================================
CREATE TABLE observed_edges (
    -- CRM 공통
    rid             TEXT PRIMARY KEY,
    rtype           TEXT NOT NULL DEFAULT 'observed_edge',
    tenant          TEXT NOT NULL DEFAULT 'default',
    classification  classification_level NOT NULL DEFAULT 'INTERNAL',
    owner           TEXT NOT NULL DEFAULT 'unknown',
    source_uri      TEXT NOT NULL DEFAULT 'otlp://tempo',
    source_version  TEXT NOT NULL DEFAULT '',
    source_kind     source_kind NOT NULL DEFAULT 'otel',
    hash            TEXT NOT NULL DEFAULT '',
    labels          TEXT[] DEFAULT '{}',
    is_quarantined  BOOLEAN NOT NULL DEFAULT false,
    quality_flags   TEXT[] DEFAULT '{}',
    status          resource_status NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    prov_pipeline   TEXT NOT NULL DEFAULT 'otel-agg-v1',
    prov_inputs     TEXT[] DEFAULT '{}',
    prov_transform  TEXT NOT NULL DEFAULT '',
    -- Observed Edge 고유
    edge_type       TEXT NOT NULL DEFAULT 'CALLS_OBSERVED',
    from_rid        TEXT NOT NULL REFERENCES entities(rid),
    to_rid          TEXT NOT NULL REFERENCES entities(rid),
    call_count      INT NOT NULL DEFAULT 0,
    error_rate      FLOAT NOT NULL DEFAULT 0.0,
    latency_p50     FLOAT,
    latency_p95     FLOAT,
    latency_p99     FLOAT,
    protocol        TEXT DEFAULT '',
    interaction_style TEXT DEFAULT '',
    sample_trace_ids TEXT[] DEFAULT '{}',
    trace_query_ref  TEXT DEFAULT '',
    resolved_via     TEXT DEFAULT '',
    window_start    TIMESTAMPTZ,
    window_end      TIMESTAMPTZ,
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_obs_rtype CHECK (rtype = 'observed_edge')
);

CREATE INDEX idx_obs_from ON observed_edges (from_rid) WHERE status = 'active';
CREATE INDEX idx_obs_to ON observed_edges (to_rid) WHERE status = 'active';
CREATE INDEX idx_obs_quality ON observed_edges USING gin (quality_flags) WHERE status = 'active';
CREATE INDEX idx_obs_last_seen ON observed_edges (last_seen_at);

-- ============================================================
-- 6. evidence
-- ============================================================
CREATE TABLE evidence (
    -- CRM 공통
    rid             TEXT PRIMARY KEY,
    rtype           TEXT NOT NULL DEFAULT 'evidence',
    tenant          TEXT NOT NULL DEFAULT 'default',
    classification  classification_level NOT NULL DEFAULT 'INTERNAL',
    owner           TEXT NOT NULL DEFAULT 'unknown',
    source_uri      TEXT NOT NULL DEFAULT '',
    source_version  TEXT NOT NULL DEFAULT '',
    source_kind     source_kind NOT NULL DEFAULT 'git',
    hash            TEXT NOT NULL DEFAULT '',
    labels          TEXT[] DEFAULT '{}',
    is_quarantined  BOOLEAN NOT NULL DEFAULT false,
    quality_flags   TEXT[] DEFAULT '{}',
    status          resource_status NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    prov_pipeline   TEXT NOT NULL DEFAULT 'indexer-v1',
    prov_inputs     TEXT[] DEFAULT '{}',
    prov_transform  TEXT NOT NULL DEFAULT '',
    -- Evidence 고유
    subject_rid     TEXT NOT NULL,
    evidence_rid    TEXT NOT NULL,
    kind            TEXT NOT NULL DEFAULT 'text_snippet',
    weight          FLOAT NOT NULL DEFAULT 0.15,
    note            TEXT DEFAULT '',
    CONSTRAINT chk_evi_rtype CHECK (rtype = 'evidence'),
    CONSTRAINT chk_weight CHECK (weight >= 0.0 AND weight <= 1.0)
);

CREATE INDEX idx_evi_subject ON evidence (subject_rid) WHERE status = 'active';
CREATE INDEX idx_evi_evidence ON evidence (evidence_rid) WHERE status = 'active';

-- ============================================================
-- View: v_edge_diff (설계 vs 관측 불일치)
-- ============================================================
CREATE OR REPLACE VIEW v_edge_diff AS
WITH designed AS (
    SELECT e.rid as edge_rid, e.edge_type, e.from_rid, e.to_rid,
           ef.name as from_name, et.name as to_name, e.confidence
    FROM edges e
    JOIN entities ef ON e.from_rid = ef.rid
    JOIN entities et ON e.to_rid = et.rid
    WHERE e.status = 'active'
),
observed AS (
    SELECT o.rid as obs_rid, o.edge_type, o.from_rid, o.to_rid,
           of2.name as from_name, ot.name as to_name,
           o.call_count, o.error_rate, o.latency_p95,
           o.protocol, o.interaction_style, o.last_seen_at
    FROM observed_edges o
    JOIN entities of2 ON o.from_rid = of2.rid
    JOIN entities ot ON o.to_rid = ot.rid
    WHERE o.status = 'active'
)
SELECT 'doc_only' as diff_type, d.edge_rid, null as obs_rid,
       d.from_name, d.to_name, d.edge_type,
       d.confidence, null::int as call_count, null::float as latency_p95
FROM designed d LEFT JOIN observed o ON d.from_rid = o.from_rid AND d.to_rid = o.to_rid
WHERE o.obs_rid IS NULL
UNION ALL
SELECT 'observed_only', null, o.obs_rid,
       o.from_name, o.to_name, o.edge_type,
       null::float, o.call_count, o.latency_p95
FROM observed o LEFT JOIN designed d ON o.from_rid = d.from_rid AND o.to_rid = d.to_rid
WHERE d.edge_rid IS NULL
UNION ALL
SELECT 'conflict', d.edge_rid, o.obs_rid,
       d.from_name, d.to_name, d.edge_type,
       d.confidence, o.call_count, o.latency_p95
FROM designed d JOIN observed o ON d.from_rid = o.from_rid AND d.to_rid = o.to_rid
WHERE false;  -- MVP: conflict 로직은 앱 레벨. 향후 이 뷰 확장.

-- ============================================================
-- Function: f_graph_neighbors (GraphRepository에서 사용)
-- ============================================================
-- base_filter 를 그래프 채널에도 강제한다(SPEC-nexus-graph-scope-filter): 양 끝 엔티티가
-- 호출자의 tenant·clearance·비격리·active 를 만족할 때만 엣지를 돌려준다. 필터를 재귀 멤버
-- '안'에 두므로 스코프 밖 노드를 '통과'하는 순회도 막힌다(경계에서 멈춤 — 의도된 보안 동작).
DROP FUNCTION IF EXISTS f_graph_neighbors(TEXT, INT);
CREATE OR REPLACE FUNCTION f_graph_neighbors(
    p_entity_rid TEXT, p_max_hops INT, p_tenant TEXT, p_clearance classification_level
) RETURNS TABLE (
    hop INT, edge_rid TEXT, edge_type TEXT,
    from_rid TEXT, from_name TEXT, to_rid TEXT, to_name TEXT,
    confidence FLOAT, source_category TEXT
) AS $$
WITH RECURSIVE neighbors AS (
    SELECT 1 as hop, e.rid as edge_rid, e.edge_type, e.from_rid, ef.name as from_name,
           e.to_rid, et.name as to_name, e.confidence, e.source_category
    FROM edges e
    JOIN entities ef ON e.from_rid = ef.rid JOIN entities et ON e.to_rid = et.rid
    WHERE e.status = 'active' AND (e.from_rid = p_entity_rid OR e.to_rid = p_entity_rid)
      AND ef.tenant = p_tenant AND ef.classification <= p_clearance
      AND ef.is_quarantined = false AND ef.status = 'active'
      AND et.tenant = p_tenant AND et.classification <= p_clearance
      AND et.is_quarantined = false AND et.status = 'active'
    UNION ALL
    SELECT n.hop + 1, e.rid as edge_rid, e.edge_type, e.from_rid, ef.name,
           e.to_rid, et.name, e.confidence, e.source_category
    FROM edges e
    JOIN entities ef ON e.from_rid = ef.rid JOIN entities et ON e.to_rid = et.rid
    JOIN neighbors n ON (e.from_rid = n.to_rid OR e.to_rid = n.from_rid)
    WHERE e.status = 'active' AND n.hop < p_max_hops AND e.rid != n.edge_rid
      AND ef.tenant = p_tenant AND ef.classification <= p_clearance
      AND ef.is_quarantined = false AND ef.status = 'active'
      AND et.tenant = p_tenant AND et.classification <= p_clearance
      AND et.is_quarantined = false AND et.status = 'active'
)
SELECT * FROM neighbors;
$$ LANGUAGE sql STABLE;

-- ============================================================
-- 7. claims (Archon — 도메인 불변식·값 거버넌스)
-- ============================================================
-- source_kind enum에 'code' 추가 (psql 자동커밋 → 다음 CREATE에서 DEFAULT 사용 가능)
ALTER TYPE source_kind ADD VALUE IF NOT EXISTS 'code';

CREATE TABLE claims (
    -- CRM 공통 (documents와 동일 타입/기본값)
    rid             TEXT PRIMARY KEY,
    rtype           TEXT NOT NULL DEFAULT 'claim',
    tenant          TEXT NOT NULL DEFAULT 'default',
    classification  classification_level NOT NULL DEFAULT 'INTERNAL',
    owner           TEXT NOT NULL DEFAULT 'unknown',
    source_uri      TEXT NOT NULL DEFAULT '',
    source_version  TEXT NOT NULL DEFAULT '',
    source_kind     source_kind NOT NULL DEFAULT 'code',
    hash            TEXT NOT NULL DEFAULT '',
    labels          TEXT[] DEFAULT '{}',
    is_quarantined  BOOLEAN NOT NULL DEFAULT false,
    quality_flags   TEXT[] DEFAULT '{}',
    status          resource_status NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    prov_pipeline   TEXT NOT NULL DEFAULT 'claim-v1',
    prov_inputs     TEXT[] DEFAULT '{}',
    prov_transform  TEXT NOT NULL DEFAULT '',
    -- claim 고유
    claim_id        TEXT NOT NULL,
    kind            TEXT NOT NULL,                      -- goal|invariant|requirement
    concepts        TEXT[] DEFAULT '{}',
    statement       TEXT NOT NULL,
    value_source    TEXT,
    value_ref_kind  TEXT,
    criticality     TEXT NOT NULL DEFAULT 'peripheral',
    activity        TEXT NOT NULL DEFAULT 'active',
    claim_status    TEXT NOT NULL DEFAULT 'unverified', -- 검증상태 (CRM status와 분리)
    confidence      TEXT NOT NULL DEFAULT 'low',
    value_symbol_hash    TEXT,
    last_verified_commit TEXT,
    last_verified_at     TIMESTAMPTZ,
    CONSTRAINT chk_claim_rtype CHECK (rtype = 'claim'),
    CONSTRAINT uq_claim UNIQUE (tenant, claim_id)
);
CREATE INDEX idx_claims_concepts ON claims USING gin (concepts) WHERE status = 'active';
CREATE INDEX idx_claims_quality ON claims USING gin (quality_flags) WHERE status = 'active';
CREATE INDEX idx_claims_tenant_class ON claims (tenant, classification)
    WHERE status = 'active' AND is_quarantined = false;

-- ============================================================
-- a2a_audit — durable A2A audit trail (Phase 3, SPEC §5.6/§19)
-- ============================================================
-- One row per A2A task (granted AND denied). The raw query is NEVER stored, and since
-- 2026-08-14 neither is any fingerprint of it: `query_sha256` was recomputable from the
-- plaintext in `search_query_text`, which walked to `principal` (SPEC-nexus-audit-query-hash).
-- The column stays for historical rows; new rows leave it NULL.
-- Best-effort durable mirror of the always-on structlog `a2a.audit` event.
CREATE TABLE a2a_audit (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    skill           TEXT NOT NULL,
    principal       TEXT,
    tenant          TEXT,
    clearance       TEXT,
    query_sha256    TEXT,               -- 역사적 컬럼. 새 행은 NULL (migration 023)
    query_len       INTEGER NOT NULL DEFAULT 0,
    route           TEXT,
    evidence_count  INTEGER NOT NULL DEFAULT 0,
    task_state      TEXT,
    denied          BOOLEAN NOT NULL DEFAULT false,
    reason          TEXT,
    latency_ms      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_a2a_audit_ts ON a2a_audit (ts DESC);
CREATE INDEX idx_a2a_audit_principal ON a2a_audit (principal, ts DESC);
CREATE INDEX idx_a2a_audit_denied ON a2a_audit (denied, ts DESC);

-- ============================================================
-- search_log — search-quality signals (demand-pull gate signals)
-- ============================================================
-- One row per retrieval across all paths (search | search_answer | cli | a2a).
-- PII-safe: the raw query is NEVER stored — only sha256 + length (Nexus principle #3),
-- mirroring a2a_audit. Best-effort, fire-and-forget on server paths.
CREATE TABLE IF NOT EXISTS search_log (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    path            TEXT NOT NULL,
    tenant          TEXT,
    -- 이 조회가 실제로 읽은 테넌트들. `tenant` 는 귀속용 단일 값이라 교차 테넌트
    -- 조회를 구별하지 못한다 (migration 037).
    read_scope      TEXT,
    clearance       TEXT,
    route           TEXT,
    query_sha256    TEXT NOT NULL DEFAULT '',
    query_len       INTEGER NOT NULL DEFAULT 0,
    n_snippets      INTEGER NOT NULL DEFAULT 0,
    top_score       DOUBLE PRECISION,
    n_entities      INTEGER NOT NULL DEFAULT 0,
    graph_requested BOOLEAN NOT NULL DEFAULT false,
    n_graph_edges   INTEGER NOT NULL DEFAULT 0,
    no_answer       BOOLEAN NOT NULL DEFAULT false,
    llm_failed      BOOLEAN NOT NULL DEFAULT false,
    latency_ms      INTEGER NOT NULL DEFAULT 0,
    n_citations          INTEGER,   -- 인용 지표(nullable = 미측정, SPEC-nexus-search-signal-completeness)
    unverified_citations INTEGER,
    prompt_tokens        INTEGER,   -- LLM 토큰/비용(nullable = 미측정/미가격, SPEC-nexus-llm-usage-persistence)
    completion_tokens    INTEGER,
    cost_usd             DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_search_log_ts     ON search_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_search_log_tenant ON search_log (tenant, ts DESC);
CREATE INDEX IF NOT EXISTS idx_search_log_route  ON search_log (route, ts DESC);

CREATE OR REPLACE VIEW v_search_health AS
SELECT path, route,
       count(*)                                                        AS n,
       avg((no_answer)::int)::numeric(4,3)                             AS no_answer_rate,
       avg((graph_requested AND n_graph_edges = 0)::int)::numeric(4,3) AS graph_empty_rate,
       avg((llm_failed)::int)::numeric(4,3)                            AS llm_fail_rate,
       avg(n_snippets)::numeric(6,2)                                   AS avg_snippets,
       percentile_disc(0.95) WITHIN GROUP (ORDER BY latency_ms)        AS p95_latency_ms,
       (SUM(unverified_citations)::numeric
          / NULLIF(SUM(n_citations), 0))::numeric(4,3)                 AS citation_fabrication_rate,
       avg(cost_usd)::numeric(12,6)                                    AS avg_cost_priced_usd,
       sum(cost_usd)::numeric(14,6)                                    AS total_cost_usd
FROM search_log
WHERE ts > now() - interval '7 days'
GROUP BY path, route;
