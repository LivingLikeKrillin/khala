# Nexus Slack Bot 설정 가이드

> Slack에서 `@khala`로 멘션하거나 DM으로 질문하면, Nexus의 하이브리드 검색 + LLM 답변을 Slack 메시지로 받을 수 있습니다.
>
> 팀을 Nexus 로 끌어오는 가장 마찰 없는 온램프다 — 새 URL·새 UI 로 보내는 대신, 하루 종일 열어두는
> 채널에서 `@khala <질문>` 하면 된다. Socket Mode 라 inbound 포트·도메인·터널이 필요 없고, 터널/Access
> 작업과 독립적으로 먼저 띄울 수 있다.

---

## 1. Slack App 생성

[api.slack.com/apps](https://api.slack.com/apps)에서 **Create New App** → **From scratch** 선택.

### 1.1 Bot Token Scopes 설정

**OAuth & Permissions** → **Scopes** → **Bot Token Scopes**에서 추가:

| Scope | 용도 |
|-------|------|
| `app_mentions:read` | @khala 멘션 감지 |
| `chat:write` | 채널/DM에 메시지 전송 |
| `im:history` | DM 메시지 읽기 |
| `im:read` | DM 채널 접근 |

### 1.2 Socket Mode 활성화

**Settings** → **Socket Mode** → **Enable Socket Mode**

App-Level Token을 생성한다 (scope: `connections:write`). 이 토큰이 `SLACK_APP_TOKEN` (`xapp-...`)이다.

> Socket Mode를 사용하면 public URL 없이 로컬/사내 환경에서 바로 동작한다.

### 1.3 Event Subscriptions

**Event Subscriptions** → **Enable Events** (Socket Mode 사용 시 Request URL 불필요)

**Subscribe to bot events**에서 추가:
- `app_mention` — 채널에서 @khala 멘션
- `message.im` — DM 메시지

### 1.4 워크스페이스에 설치

**OAuth & Permissions** → **Install to Workspace** → 권한 승인

설치 후 **Bot User OAuth Token** (`xoxb-...`)을 복사한다.

---

## 2. 환경 변수 — 토큰 셋

봇은 **세 개**의 토큰이 있어야 뜬다. 세 번째(`NEXUS_SLACK_TOKEN`)가 없으면 봇은 시동 자체를 거부한다
— 토큰 없이 떠서 모든 질의를 401 로 실패하는 조용한 오작동 대신.

```bash
# .env에 추가
SLACK_BOT_TOKEN=xoxb-...          # Bot User OAuth Token (Slack 앱)
SLACK_APP_TOKEN=xapp-...          # App-Level Token (Socket Mode)
SLACK_SIGNING_SECRET=...          # Basic Information → App Credentials (선택)

# Nexus bearer — 봇이 Nexus 에 붙는 읽기 전용 principal.
NEXUS_SLACK_TOKEN=...             # nexus auth gen-token 으로 발급
```

### 2.1 Nexus 토큰 발급 (`NEXUS_SLACK_TOKEN`)

봇은 하나의 서비스 principal 로 Nexus 에 붙는다 — MCP 서버가 `NEXUS_MCP_TOKEN` 을 쓰는 것과 똑같다.
운영자가 토큰을 발급하고, **capability 없이**(읽기 전용) 등록한다:

```bash
nexus auth gen-token   # 발급된 bearer 를 NEXUS_SLACK_TOKEN 에 넣는다
```

읽기 전용은 관례가 아니라 서버가 강제한다: Nexus 의 쓰기 경로(hide/restore/supersede, source 등록)는
`manage_documents`/`manage_sources` capability 를 요구하고 기본 거부다. capability 0 인 principal 은
그 엔드포인트에서 403 을 받는다. 봇이 쓰기 경로를 부를 일도 없지만, 버그가 그래도 부른다면 그 벽이 선다.

### 2.2 ⚠️ 봇의 clearance = 워크스페이스 전원에게 확장하는 신뢰의 바닥

단일 서비스 principal 이라는 건, **그 워크스페이스의 모든 멤버**(단일 채널 게스트·외부 공유채널 참여자
포함)가 그 principal 이 읽을 수 있는 것을 전부 읽는다는 뜻이다. 그래서 clearance 는 `auth.slack.clearance`
운영자 설정이고, **기본값은 `PUBLIC`** — 안전한 바닥이다.

- 외부 게스트가 있는 워크스페이스 → `PUBLIC` 로 두라.
- 전원이 직원인 워크스페이스 → `INTERNAL` 로 올려도 된다.

누가 들어오는지는 상류(Slack 워크스페이스 멤버십)에서 정해진다. 그 입장이 **무엇을 읽을 수 있는지**는
운영자의 명시적 선택이다. 게스트가 있다면 `PUBLIC` 밖으로 올리지 말 것.

### 2.3 채널마다 다른 코퍼스에 묻기 (선택)

기본값은 봇 전체가 **하나의 코퍼스**를 본다. 팀이 두 번째 코퍼스(예: 설계문서)에도 물어야 하면
채널을 코퍼스에 붙인다 — 그리고 그것은 결국 **채널을 토큰에 붙이는 일**이다.

**왜 토큰인가.** 요청 본문의 `tenant` 는 서버가 무시한다(`auth/scope.py`: 테넌트는 principal 의
것이고 요청은 넓힐 수 없다 — 테넌트 격리이자 존재 유출 방지). 그래서 코퍼스를 고르는 유일한
방법은 그 테넌트에 묶인 토큰을 쓰는 것이다.

```bash
# 코퍼스 하나당 변수 하나: 토큰|테넌트[|등급]  (등급 생략 시 NEXUS_SLACK_CLEARANCE)
NEXUS_SLACK_CORPUS_DESIGN=<nexus auth gen-token 값>|design_docs|INTERNAL

# 채널 → 별칭. 매핑에 없는 채널은 기본 코퍼스로 간다.
NEXUS_SLACK_CHANNELS=C01ABCDEF:design,C02GHIJKL:design
```

- 서버는 **같은 변수**에서 `slack-design` principal 을 파생한다(`auth/config.py`). 봇이 보내는
  토큰과 서버가 아는 토큰이 어긋나는 상태가 표현 불가능하다는 규율이 여기서도 그대로다.
- 값이 깨졌으면 **그 코퍼스만 건너뛴다.** 오타 하나로 배포 전체가 안 뜨면 안 된다.
- 별칭은 있는데 토큰이 없으면 그 채널은 **기본 코퍼스**로 간다(없는 토큰으로 401 을 내면
  사용자에게는 그냥 고장으로 보인다).
- 진단(`/visibility`, `/status`)도 **답변과 같은 토큰**으로 나간다 — 아니면 다른 코퍼스의 상태를
  보고한다.
- ⚠ 등급은 코퍼스마다 따로 정한다. §2.2 의 경고가 코퍼스마다 그대로 적용된다: 그 채널을 볼 수
  있는 사람 전원이 그 principal 이 읽는 것을 전부 읽는다.

---

## 3. 설치 및 실행

### 3.1 Docker (권장) — `--profile slack`

봇은 opt-in 프로필 서비스다. 세 토큰을 `.env` 에 넣고:

```bash
docker compose --profile slack up -d
```

`nexus-app` 과 `nexus-slack` 이 함께 뜬다. 봇은 `http://nexus-app:8000` 으로 Nexus 에 붙는다.

### 3.2 로컬 실행 (개발)

```bash
pip install -e '.[slack]'
docker compose up -d          # Nexus API 가 먼저 떠 있어야 함
nexus-slack                    # 또는: python -m nexus.slack.app
```

정상 시작 로그:
```
2026-03-15 12:00:00 nexus.slack.app INFO Nexus Slack Bot 시작 (Socket Mode)
```

`NEXUS_SLACK_TOKEN` 이 없으면:
```
nexus.slack.app ERROR NEXUS_SLACK_TOKEN 환경 변수가 필요합니다 — 봇은 Nexus 에 읽기 전용 principal 로 붙는다.
```
그리고 봇은 뜨지 않는다(exit 1).

### 3.3 토큰 회전

다른 Nexus 토큰과 동일하다: 새로 발급(`nexus auth gen-token`) → env 갱신 → 봇 재시작.

---

## 4. 사용법

### 채널에서 멘션

```
@khala 결제 서비스가 발행하는 토픽이 뭐야?
```

```
@khala payment-service와 notification-service의 관계는?
```

### DM으로 직접 질문

Nexus 봇에게 DM을 보내면 멘션 없이 바로 질문할 수 있다.

```
결제 서비스 장애 원인 분석해줘
```

### 스레드 응답

모든 답변은 원본 메시지의 **스레드**에 달린다. 채널이 어지러워지지 않는다.

### 스레드를 이어서 묻기 (멀티턴)

봇은 자기가 답하고 있는 **스레드를 읽는다.** 따라서 스레드 안에서는 생략형 질문이 통한다 — "그럼 그건 언제 바뀌었어?" 처럼 앞 질문을 다시 쓰지 않아도 된다.

이력은 **8턴 / 8KiB** 상한이 걸리고, 넘으면 오래된 쪽부터 버린다. 이어붙이는 게 아니라 후속 질문을 재작성해서 검색에 넘기며, **사용자가 실제로 친 문장은 절대 잃지 않는다** — 답변자는 재작성본과 원문을 함께 본다.

### 봇에게 봇 자신을 묻기

완전 일치하는 명령어를 보내면 검색 결과가 아니라 **시스템 상태 카드**가 온다. 코퍼스에 자기 자신에 대한 문서가 없으니 검색으로는 답이 나올 수 없고, 나온다면 그게 더 나쁜 답이다.

---

## 5. 응답 형태

Slack Block Kit으로 구성된 응답:

```
┌─────────────────────────────────────────────┐
│ 결제 서비스는 payment.completed 토픽을       │
│ Kafka로 발행합니다. [1][2]                   │  ← 답변 본문
├─────────────────────────────────────────────┤
│ [1] 결제 설계 문서 > 아키텍처 > 이벤트        │
│     (score: 0.92)                           │  ← 근거 (최대 5개)
│ [2] API 명세 > 결제 API (score: 0.78)       │
├─────────────────────────────────────────────┤
│ 📄 payment-service →PUBLISHES→              │
│    payment.completed                         │  ← 그래프 관계
│ 👁 payment-service → notification-service    │
│    (1500 calls)                              │
├─────────────────────────────────────────────┤
│ 출처: `docs/payment.md` | `docs/api.md`    │  ← 출처 링크
├─────────────────────────────────────────────┤
│ 경로: hybrid_then_graph | 450ms             │  ← 메타 정보
└─────────────────────────────────────────────┘
```

### 제한 사항

| 항목 | 제한 |
|------|------|
| 답변 길이 | **3,000자** — Block Kit의 블록당 `text` 상한. 잘림 표시(`…`)를 붙인 **뒤의** 길이가 상한 이하여야 한다 |
| 근거 표시 | 상위 5개까지 |
| 출처 링크 | 3개까지 |
| 그래프 관계 | designed 3개 + observed 3개까지 |
| API 타임아웃 | 60초 |

### 답변 피드백 (👍 / 👎)

모든 답변에 버튼 두 개가 붙는다. 👎를 누르면 사유를 네 가지 중에서 고르게 한다 — `wrong_evidence`(근거가 틀림) · `not_my_question`(내 질문이 아님) · `ignored_format`(요청한 형식 무시) · `not_found`(못 찾음).

설계상 **지표가 아니라 자료**다.

- **저장하는 것**: 투표와 사유 코드, 그리고 카운트. 그뿐이다.
- **저장하지 않는 것**: 자유 텍스트도, 누른 사람의 신원도 저장하지 않는다.
- **푸시하지 않는다.** 👎가 알림으로 튀지 않는다. 운영자가 `nexus feedback`으로 **조회할 때** 본다. 알림으로 만들면 응답 속도를 재게 되고, 그건 이 데이터가 답할 질문이 아니다.
- 사유는 👎에 한해, **1시간 이내에, 한 번만** 붙는다(투표당 사유는 덮어쓰지 않는다).
- 봇은 DB를 직접 붙지 않는다. 피드백도 다른 모든 것과 마찬가지로 **HTTP로** Nexus에 간다.

### 봇이 답할 수 없을 때

봇은 왜 못 답하는지를 **올바른 대상에게** 말한다. 401 은 운영자용(봇 토큰이 틀린 것이지 사용자 질문이
틀린 게 아니다), 나머지는 사용자에게 정직하게. 스택 트레이스는 절대 노출하지 않는다.

| 상황 | 대상 | 메시지 |
|------|------|--------|
| Nexus 401 | 운영자 | "봇 인증 설정이 잘못되었습니다 — 운영자에게 알리세요." |
| 503 / 연결 불가 | 사용자 | "지금 답변할 수 없습니다. 잠시 후 다시 시도하세요." |
| 근거 0건 (코퍼스는 있음) | 사용자 | "인덱싱된 문서에서 답을 찾지 못했습니다." |
| 코퍼스 0건 | 사용자 | "아직 인덱싱된 문서가 없습니다. 먼저 문서를 적재하세요." |
| 그 외 (429/500/timeout) | 사용자 (운영자는 로그) | "답변 중 오류가 발생했습니다. 잠시 후 다시 시도하세요." |

"근거 없음"과 "코퍼스 없음"은 다른 사실이다: 봇은 답변 응답의 `evidence_snippets` 로 전자를,
`/status` 의 `documents_count` 로 후자를 각각 확인한다 — 하나에서 다른 하나를 추측하지 않는다.

봇 토큰은 어떤 Slack 메시지에도, 어떤 로그 라인에도 나타나지 않는다.

---

## 6. 아키텍처

```
사용자 → Slack → Socket Mode → nexus.slack.app
                                    │
                              handle_mention()
                              handle_dm()
                                    │
                              _extract_query()
                                    │
                              POST /search/answer
                              (httpx → Nexus API)
                                    │
                              format_answer()
                              (Block Kit 변환)
                                    │
                              say(blocks=...)
                                    │
                              Slack ← 사용자
```

### 파일 구조

```
nexus/slack/
├── __init__.py
├── app.py          # Slack Bolt AsyncApp + Socket Mode 진입점
├── bot.py          # 이벤트 핸들러 + API 호출
└── formatter.py    # NexusResponse → Slack Block Kit 변환
```

---

## 7. 트러블슈팅

### Bot이 응답하지 않음
1. `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `NEXUS_SLACK_TOKEN` 세 개 모두 확인
2. Event Subscriptions에서 `app_mention`, `message.im` 구독 확인
3. Socket Mode가 활성화되어 있는지 확인
4. Nexus API (`http://localhost:8000/status`)가 정상인지 확인

### "봇 인증 설정이 잘못되었습니다" (운영자용)
- `NEXUS_SLACK_TOKEN` 이 유효한 Nexus bearer 인지 확인 — Nexus 가 401 을 돌려주고 있다.
- 재발급: `nexus auth gen-token` → env 갱신 → 봇 재시작.

### 봇이 아예 안 뜸 (exit 1)
- 로그에 `NEXUS_SLACK_TOKEN 환경 변수가 필요합니다` → 세 번째 토큰이 비어 있다. `.env` 에 넣고 재시작.

### "데이터베이스 연결 실패" 에러
- `docker compose up -d`로 인프라가 실행 중인지 확인
- `NEXUS_API_URL` 환경 변수가 올바른지 확인

### 답변이 "검색할 내용을 입력해주세요"
- `@khala` 뒤에 실제 질문을 포함해야 함
- `@khala`만 보내면 안내 메시지가 표시됨
