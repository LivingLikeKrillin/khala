import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { detectPlatform, getProfileForPlatform } from '../src/profiles/detector.js';

describe('platform-detector', () => {
  let testDir: string;

  beforeEach(() => {
    testDir = join(tmpdir(), `probe-test-${Date.now()}`);
    mkdirSync(testDir, { recursive: true });
  });

  afterEach(() => {
    rmSync(testDir, { recursive: true, force: true });
  });

  it('build.gradle.kts가 있으면 spring-boot로 감지한다', () => {
    writeFileSync(join(testDir, 'build.gradle.kts'), '');

    expect(detectPlatform(testDir)).toBe('spring-boot');
  });

  it('pom.xml이 있으면 spring-boot로 감지한다', () => {
    writeFileSync(join(testDir, 'pom.xml'), '');

    expect(detectPlatform(testDir)).toBe('spring-boot');
  });

  it('next.config.js가 있으면 nextjs로 감지한다', () => {
    writeFileSync(join(testDir, 'next.config.js'), '');

    expect(detectPlatform(testDir)).toBe('nextjs');
  });

  it('next.config.mjs가 있으면 nextjs로 감지한다', () => {
    writeFileSync(join(testDir, 'next.config.mjs'), '');

    expect(detectPlatform(testDir)).toBe('nextjs');
  });

  it('vite.config.ts + src/pages/가 있으면 react-spa로 감지한다', () => {
    writeFileSync(join(testDir, 'vite.config.ts'), '');
    mkdirSync(join(testDir, 'src', 'pages'), { recursive: true });

    expect(detectPlatform(testDir)).toBe('react-spa');
  });

  it('package.json에 next 의존성이 있으면 nextjs로 감지한다', () => {
    writeFileSync(join(testDir, 'package.json'), JSON.stringify({
      dependencies: { next: '^14.0.0', react: '^18.0.0' },
    }));

    expect(detectPlatform(testDir)).toBe('nextjs');
  });

  it('판단 불가 시 unknown을 반환한다', () => {
    expect(detectPlatform(testDir)).toBe('unknown');
  });

  it('unknown이면 getProfileForPlatform이 undefined를 반환한다', () => {
    expect(getProfileForPlatform('unknown')).toBeUndefined();
  });

  it('spring-boot이면 getProfileForPlatform이 프로파일을 반환한다', () => {
    const profile = getProfileForPlatform('spring-boot');
    expect(profile).toBeDefined();
    expect(profile!.name).toBe('spring-boot');
  });
});
