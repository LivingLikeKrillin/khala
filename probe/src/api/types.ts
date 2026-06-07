/**
 * API 린트/분석 타입 정의
 *
 * v0.2 핵심 타입. API 스펙 린트 결과, diff 결과,
 * 린트 룰 인터페이스를 정의한다.
 *
 * 규정 문서: docs/probe-v0.2-scope.md § 3.1, 3.2
 */

// ─── API 린트 ───

/** API 린트 결과 */
export interface ApiLintResult {
  /** 스펙 파일 경로 */
  specPath: string;

  /** 린트 결과 요약 */
  summary: {
    errors: number;
    warnings: number;
    passed: number;
  };

  /** 위반 목록 */
  violations: ApiLintViolation[];
}

/** 린트 위반 항목 */
export interface ApiLintViolation {
  /** 규칙 ID */
  ruleId: string;

  /** 심각도 */
  severity: 'error' | 'warn';

  /** 위반 위치 (JSON path) */
  path: string;

  /** 메시지 (한국어 + 영어) */
  message: string;

  /** 수정 가이드 */
  fix?: string;
}

/** 린트 룰 인터페이스 */
export interface LintRule {
  /** 규칙 ID */
  id: string;

  /** 기본 심각도 */
  defaultSeverity: 'error' | 'warn';

  /** 규정 근거 */
  guidelineRef: string;

  /** 설명 */
  description: string;

  /**
   * 룰을 실행한다.
   * @param spec 파싱된 OpenAPI 스펙
   * @returns 위반 목록
   */
  check(spec: OpenApiSpec): ApiLintViolation[];
}

// ─── API diff ───

/** API diff 결과 */
export interface ApiDiffResult {
  /** 변경 요약 */
  summary: {
    added: number;
    modified: number;
    removed: number;
    deprecated: number;
    hasBreaking: boolean;
  };

  /** 엔드포인트별 변경 내역 */
  changes: ApiChange[];

  /** 권장 PR 라벨 */
  suggestedLabel: 'api:additive' | 'api:breaking' | 'api:deprecation' | null;
}

/** 엔드포인트 변경 */
export interface ApiChange {
  /** HTTP 메서드 + 경로 */
  endpoint: string;

  /** 변경 유형 */
  type: 'added' | 'modified' | 'removed' | 'deprecated';

  /** breaking 여부 */
  breaking: boolean;

  /** 변경 상세 */
  details: string[];
}

// ─── OpenAPI 스펙 (최소 타입) ───

/** 파싱된 OpenAPI 스펙의 최소 구조 */
export interface OpenApiSpec {
  openapi?: string;
  info?: {
    title?: string;
    version?: string;
  };
  paths?: Record<string, PathItem>;
  components?: {
    schemas?: Record<string, SchemaObject>;
  };
}

/** 경로 항목 */
export interface PathItem {
  get?: OperationObject;
  post?: OperationObject;
  put?: OperationObject;
  patch?: OperationObject;
  delete?: OperationObject;
  [key: string]: unknown;
}

/** 오퍼레이션 */
export interface OperationObject {
  operationId?: string;
  summary?: string;
  deprecated?: boolean;
  parameters?: ParameterObject[];
  requestBody?: RequestBodyObject;
  responses?: Record<string, ResponseObject>;
  [key: string]: unknown;
}

/** 파라미터 */
export interface ParameterObject {
  name?: string;
  in?: string;
  required?: boolean;
  schema?: SchemaObject;
  [key: string]: unknown;
}

/** 요청 본문 */
export interface RequestBodyObject {
  required?: boolean;
  content?: Record<string, MediaTypeObject>;
  [key: string]: unknown;
}

/** 응답 */
export interface ResponseObject {
  description?: string;
  content?: Record<string, MediaTypeObject>;
  [key: string]: unknown;
}

/** 미디어 타입 */
export interface MediaTypeObject {
  schema?: SchemaObject;
  [key: string]: unknown;
}

/** 스키마 */
export interface SchemaObject {
  type?: string;
  nullable?: boolean;
  required?: string[];
  properties?: Record<string, SchemaObject>;
  items?: SchemaObject;
  enum?: unknown[];
  format?: string;
  example?: unknown;
  deprecated?: boolean;
  $ref?: string;
  allOf?: SchemaObject[];
  oneOf?: SchemaObject[];
  anyOf?: SchemaObject[];
  [key: string]: unknown;
}

/** HTTP 메서드 */
export const HTTP_METHODS = ['get', 'post', 'put', 'patch', 'delete'] as const;
export type HttpMethod = typeof HTTP_METHODS[number];
