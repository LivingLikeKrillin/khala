#!/bin/bash
# scripts/check-scope.sh
# PostToolUse hook에서 호출되는 PR 범위 확인 스크립트
# 파일 변경이 일어날 때마다 실행되어, 범위 초과 시 stderr로 경고

# probe CLI가 빌드되어 있으면 사용, 없으면 skip
if command -v probe &> /dev/null || [ -f ./dist/cli/index.js ]; then
  npx probe check --silent --format brief 2>&1
else
  # CLI 미빌드 상태에서는 단순 파일 수 체크만
  CHANGED=$(git diff --name-only origin/main 2>/dev/null | wc -l)
  if [ "$CHANGED" -gt 25 ]; then
    echo "⚠️ 변경 파일이 ${CHANGED}개입니다. PR 범위를 확인하세요." >&2
  fi
fi
