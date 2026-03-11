/**
 * 플랫폼 프로파일 자동 감지
 *
 * 프로젝트 루트의 파일 구조를 보고 플랫폼을 추론한다.
 *
 * build.gradle.kts / pom.xml         → spring-boot
 * next.config.*                       → nextjs
 * vite.config.* + src/pages/          → react-spa
 * package.json dependencies 분석      → 추가 판단
 */

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { PlatformProfile } from './types.js';
import { springBootProfile } from './spring-boot.js';
import { nextjsProfile } from './nextjs.js';
import { reactSpaProfile } from './react-spa.js';

export type DetectedPlatform = 'spring-boot' | 'nextjs' | 'react-spa' | 'unknown';

const PROFILE_MAP: Record<Exclude<DetectedPlatform, 'unknown'>, PlatformProfile> = {
  'spring-boot': springBootProfile,
  'nextjs': nextjsProfile,
  'react-spa': reactSpaProfile,
};

/**
 * 프로젝트 루트를 분석하여 플랫폼을 감지한다.
 */
export function detectPlatform(projectRoot?: string): DetectedPlatform {
  const root = projectRoot ?? process.cwd();

  // Spring Boot 감지: build.gradle.kts, build.gradle, pom.xml
  if (
    existsSync(join(root, 'build.gradle.kts')) ||
    existsSync(join(root, 'build.gradle')) ||
    existsSync(join(root, 'pom.xml'))
  ) {
    return 'spring-boot';
  }

  // Next.js 감지: next.config.*
  if (
    existsSync(join(root, 'next.config.js')) ||
    existsSync(join(root, 'next.config.mjs')) ||
    existsSync(join(root, 'next.config.ts'))
  ) {
    return 'nextjs';
  }

  // React SPA 감지: vite.config.* + src/pages/
  const hasVite =
    existsSync(join(root, 'vite.config.ts')) ||
    existsSync(join(root, 'vite.config.js')) ||
    existsSync(join(root, 'vite.config.mjs'));
  const hasSrcPages = existsSync(join(root, 'src', 'pages'));

  if (hasVite && hasSrcPages) {
    return 'react-spa';
  }

  // package.json dependencies 기반 추가 판단
  const pkgPath = join(root, 'package.json');
  if (existsSync(pkgPath)) {
    try {
      const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8')) as Record<string, unknown>;
      const deps = {
        ...(pkg['dependencies'] as Record<string, string> | undefined),
        ...(pkg['devDependencies'] as Record<string, string> | undefined),
      };

      if ('next' in deps) return 'nextjs';
      if ('react' in deps && hasVite) return 'react-spa';
    } catch {
      // package.json 파싱 실패 — 무시
    }
  }

  return 'unknown';
}

/**
 * 감지된 플랫폼에 해당하는 프로파일을 반환한다.
 */
export function getProfileForPlatform(platform: DetectedPlatform): PlatformProfile | undefined {
  if (platform === 'unknown') return undefined;
  return PROFILE_MAP[platform];
}
