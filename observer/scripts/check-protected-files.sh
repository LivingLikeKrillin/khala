#!/bin/bash
# scripts/check-protected-files.sh
# PreToolUse hook에서 호출되어, 자동 생성 파일의 수작업 편집을 차단

TOOL_INPUT="$1"

# 보호 대상 파일 패턴
PROTECTED_PATTERNS=(
  "src/design-tokens/tokens.json"
  "src/design-tokens/tokens.css"
  "src/design-tokens/theme.ts"
  "api/openapi.json"
  "api/openapi.yaml"
  "api/asyncapi.json"
  "api/asyncapi.yaml"
  "src/api/types.ts"
  "src/api/client.ts"
  "src/api/ws-types.ts"
  "src/api/ws-events.ts"
)

for pattern in "${PROTECTED_PATTERNS[@]}"; do
  if echo "$TOOL_INPUT" | grep -q "$pattern"; then
    echo "{\"decision\":\"block\",\"reason\":\"❌ 이 파일은 자동 생성됩니다. 수작업 편집이 금지됩니다. (This file is auto-generated. Manual editing is prohibited.)\"}" >&2
    exit 2
  fi
done
