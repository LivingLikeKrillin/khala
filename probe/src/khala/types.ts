/**
 * 칼라(Khala) 연동 타입 정의
 *
 * Karax가 칼라 API를 호출할 때 사용하는 요청/응답 타입.
 * 칼라 API 계약(API_CONTRACT.md)에 기반한다.
 *
 * 규정 문서: docs/karax-v0.4-scope.md § 3
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
