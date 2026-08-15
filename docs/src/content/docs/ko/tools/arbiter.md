---
title: Arbiter
description: AI가 생성한 명세·ADR을 기록하고, 사인오프된 리뷰 뒤로 코드 편집을 게이트한다.
---

Arbiter는 판단의 순간을 가정하지 않고 **책임질 수 있게** 만듭니다. Python MCP 서버와 Claude Code `PreToolUse` 훅으로, AI가 생성한 ADR·설계 명세를 Markdown + frontmatter로 기록하고, 코드가 쓰이기 전에 리뷰 절차를 강제합니다: **AI 비평 → 사람의 이슈 처분 → 사인오프.** 승인된 문서는 Nexus 싱크로 발행할 수 있습니다.

어시스턴트가 확신에 찬 명세를 내놓으면 가장 쉬운 길은 그냥 승인하는 것입니다. 리뷰는 아무도 제대로 읽지 않은 텍스트에 찍히는 녹색 체크, 곧 의례로 전락합니다. Arbiter는 판단이 비용이 싸고 기록이 남는 곳에서 일어나도록 강제합니다. 명세가 승인되고 content hash로 스탬프되기 전까지, 비면제 소스 경로에 대한 모든 `Write`/`Edit`/`MultiEdit`는 **차단**됩니다. 게이트는 구현 중에만 켜집니다. `begin_implementation`이 무장하고 `end_implementation`이 해제합니다.

한마디로: "누가 무엇을, 왜 승인했는가"를 기록되고 귀속 가능한 행위로 만드는 원장입니다. 그 위로 고무도장을 찍고 지나갈 수 없습니다.

<svg class="kh-fig" viewBox="0 0 560 224" role="img" aria-label="Arbiter는 승인·content-hash된 명세에만 구현을 허용한다. SPEC-014는 기록됨 → 비평됨(이슈 2) → 승인·잠금으로 진행하고, 승인 해시 e34a17c9가 변경 해시와 일치해야 게이트가 열린다 — 불일치면 Write/Edit 차단.">
<defs><marker id="ab-a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="kh-fig-ah" d="M0 0 L10 5 L0 10 z"/></marker></defs>
<rect class="kh-fig-box" x="24" y="28" width="120" height="38" rx="6"/>
<text class="kh-fig-d" x="84" y="47" text-anchor="middle">Recorded</text>
<path class="kh-fig-line" d="M144 47 L176 47" marker-end="url(#ab-a)"/>
<rect class="kh-fig-box" x="176" y="28" width="150" height="38" rx="6"/>
<text class="kh-fig-d" x="251" y="47" text-anchor="middle">Critiqued · 2 issues</text>
<path class="kh-fig-line" d="M326 47 L358 47" marker-end="url(#ab-a)"/>
<rect class="kh-fig-box-acc" x="358" y="28" width="164" height="38" rx="6"/>
<text class="kh-fig-d" x="440" y="47" text-anchor="middle">Approved · locked</text>
<rect class="kh-fig-panel" x="24" y="92" width="512" height="118" rx="8"/>
<text class="kh-fig-h" x="42" y="116">GATE · APPROVED_HASH</text>
<line class="kh-fig-rule" x1="42" y1="128" x2="518" y2="128"/>
<text class="kh-fig-d" x="42" y="152">approved</text>
<text class="kh-fig-d" x="140" y="152">e34a17c9</text>
<text class="kh-fig-d" x="42" y="176">change</text>
<text class="kh-fig-d" x="140" y="176">e34a17c9</text>
<path class="kh-fig-line-acc" d="M244 152 L256 152 L256 164 M244 176 L256 176 L256 164 M256 164 L274 164" marker-end="url(#ab-a)"/>
<text class="kh-fig-verified" x="286" y="164">✓ MATCH · gate open</text>
<text class="kh-fig-s" x="42" y="200">mismatch → Write / Edit blocked</text>
</svg>

## 핵심 개념

- **게이트** — 명세가 `approved` + content-hash 스탬프되기 전까지 비면제 경로의 파일 편집 도구가 차단됩니다. 기본 허용 글롭은 `docs/**`, `tests/**`(설정 가능).
- **무장 / 해제** — `begin_implementation`이 특정 명세에 대해 게이트를 무장하고, `end_implementation`이 해제합니다.
- **책임 있는 리뷰 흐름** — `critique`(AI 리뷰 → 이슈 개설) → 사람이 본문 수정 → `approve`(이슈별 처분 + 본문 변경 검증 + content hash 스탬프).
- **content-hash 스탬프 + 변조 감지** — 승인이 명세를 hash에 묶고, `status`가 상태와 변조를 보고합니다.
- **DB 없음** — 모든 상태가 `ARBITER_DOCS` 아래 Markdown과 `ARBITER_ROOT`의 작은 `.arbiter/` 마커에 존재합니다.
- **선택적 Nexus 발행** — `publish`는 승인 문서를 Nexus 싱크로 보내며, 미설정 시 안전한 no-op입니다.
- **CLI로도 같은 게이트** — MCP 없이 손으로 돌릴 수 있습니다: `arbiter record` · `status` · `critique` · `approve` · `check-gate`. MCP 서버와 **같은 함수를 호출**하므로 사람이 돌리든 에이전트가 돌리든 판정이 갈리지 않습니다.

설치(`pip install -e ".[dev]"`), `.mcp.json`·`settings.json` 등록, 10개 MCP 도구는 영어 페이지([Arbiter](/tools/arbiter/))를 참고하세요.
