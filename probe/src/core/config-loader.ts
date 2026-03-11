/**
 * karax.config.ts 로더
 *
 * 프로젝트 루트의 karax.config.ts (또는 .js, .mjs, .json)를 읽어서 설정을 반환한다.
 * 설정 파일이 없으면 기본값을 사용한다.
 *
 * 규정 문서: docs/karax-v0.1-scope.md § 5
 */

import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import type { PlatformProfile, PrThresholds } from '../profiles/types.js';

export interface KaraxConfig {
  /** 플랫폼 프로파일 (자동 감지 또는 수동 지정) */
  platform?: 'spring-boot' | 'nextjs' | 'react-spa' | 'custom';

  /** 커스텀 프로파일 (platform: 'custom' 시) */
  customProfile?: PlatformProfile;

  /** 프로파일 임계치 오버라이드 */
  thresholds?: Partial<PrThresholds>;

  /** 무시할 파일 패턴 */
  ignore?: string[];

  /** 경고 레벨 설정 */
  severity?: {
    /** 범위 경고 최소 레벨 (이 레벨 이상만 표시) */
    minLevel?: 'info' | 'warn' | 'error';
  };
}

/**
 * 설정 파일 후보 (우선순위 순).
 * TypeScript/JS 파일은 동적 import, JSON은 직접 파싱.
 */
const CONFIG_CANDIDATES = [
  { name: 'karax.config.ts', type: 'module' as const },
  { name: 'karax.config.js', type: 'module' as const },
  { name: 'karax.config.mjs', type: 'module' as const },
  { name: 'karax.config.json', type: 'json' as const },
];

/**
 * JSON 설정 파일을 동기적으로 로드한다.
 */
function loadJsonConfig(configPath: string): KaraxConfig | undefined {
  try {
    const content = readFileSync(configPath, 'utf-8');
    return JSON.parse(content) as KaraxConfig;
  } catch {
    return undefined;
  }
}

/**
 * karax.config를 동기적으로 로드한다.
 *
 * TS/JS 모듈 설정 파일은 비동기 API인 `loadConfigAsync()`를 사용해야 한다.
 * 동기 버전은 JSON 파일만 로드하고, TS/JS 파일이 존재하면 경로만 반환한다.
 */
export function loadConfig(projectRoot?: string): KaraxConfig {
  const root = projectRoot ?? process.cwd();

  for (const candidate of CONFIG_CANDIDATES) {
    const configPath = join(root, candidate.name);
    if (!existsSync(configPath)) continue;

    if (candidate.type === 'json') {
      return loadJsonConfig(configPath) ?? {};
    }

    // TS/JS 모듈은 동기 로드 불가 — JSON fallback 탐색 계속
    // 사용자는 loadConfigAsync()를 써야 한다
  }

  return {};
}

/**
 * karax.config를 비동기로 로드한다.
 * TS/JS 모듈 설정 파일(export default)을 지원한다.
 *
 * @example
 * ```typescript
 * // karax.config.ts
 * export default {
 *   platform: 'spring-boot',
 *   thresholds: { maxFilesPerPr: 25 },
 * };
 * ```
 */
export async function loadConfigAsync(projectRoot?: string): Promise<KaraxConfig> {
  const root = projectRoot ?? process.cwd();

  for (const candidate of CONFIG_CANDIDATES) {
    const configPath = join(root, candidate.name);
    if (!existsSync(configPath)) continue;

    if (candidate.type === 'json') {
      return loadJsonConfig(configPath) ?? {};
    }

    // TS/JS 모듈 동적 import
    try {
      const absPath = resolve(configPath);
      const fileUrl = pathToFileURL(absPath).href;
      const mod = await import(fileUrl) as { default?: KaraxConfig };
      return mod.default ?? {};
    } catch {
      // import 실패 시 다음 후보로
    }
  }

  return {};
}

/**
 * 설정의 임계치 오버라이드를 프로파일에 적용한다.
 */
export function applyConfigOverrides(
  profile: PlatformProfile,
  config: KaraxConfig,
): PlatformProfile {
  if (!config.thresholds) return profile;

  return {
    ...profile,
    thresholds: {
      ...profile.thresholds,
      ...config.thresholds,
      mixedConcerns: config.thresholds.mixedConcerns ?? profile.thresholds.mixedConcerns,
    },
  };
}
