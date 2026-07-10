#!/bin/bash
# scripts/check-protected-files.sh
# PreToolUse hook에서 호출되어, 자동 생성 파일의 수작업 편집을 차단
#
# Claude Code 의 PreToolUse 훅은 페이로드를 **stdin(JSON)** 으로 넘긴다(인자가 아니다).
# 인자로 준 경우도 받아 준다 — 손으로 테스트할 때 편하도록.
TOOL_INPUT="${1:-$(cat)}"

# 보호 대상 파일 패턴 (경로 끝과 정확히 일치해야 한다)
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

# 페이로드 **전체**가 아니라 `file_path` 만 본다.
#
# 전에는 JSON 전체를 grep 했다. 그러면 보호 경로를 *언급*하기만 하는 무해한 편집도 막힌다 —
# "api/openapi.json 은 자동 생성됩니다" 라고 쓴 문서를 저장할 수 없게 된다. 가드가 문서를
# 못 쓰게 만들면 사람들은 가드를 끈다.
FILE_PATH=$(printf '%s' "$TOOL_INPUT" \
  | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 \
  | sed -E 's/.*:[[:space:]]*"([^"]*)"$/\1/')

# file_path 가 없는 페이로드(다른 툴, 빈 입력)는 막지 않는다. 모르면 통과시킨다.
[ -z "$FILE_PATH" ] && exit 0

# Windows 경로도 같은 규칙으로 본다.
FILE_PATH="${FILE_PATH//\\//}"

for pattern in "${PROTECTED_PATTERNS[@]}"; do
  # 경로 **끝**과 일치해야 한다. 부분 문자열이면 `src/api/types.ts.bak` 도 막힌다.
  if [ "$FILE_PATH" = "$pattern" ] || [ "${FILE_PATH%"/$pattern"}" != "$FILE_PATH" ]; then
    echo "{\"decision\":\"block\",\"reason\":\"❌ 이 파일은 자동 생성됩니다. 수작업 편집이 금지됩니다. (This file is auto-generated. Manual editing is prohibited.)\"}" >&2
    exit 2
  fi
done

exit 0
