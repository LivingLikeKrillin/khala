---
title: Arbiter
description: 사양(SPEC) 및 결정(ADR) 승인 이력을 관리하고, 사전 승인 기반 코드 수정을 강제하는 거버넌스 게이트.
---

Arbiter는 소프트웨어 아키텍처 의사결정의 책임성과 추적성을 보장하는 거버넌스 프레임워크입니다. Python 기반 MCP(Model Context Protocol) 서버 및 `PreToolUse` 인터셉터를 통해, 자동 생성된 ADR 및 설계 사양을 구조화된 마크다운 및 메타데이터 frontmatter로 영속화하고, 코드 구현 착수 전 단계별 검증 절차(**AI 비평 분석 → 이슈 항목 처분 → 승인권자 서명**)를 강제합니다. 승인 완료된 사양은 Nexus 지식 기판으로 동기화 발행할 수 있습니다.

형식적 승인(Rubber-stamping)으로 인한 품질 게이트 무력화를 방지하기 위해, Arbiter는 사양 본문이 검토 및 승인되어 SHA-256 무결성 해시(`content_hash`)로 잠금되기 전까지 비면제 소스 경로에 대한 일체의 파일 수정 도구(`Write`, `Edit`, `MultiEdit`) 호출을 결정론적으로 차단합니다. 본 거버넌스 게이트는 구현 수명주기에 연동되어 `begin_implementation` 호출 시 활성화되고 `end_implementation` 호출 시 해제됩니다.

<svg class="kh-fig" viewBox="0 0 560 224" role="img" aria-label="Arbiter 아키텍처 게이트 흐름: 승인 및 content_hash 잠금된 사양에 대해서만 구현 권한을 부여함. 기록됨 → 비평됨(이슈 2건) → 승인 및 잠금 상태로 전이되며, 승인 시점의 해시값과 현재 변경 해시가 일치해야 게이트가 개방됨. 불일치 시 Write/Edit 도구 차단.">
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

## 핵심 아키텍처 및 기능 명세

- **수정 차단 게이트 (PreToolUse Gate)** — 대상 사양이 `approved` 상태로 전이되고 `content_hash` 스탬프가 발급되기 전까지, 비면제 경로에 대한 파일 수정 도구를 인터셉트하여 차단합니다 (기본 허용 경로: `docs/**`, `tests/**`, 설정 변경 가능).
- **게이트 수명주기 관리** — `begin_implementation` 명령을 통해 특정 사양 식별자에 대해 게이트를 활성화(Arm)하고, 구현 완료 후 `end_implementation` 명령으로 비활성화(Disarm)합니다.
- **다단계 검증 워크플로** — `critique`(비평 에이전트의 정적 검토 및 이슈 발행) → 이슈 수정 및 본문 보완 → `approve`(이슈 처분 결과 확인, 본문 무결성 해시 산출 및 스탬프 발행) 순으로 진행됩니다.
- **무결성 해시 및 변조 감지 (Tamper Detection)** — 승인 시점의 본문 공백 정규화 SHA-256 해시를 frontmatter에 고정하며, `status` 조회 및 CI 파이프라인(`scripts/ledger_integrity.py`)에서 임의 수정 여부를 실시간으로 판정합니다.
- **파일 기반 상태 영속성** — 별도의 외부 데이터베이스 없이 `ARBITER_DOCS` 경로의 마크다운 파일과 `ARBITER_ROOT` 내 `.arbiter/` 메타데이터 디렉토리를 통해 모든 거버넌스 상태를 관리합니다.
- **Nexus 지식 기판 연동** — `publish` 명령을 통해 승인 완료된 사양 문서를 Nexus 저장소로 자동 동기화하며, 대상 미설정 시 무영향(no-op)으로 종료됩니다.
- **결정론적 단일 실행 로직** — CLI(`arbiter record`, `status`, `critique`, `approve`, `check-gate`)와 MCP 서버가 동일한 코어 비즈니스 로직을 호출하므로, 실행 주체(개발자 또는 자율 에이전트)에 상관없이 동일한 거버넌스 판정 결과를 보장합니다.

설치 및 상세 API 명세는 영문 참조 페이지([Arbiter](/tools/arbiter/))를 참고하십시오.
