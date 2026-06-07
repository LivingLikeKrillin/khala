/**
 * 칼라(Khala) 연동 타입 정의
 *
 * Probe가 칼라 API를 호출할 때 사용하는 요청/응답 타입.
 * 칼라 API 계약(API_CONTRACT.md)에 기반한다.
 *
 * 규정 문서: docs/probe-v0.4-scope.md § 3
 */

// ─── 공통 ───

/** 칼라 API 공통 응답 래퍼 */
export interface KhalaResponse<T> {
  success: boolean;
  data: T;
  error: string | null;
  meta: Record<string, unknown>;
}

// ─── 검색 ───

/** 검색 요청 */
export interface KhalaSearchRequest {
  query: string;
  top_k?: number;
  route?: string;
  classification_max?: string;
  include_graph?: boolean;
  include_evidence?: boolean;
}

/** 검색 결과 */
export interface KhalaSearchResult {
  results: KhalaSearchHit[];
  graph_findings: KhalaGraphFindings | null;
  route_used: string;
  timing_ms: Record<string, number>;
}

/** 검색 히트 */
export interface KhalaSearchHit {
  rid: string;
  doc_rid: string;
  doc_title: string;
  section_path: string;
  source_uri: string;
  snippet: string;
  score: number;
  bm25_rank: number | null;
  vector_rank: number | null;
  classification: string;
}

/** 그래프 검색 결과 */
export interface KhalaGraphFindings {
  designed_edges: KhalaDesignedEdge[];
  observed_edges: KhalaObservedEdge[];
  diff_flags: KhalaDiffFlag[];
}

// ─── 답변 ───

/** 답변 요청 */
export interface KhalaAnswerRequest {
  query: string;
  top_k?: number;
  route?: string;
  classification_max?: string;
}

/** 답변 결과 */
export interface KhalaAnswerResult {
  answer: string;
  evidence_snippets: unknown[];
  graph_findings: unknown;
  provenance: unknown;
  route_used: string;
  timing_ms: Record<string, number>;
}

// ─── 그래프 ───

/** 그래프 조회 결과 */
export interface KhalaGraphResult {
  center_entity: KhalaEntity;
  edges: KhalaEdgeWithEvidence[];
  observed_edges: KhalaObservedEdgeDetail[];
}

/** 엔티티 */
export interface KhalaEntity {
  rid: string;
  name: string;
  type?: string;
  aliases?: string[];
  description?: string;
}

/** 설계 엣지 */
export interface KhalaDesignedEdge {
  rid: string;
  edge_type: string;
  from_name: string;
  to_name: string;
  confidence: number;
}

/** 설계 엣지 + 근거 */
export interface KhalaEdgeWithEvidence extends KhalaDesignedEdge {
  from_rid: string;
  to_rid: string;
  hop: number;
  evidence: KhalaEvidenceSnippet[];
}

/** 근거 스니펫 */
export interface KhalaEvidenceSnippet {
  doc_title: string;
  section_path: string;
  text: string;
  note: string;
}

/** 관측 엣지 (요약) */
export interface KhalaObservedEdge {
  rid: string;
  edge_type: string;
  from_name: string;
  to_name: string;
  call_count: number;
  error_rate: number;
  latency_p95: number;
}

/** 관측 엣지 (상세) */
export interface KhalaObservedEdgeDetail extends KhalaObservedEdge {
  sample_trace_ids: string[];
  trace_query_ref: string;
}

// ─── Diff ───

/** diff 보고서 */
export interface KhalaDiffResult {
  total_designed_edges: number;
  total_observed_edges: number;
  diffs: KhalaDiffItem[];
  generated_at: string;
}

/** diff 항목 */
export interface KhalaDiffItem {
  flag: 'doc_only' | 'observed_only' | 'conflict';
  edge_rid: string | null;
  observed_edge_rid: string | null;
  from_name: string;
  to_name: string;
  edge_type: string;
  detail: string;
  designed_evidence: KhalaEvidenceSnippet[];
  observed_evidence: {
    sample_trace_ids: string[];
    trace_query_ref: string;
  } | null;
}

/** diff 플래그 (그래프 검색 결과 내) */
export interface KhalaDiffFlag {
  flag: string;
  from_name: string;
  to_name: string;
  edge_type: string;
}

// ─── 클라이언트 설정 ───

/** 칼라 클라이언트 설정 */
export interface KhalaClientConfig {
  /** 칼라 API 서버 URL (기본: http://localhost:8000) */
  baseUrl: string;
  /** 요청 타임아웃 ms (기본: 3000) */
  timeoutMs: number;
  /** 테넌트 (기본: "default") */
  tenant: string;
  /** 최대 분류 등급 (기본: "INTERNAL") */
  classificationMax: string;
}

// ─── 보강 결과 ───

/** 컨텍스트 보강 결과 */
export interface EnrichmentResult {
  /** 관련 규정/문서 스니펫 */
  relevantDocs: RelevantDoc[];
  /** 영향받는 서비스 (graph neighbor) */
  impactedServices: ImpactedService[];
  /** 설계-관측 불일치 */
  designObservationGaps: DesignGap[];
  /** 칼라 가용 여부 */
  khalaAvailable: boolean;
}

/** 관련 문서 */
export interface RelevantDoc {
  docTitle: string;
  sectionPath: string;
  snippet: string;
  score: number;
  classification: string;
}

/** 영향받는 서비스 */
export interface ImpactedService {
  name: string;
  rid: string;
  relationship: 'calls' | 'called_by' | 'publishes_to' | 'subscribes_from';
  confidence: number;
  /** 관측 데이터 (있으면) */
  observed?: {
    callCount: number;
    errorRate: number;
    latencyP95: number;
    /** 관측 엣지의 실제 호출 방향 (운영신호 fromName/toName 정확도용) */
    fromName?: string;
    toName?: string;
  };
}

/** 설계-관측 갭 */
export interface DesignGap {
  flag: 'doc_only' | 'observed_only' | 'conflict';
  fromName: string;
  toName: string;
  edgeType: string;
  detail: string;
  /** 설계 근거 (문서 스니펫) */
  designedEvidence?: string;
  /** 관측 근거 (트레이스 ID) */
  observedEvidence?: string[];
}

// ─── 영향 분석 ───

/** 영향 분석 결과 */
export interface ImpactAnalysis {
  /** 변경된 서비스 */
  changedServices: string[];
  /** 직접 영향 (1홉) */
  directImpact: ImpactedService[];
  /** 간접 영향 (2홉) */
  indirectImpact: ImpactedService[];
  /** 영향 요약 */
  summary: string;
  /** 심각도 */
  severity: 'none' | 'low' | 'medium' | 'high';
}

// ─── 트러블슈팅 그라운딩 (v0.5) ───

/**
 * /status 응답 (가용성·티어 진단용).
 * 필드는 khala api.py status() (812~852행)가 반환하는 카운트와 일치:
 * documents_count/edges_count/observed_edges_count/diff_summary는 db_connected일 때만 채워짐.
 */
export interface KhalaStatusResult {
  db_connected: boolean;
  ollama_connected?: boolean;
  tempo_connected?: boolean;
  documents_count?: number;
  chunks_count?: number;
  entities_count?: number;
  edges_count?: number;
  observed_edges_count?: number;
  diff_summary?: {
    doc_only_count: number;
    observed_only_count: number;
    conflict_count: number;
  };
}

/** 트러블슈팅 입력 */
export interface TroubleshootInput {
  signal: string;
  kind?: 'stacktrace' | 'error' | 'test-failure' | 'incident';
  diffBase?: string;
  suspectServices?: string[];
}

/** 국소화 산출물 — §1 / localizer→grounder 계약 */
export interface Suspect {
  entityName: string;
  evidence: { kind: 'frame' | 'path' | 'user' | 'keyword'; raw: string }[];
  confidence: number;
}

/** Archon claim의 읽기 전용 투영 (Archon 연동 시에만) */
export interface ClaimRef {
  id: string;
  kind: 'goal' | 'invariant' | 'requirement';
  statement: string;
  status: string;
  criticality: 'core' | 'peripheral';
  confidence: 'high' | 'medium' | 'low';
  codeDrift: boolean;
  owner: string;
  boundSymbol: string;
}

/** 운영 신호 이상치 (§4) */
export interface OperationalSignal {
  fromName: string;
  toName: string;
  callCount: number;
  errorRate: number;
  latencyP95: number;
  anomaly: string;
}

/** 최근 변경 상관 (§6) */
export interface ChangeLink {
  service: string;
  changedFiles: string[];
  relationship: string;
}

/** 트러블슈팅 그라운딩 결과 */
export interface GroundingPack {
  tier: 0 | 1 | 2 | 3;
  tierReason: string;
  suspects: Suspect[];
  knowledge?: RelevantDoc[];
  topology?: ImpactAnalysis;
  designObservationGaps?: DesignGap[];
  operationalSignals?: OperationalSignal[];
  changeCorrelation?: ChangeLink[];
  domainInvariants?: ClaimRef[];
  caveats: string[];
}

// ─── 리뷰 그라운딩 (v0.6) ───

/** 변경 엔티티 — diff→service/entity 라우팅 산출 (v0.6) */
export interface ChangedEntity {
  /** grounder가 /graph·/diff에 넘길 정규화 service/entity명 */
  entityName: string;
  /** fileBelongsToService로 이 엔티티에 귀속된 변경 파일 */
  changedFiles: string[];
  /** scope-analyzer 응집 그룹명 (추적용, 선택) */
  cohesionGroup?: string;
}

/** specledger가 Khala에 발행한 승인 스펙의 읽기전용 투영 (v0.6) */
export interface SpecRef {
  docTitle: string;
  sectionPath: string;
  /** specledger content-hash 스탬프 (있으면) */
  approvedHash?: string;
  snippet: string;
  classification: string;
}

/** 리뷰 그라운딩 결과 — 증거만, 정합 판정은 Claude가 한다 (v0.6) */
export interface ReviewGroundingPack {
  tier: 0 | 1 | 2 | 3;
  tierReason: string;
  changedEntities: ChangedEntity[];
  applicableGuidelines?: RelevantDoc[];
  specRefs?: SpecRef[];
  topology?: ImpactAnalysis;
  designObservationGaps?: DesignGap[];
  claimDrift?: ClaimRef[];
  caveats: string[];
}
