---
name: split-pr
description: "현재 변경을 여러 PR로 분할하는 방법을 안내합니다. /split-pr로 수동 호출."
allowed-tools: Read, Bash, Grep, Glob
---

현재 브랜치의 변경이 여러 관심사에 걸쳐 있을 때, 구체적인 분할 방법을 안내합니다.

1. `npx karax check --json`으로 변경 분석
2. 각 관심사 그룹별로 파일 목록을 나열
3. 의존 관계를 고려한 머지 순서 제안
4. git 명령어 가이드 제공 (stash, cherry-pick, 새 브랜치 생성 등)

$ARGUMENTS로 특정 분할 전략을 지정할 수 있습니다.
