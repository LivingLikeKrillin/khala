#!/usr/bin/env node

/**
 * PostToolUse 훅에서 호출되는 관심사 드리프트 감지 스크립트
 *
 * 환경변수 TOOL_INPUT에서 편집된 파일 경로를 추출하고,
 * 현재 브랜치의 변경 파일과 비교하여 관심사가 달라졌는지 판단한다.
 *
 * 드리프트 감지 시 stderr로 경고를 출력한다.
 */

import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(__dirname, '..');

// ─── 편집된 파일 경로 추출 ───

function getEditedFilePath() {
  const toolInput = process.env.TOOL_INPUT;
  if (!toolInput) return null;

  try {
    const parsed = JSON.parse(toolInput);
    return parsed.file_path || parsed.filePath || null;
  } catch {
    return null;
  }
}

// ─── 변경 파일 수집 ───

function getChangedFiles(base = 'origin/main') {
  try {
    const output = execSync(`git diff --name-only ${base}`, {
      cwd: projectRoot,
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    return output.trim().split('\n').filter(Boolean);
  } catch {
    return [];
  }
}

// ─── 메인 ───

async function main() {
  const editedFile = getEditedFilePath();
  if (!editedFile) return;

  const changedFiles = getChangedFiles();
  if (changedFiles.length < 2) return;

  // 빌드된 모듈이 있으면 사용
  const driftModulePath = resolve(projectRoot, 'dist/core/concern-drift.js');
  const detectorPath = resolve(projectRoot, 'dist/profiles/detector.js');

  if (!existsSync(driftModulePath) || !existsSync(detectorPath)) {
    // 빌드 안 된 상태면 단순 파일 수 체크로 fallback
    if (changedFiles.length > 25) {
      process.stderr.write(`⚠️ 변경 파일이 ${changedFiles.length}개입니다. PR 범위를 확인하세요.\n`);
    }
    return;
  }

  const { detectConcernDrift } = await import(driftModulePath);
  const { detectPlatform, getProfileForPlatform } = await import(detectorPath);

  const platform = detectPlatform();
  const profile = getProfileForPlatform(platform);
  if (!profile) return;

  // 편집 파일을 프로젝트 루트 기준 상대 경로로 변환
  const relativePath = editedFile
    .replace(/\\/g, '/')
    .replace(projectRoot.replace(/\\/g, '/') + '/', '');

  const result = detectConcernDrift(changedFiles, relativePath, profile);

  if (result.drifted && result.message) {
    process.stderr.write(result.message + '\n');
  }
}

main().catch(() => {});
