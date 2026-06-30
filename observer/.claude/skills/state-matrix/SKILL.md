---
name: state-matrix
description: "기능/화면의 State Matrix를 생성합니다. /state-matrix [기능명]으로 호출."
allowed-tools: Read, Write, Bash, Grep, Glob
---

기능/화면에 대한 State Matrix를 생성합니다.

1. $ARGUMENTS에서 기능/화면 이름을 받습니다
2. 해당 기능과 관련된 코드 파일을 탐색합니다
3. docs/templates.md의 State Matrix 템플릿을 기반으로 초안을 생성합니다
4. Layer 1 (필수 4종: loading, empty, success, error)을 반드시 포함합니다
5. 코드 분석을 통해 Layer 2~4 해당 여부를 판단합니다
   - 인증/권한 관련 코드가 있으면 → Layer 2 포함
   - 폼/입력 관련 코드가 있으면 → Layer 3 포함
   - WebSocket/실시간 관련 코드가 있으면 → Layer 4 포함
6. 결과를 docs/state-matrices/{기능명}.md에 저장합니다

상세 규정: docs/guidelines/state-matrix-guidelines.md 참조
