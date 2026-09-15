<p align="center">
  <img src="assets/logo.svg" alt="Khala" width="120" />
</p>

<h1 align="center">Khala</h1>

<p align="center">
  <strong>AI 시대의 소프트웨어 아키텍처를 교정하는 엔지니어링 도구 연합</strong>
</p>

<p align="center">
  <em>AI가 만들고, 인간이 이해한다.</em>
</p>

<p align="center">
  <a href="README.en.md"><strong>English Documentation (Global Overview)</strong></a>
</p>

---

Khala는 AI 지원 소프트웨어 개발에서 발생하는 **2대 핵심 실패 양식 — 기계의 확신에 찬 오답(Hallucination)과 인간의 형식적 승인(Rubber-stamping)** — 을 주관적 권고가 아닌 **결정론적 근거 검증(Deterministic Grounding)**으로 방어합니다. Khala는 단순한 독립 실행 도구가 아니라, 다양한 개발 도구들이 지식을 교환하는 단일 기판이자 공유 링크입니다. 생태계 전체는 **Khala**이며, 그 핵심 컴포넌트 중 하나가 **Nexus**입니다.

- **기계의 확신에 찬 오답 방어**: 모델은 만료되거나 부정확한 사실도 확신을 갖고 답변합니다. Khala는 신뢰가 아닌 기계적 검증으로 이를 방어합니다: 모든 인용은 검색된 근거 패킷에 대해 교차 검증되고, 답변 내 수치는 근거 원문에 반드시 존재해야 하며, 만료된 문서를 기반으로 한 답변에는 경고 플래그가 결속됩니다.
- **인간의 형식적 승인 방어**: AI가 생성한 코드를 정밀 검토 없이 통과시키는 위험을 차단합니다. 코드가 작성되기 전에 명시적인 검토 및 승인을 거버넌스 게이트로 강제합니다.

## 단일 기판, 네 종류의 정보 흐름

Khala는 서비스를 개발하고 운영하는 모든 주체 — 인간 엔지니어와 자율 에이전트 — 가 **동일한 단일 진실 공급원(Single Source of Truth)**에서 사고하도록 보장합니다. 문서 하나만으로는 이를 달성할 수 없습니다. AI 시대의 엔지니어링 조직에서 분산되기 쉬운 네 종류의 정보가 Khala의 단일 기판 위에서 통합됩니다:

<p align="center">
  <img src="assets/same-information.svg" alt="조직의 지식, 설계 결정, 운영 사실, 인지 이해도의 네 정보 흐름이 승인·최신성·인용이 보장된 단일 통제 기판으로 유입되어 인간과 에이전트에게 일관된 단일 뷰를 제공함." width="660" />
</p>

| 정보 유형 | 전체 주체에게 *동일성*을 유지하는 방식 | 담당 도구 |
|---|---|---|
| **조직의 공인 지식** — 문서, 사양, 기술 노하우 | 단일 지식 기판, 이중 접근 인터페이스: 사람(Web UI)과 에이전트(MCP/A2A)가 동일한 통제 코퍼스를 참조 — 동일한 승인, 동일한 최신 버전, 동일한 인용 체계. | [Nexus](./nexus) |
| **설계 의도 및 의사결정 이력** — 아키텍처 결정 | 의사결정 레코더: 코딩 에이전트가 생성하는 대규모 의사결정 트레이드오프를 한계비용 0으로 기록하고, 승인은 공인된 엔지니어의 명시적 책임 행위로 영속화. | [Arbiter](./arbiter) |
| **런타임 시스템 관측 상태** — 트레이스, 메트릭, 로그 | 판단 맥락 제공: 단순 모니터링 대시보드가 아니라, 텔레메트리를 승인된 지식(사양, 런북, 결정)과 결합하여 리뷰 및 장애 분석의 신뢰할 수 있는 증거 구성. | [Observer](./observer) (Nexus + OTel) |
| **인지 이해도 및 보증 현황** — 시스템 이해 | 인지 부채 원장: 전체 배포 아티팩트가 분모(이해해야 할 대상), 엔지니어의 유효한 보증(Vouch)이 분자(설명 가능한 범위) — 그 간극을 측정하고 체계적으로 해소. | [Adept](./adept) |

첫 번째 행은 조직이 즉각적으로 활용하는 일상적 가치입니다. 마지막 행은 시간이 갈수록 중요해지는 본질적 가치입니다: AI 생성 산출물이 폭발적으로 증가할 때, 시스템에 대한 조직의 이해도를 계측하지 않는 조직은 자신이 무엇을 더 이상 이해하지 못하는지조차 인지하지 못하게 됩니다.

## AI 시대가 초래하는 3대 엔지니어링 부채

AI가 시스템의 주된 생산자가 되면서 3대 부채가 누적됩니다:

- **기술 부채 (Technical Debt)** — 산출물이 유지보수 수용 속도보다 빠르게 누적되는 현상 → **Probe** + **Observer**로 결함 검출 및 완화.
- **의도 부채 (Intent Debt)** — 시스템이 *왜* 그렇게 설계되었는지 이유와 배경이 망실되는 현상 → **Arbiter**로 결정론적 추적 관리.
- **인지 부채 (Cognitive Debt)** — *시스템 전체를 아무도 완전히 이해하지 못하는* 불일치 현상 → **Adept**가 단일 기판에 대한 보증 커버리지(Vouch Coverage)로 계측하고 계획적인 해소를 지원.

이 재정의 사양은 [ADR-0002](adr/ADR-0002-reframe-system-command-debt.md)에 공식 수립되어 있습니다.

## 생태계 도구군

| 도구 | 핵심 역할 | 디렉터리 |
|---|---|---|
| **Nexus** | 문서 및 분산 추적(OTel) 대상 하이브리드 검색 — 모든 답변에 코드 수준에서 검증된 인용 결속. | [`./nexus`](./nexus) |
| **Archon** | 도메인 불변 상수에 대한 권위 창(Authoritative Window) — 질의 시점에 코드 상수에서 최신 값 판독 (Nexus 내장). | [`./nexus/nexus/claims`](./nexus/nexus/claims) |
| **Observer** | 플랫폼 인식 PR 정적 분석기 — PR 변경 범위, API 계약 린트/차분, 리뷰 체크리스트 생성. | [`./observer`](./observer) |
| **Arbiter** | ADR/SDD 거버넌스 MCP — 검토 가능하고 추적 가능한 설계 결정 원장 관리 및 Nexus 연동. | [`./arbiter`](./arbiter) |
| **Probe** | 변이 기반 테스트 품질 검증 하니스(Mutation Testing) — 통과된 테스트 스위트의 미검출 공백 식별. | [`./probe`](./probe) |
| **Adept** | 인지 부채 계측기 — 등급화된 이해도 보증(Vouch) 원장, 보증 커버리지 및 고아 아티팩트 분석. | [`./adept`](./adept) |
| **Adept web** | 인지 부채 팀 콘솔 — 브라우저 UI 및 파일/DB 백엔드 연동 지원. | [`./adept-web`](./adept-web) |
| **docs** | Astro Starlight 기반 공식 기술 문서 사이트. | [`./docs`](./docs) |

## 빠른 시작 가이드 (Nexus 로컬 스택 기동)

실행 환경 요구사항: Docker 및 Docker Compose ([go-task](https://taskfile.dev) 설치 권장, 미설치 시 compose 명령어 직접 실행).

```bash
# (선택 사항) LLM 답변 생성용 API 키 설정 — 미설정 시에도 근거 패킷 검색 파이프라인은 정상 동작
export ANTHROPIC_API_KEY=sk-ant-...

task up        # 또는: cd nexus && docker compose up -d
task models    # 최초 1회 임베딩 모델 로드 (docker compose exec nexus-ollama ollama pull nomic-embed-text)
```

> **개발 환경 무키(Keyless) 실행 옵션:** 외부 유료 API 키 없이도 답변 생성이 가능합니다. `NEXUS_LLM_PROVIDER=claude-code` 환경변수를 지정하고 `task llm-bridge`를 실행하면 호스트의 Claude Code 프로세스를 LLM 백엔드로 연동합니다.

브라우저에서 **http://localhost:8000** 접속 후 웹 인터페이스에서 질의를 수행하면 검증된 근거 및 출처 링크와 함께 답변이 생성됩니다.

- **문서 색인(Ingestion):** 웹 UI 내 업로드 기능 사용 또는 CLI 명령 실행: `docker compose exec nexus-app nexus ingest ./docs`
- **서비스 갱신 및 마이그레이션:** 소스 동기화 후 `task update` 실행 — 컨테이너 재빌드 및 DB 스키마 마이그레이션 적용 ([nexus/migrations](nexus/migrations/README.md))
- **서비스 중지:** `task down` (또는 `docker compose down`)

## 저장소의 정합성 및 무결성 검증 체계

보정(Calibration)을 핵심 약속으로 제시하는 시스템은 스스로에게도 동일한 엄격성을 강제해야 합니다. 아래의 가드들은 형식이 아니라 과거의 결함을 방지하기 위해 수립되었으며, 기억에 의존하지 않고 매 푸시마다 기계적으로 검증됩니다:

| 거버넌스 가드 | 거부 대상 | 존재 이유 |
|---|---|---|
| **문서-코드 앵커 계약** — [`doc-anchors.yml`](./doc-anchors.yml) | 앵커링된 소스 경로가 존재하지 않는 문서 | 문서의 만료 여부를 수동으로 판단하지 않고 코드 심볼 조인을 통해 결정론적으로 판정. |
| **임시 테스트 데이터베이스 마커** | 테스트용 스크래치 선언이 없는 데이터베이스 대상 실행 | 테스트 스위트의 테이블 초기화 로직으로 인한 개발/프로덕션 데이터베이스 유실 방지. |
| **조직 지문 스캐너** | 식별 가능한 세부 정보(비공개 식별자, 개인 토큰 등)가 포함된 푸시 | 커밋 메시지, PR 본문, 추적 파일 전반의 비공개 정보 유출 원천 차단. |
| **선언된 색인 세대(Generation)** | 코퍼스의 선언된 세대와 일치하지 않는 임베딩 모델 실행 | 버전이 다른 임베딩 모델이 동일 코퍼스 컬럼에 벡터를 기록하는 조용한 색인 오염 방지. |
| **사전 등록된 평가 판정 규칙** | 평가 점수 산출 이후에 수정된 평가 하니스 규칙 | 평가 라벨 서명 및 결과 산출 이전 판정 기준 사전 확정을 통한 객관성 보장. |
| **선언된 평가 코퍼스 범위** | 질의 대상 코퍼스가 불명확하거나 도달 불가능한 라벨 평가 실행 | 평가 라벨이 작성되지 않은 엉뚱한 테넌트를 측정하는 평가 오류 방지. |

2,988 test functions and 17 CI jobs run across the repository, including real Postgres integration with schema migrations. Governance artifacts (10 ADRs, 54 SPECs) are stamped and cryptographically verified for integrity in CI via `scripts/ledger_integrity.py`.

- **[→ 엔지니어링 로그](https://livinglikekrillin.github.io/khala/ko/engineering-log/)** — 시스템에서 발생한 결함, 결함이 드러난 계층, 그리고 이에 따른 수정 이력을 일자별로 기록한 분석 문서입니다.
- 열린 항목들은 [OPEN.md](./OPEN.md)에서 상태머신 원장으로 결정론적으로 관리됩니다.

## 공식 문서

전체 생태계 상세 참조, 아키텍처 철학 및 도구별 가이드는 공식 문서 사이트에서 제공됩니다:
**https://livinglikekrillin.github.io/khala/** (소스 경로: [`./docs`](./docs))

## 컨벤션 및 라이선스

- 기여 절차, 네이밍, 버전 관리 및 용어 규칙: [CONVENTIONS.md](./CONVENTIONS.md).
- 5대 핵심 도메인 표준 기술 용어집: [docs/glossary.md](docs/glossary.md).
- 용어 관리 기준 및 걷어낸 말 기록: [GLOSSARY.md](./GLOSSARY.md) (`scripts/check_terms.py`로 자동 검증).
- 라이선스: [MIT License](./LICENSE).
