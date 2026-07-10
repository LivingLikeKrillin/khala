#!/bin/bash
# scripts/check-scope.sh
# PostToolUse hook에서 호출되는 PR 범위 확인 스크립트
# 파일 변경이 일어날 때마다 실행되어, 범위 초과 시 stderr로 경고

# 빌드된 CLI가 있으면 그것으로 관심사 기반 범위 분석, 없으면 단순 파일 수 체크로 폴백.
# 전역 링크(pnpm link --global)에 의존하지 않는다 — 훅은 자동 실행이라 PATH 에 `observer`가
# 없을 수 있다. 스크립트 위치 기준으로 빌드 산출물을 node 로 직접 부른다(분석 대상은 여전히 CWD).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="$SCRIPT_DIR/../dist/cli/index.js"

if [ -f "$CLI" ]; then
  # Git Bash(Windows)에서 node 는 POSIX 형식(/c/...) 절대경로를 못 읽으므로 Windows 경로로 변환.
  # Linux/macOS 에는 cygpath 가 없으니 POSIX 경로를 그대로 쓴다.
  if command -v cygpath >/dev/null 2>&1; then
    CLI="$(cygpath -w "$CLI")"
  fi
  node "$CLI" check --silent --format brief 2>&1
else
  # CLI 미빌드 상태(pnpm build 전)에서는 단순 파일 수 체크만
  CHANGED=$(git diff --name-only origin/main 2>/dev/null | wc -l)
  if [ "$CHANGED" -gt 25 ]; then
    echo "⚠️ 변경 파일이 ${CHANGED}개입니다. PR 범위를 확인하세요. (observer 를 빌드하면 관심사 기반 분석을 받습니다: cd observer && pnpm install && pnpm build)" >&2
  fi
fi
