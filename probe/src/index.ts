/**
 * Probe — 프로덕트 개발 워크플로 자동 검증 도구
 *
 * 플랫폼 인식 PR 범위 분석을 핵심으로,
 * API 계약 검증, 리뷰 체크리스트, Nexus 연동 기반 맥락 리뷰를 제공한다.
 */

export { analyzeScope, type ScopeAnalysisResult, type DetectedGroup, type AnalyzedFile, type MixedConcernWarning, type SplitSuggestion, type ProposedPr } from './core/scope-analyzer.js';
export { detectPlatform, getProfileForPlatform, type DetectedPlatform } from './profiles/detector.js';
export { loadConfig, loadConfigAsync, applyConfigOverrides, resolveNexusConfig, type ProbeConfig, type ApiConfig, type ReviewConfig, type NexusConfig } from './core/config-loader.js';
export type { PlatformProfile, CohesionGroup, PrThresholds, FileRolePattern, MixedConcernRule, SeverityLevel } from './profiles/types.js';
export { springBootProfile } from './profiles/spring-boot.js';
export { nextjsProfile } from './profiles/nextjs.js';
export { reactSpaProfile } from './profiles/react-spa.js';

// v0.2 — API 분석
export { lintApiSpec, type ApiLintOptions } from './core/api-linter.js';
export { diffApiSpecs, type ApiDiffOptions } from './core/api-analyzer.js';
export { lintSpec } from './api/spec-linter.js';
export { diffSpecs } from './api/spec-differ.js';
export type { ApiLintResult, ApiLintViolation, ApiDiffResult, ApiChange, OpenApiSpec, LintRule } from './api/types.js';

// v0.2 — 리뷰 체크리스트
export { generateReviewChecklist, type ReviewOptions } from './core/review-checklist.js';
export { detectPrType } from './review/pr-type-detector.js';
export { generateChecklist } from './review/checklist-generator.js';
export type { PrType, ReviewChecklist, ChecklistItem, VerifiedItem } from './review/types.js';

// v0.4 — 관심사 드리프트 감지
export { detectConcernDrift, type DriftResult } from './core/concern-drift.js';

// v0.4 — Nexus 연동
export { NexusClient, withNexusFallback } from './nexus/client.js';
export { enrichWithNexus, extractServiceNames } from './nexus/context-enricher.js';
export { analyzeImpact } from './nexus/impact-analyzer.js';
export type { NexusClientConfig, EnrichmentResult, RelevantDoc, ImpactedService, DesignGap, ImpactAnalysis, NexusSearchResult, NexusGraphResult, NexusDiffResult } from './nexus/types.js';
