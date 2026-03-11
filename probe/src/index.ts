/**
 * Karax — 프로덕트 개발 워크플로 자동 검증 도구
 *
 * 칼라(Khala)의 기술자. 플랫폼 인식 PR 범위 분석을 핵심으로,
 * API 계약 검증, 테스트/리뷰 에이전트, 맥락 기반 리뷰를 제공한다.
 */

export { analyzeScope, type ScopeAnalysisResult, type DetectedGroup, type AnalyzedFile, type MixedConcernWarning, type SplitSuggestion, type ProposedPr } from './core/scope-analyzer.js';
export { detectPlatform, getProfileForPlatform, type DetectedPlatform } from './profiles/detector.js';
export { loadConfig, loadConfigAsync, applyConfigOverrides, type KaraxConfig } from './core/config-loader.js';
export type { PlatformProfile, CohesionGroup, PrThresholds, FileRolePattern, MixedConcernRule, SeverityLevel } from './profiles/types.js';
export { springBootProfile } from './profiles/spring-boot.js';
export { nextjsProfile } from './profiles/nextjs.js';
export { reactSpaProfile } from './profiles/react-spa.js';
