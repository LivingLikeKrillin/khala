---
name: check-scope
description: "현재 브랜치의 변경 범위를 분석합니다. /check-scope로 수동 호출."
allowed-tools: Read, Bash, Grep, Glob
---

현재 브랜치의 변경 파일을 분석하여 PR 범위 리포트를 생성합니다.

1. `npx karax check`를 실행합니다.
2. 결과가 정상이면 "✅ 현재 변경은 리뷰 가능한 범위입니다"로 요약합니다.
3. 경고가 있으면 분할 제안을 포함하여 안내합니다.

$ARGUMENTS가 있으면 특정 파일 목록에 대해서만 분석합니다.
