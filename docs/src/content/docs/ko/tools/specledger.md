---
title: specledger
description: 의사결정 책임성 — AI가 생성한 명세/ADR을 기록하고, 책임 있는 리뷰·사인오프 뒤로 코드 편집을 게이트한다.
---

specledger는 판단의 순간을 가정된 것이 아니라 **책임질 수 있는 것**으로 만듭니다. Python MCP 서버 + Claude Code `PreToolUse` 훅으로, AI가 생성한 ADR·설계 명세를 일관된 Markdown + frontmatter로 기록하고, 코드 편집이 쓰이기 전에 책임 있는 리뷰 — **AI 비평 → 사람의 이슈 처분 → 사인오프** — 를 강제하며, 선택적으로 승인된 문서를 Nexus 싱크로 발행합니다.

specledger가 보정하는 문제는 이렇습니다. 어시스턴트가 확신에 찬 명세를 내놓으면 가장 쉬운 길은 그냥 승인하는 것입니다. 리뷰는 아무도 제대로 읽지 않은 텍스트에 찍히는 녹색 체크마크, 즉 의례로 전락합니다. specledger는 판단이 비용이 싸고 흔적이 남는 곳에서 일어나도록 강제합니다. 명세가 승인되고 content hash로 스탬프되기 전까지, 비면제(non-exempt) 소스 경로를 대상으로 하는 모든 `Write`/`Edit`/`MultiEdit` 호출은 **차단**됩니다. 게이트는 구현 중에만 활성화됩니다 — `begin_implementation`이 무장하고 `end_implementation`이 해제합니다.

한 줄 정체성: "누가 무엇을, 왜 승인했는가"를 기록되고 귀속 가능한 행위로 만드는 원장 — 그 위로 고무도장을 찍고 지나갈 수 없습니다.

<img
  src="/diagrams/specledger.svg"
  alt="명세 생명주기: 기록됨 → 비평됨(이슈) → 승인됨(content hash) → 구현 중(게이트 무장, 편집 허용) → 완료. 승인 전까지 Write/Edit는 차단된다."
  style="max-width: 100%; height: auto; display: block; margin: 1.5rem auto;"
/>

## 핵심 개념

- **게이트** — 명세가 `approved` + content-hash 스탬프되기 전까지 비면제 경로의 파일 편집 도구가 차단됩니다. 기본 허용 글롭은 `docs/**`, `tests/**`(설정 가능).
- **무장 / 해제** — `begin_implementation`이 특정 명세에 대해 게이트를 무장하고, `end_implementation`이 해제합니다.
- **책임 있는 리뷰 흐름** — `critique`(AI 리뷰 → 이슈 개설) → 사람이 본문 수정 → `approve`(이슈별 처분 + 본문 변경 검증 + content hash 스탬프).
- **content-hash 스탬프 + 변조 감지** — 승인이 명세를 hash에 묶고, `status`가 상태와 변조를 보고합니다.
- **DB 없음** — 모든 상태가 `SPECLEDGER_DOCS` 아래 Markdown과 `SPECLEDGER_ROOT`의 작은 `.specledger/` 마커에 존재합니다.
- **선택적 Nexus 발행** — `publish`는 승인 문서를 Nexus 싱크로 보내며, 미설정 시 안전한 no-op입니다.

설치(`pip install -e ".[dev]"`), `.mcp.json`·`settings.json` 등록, 10개 MCP 도구는 영어 페이지([specledger](/tools/specledger/))를 참고하세요.
