# Khala Slack Bot 설정 가이드

> Slack에서 `@khala`로 멘션하거나 DM으로 질문하면, Khala의 하이브리드 검색 + LLM 답변을 Slack 메시지로 받을 수 있습니다.

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

## 2. 환경 변수

```bash
# .env에 추가
SLACK_BOT_TOKEN=xoxb-...          # Bot User OAuth Token
SLACK_APP_TOKEN=xapp-...          # App-Level Token (Socket Mode)
SLACK_SIGNING_SECRET=...          # Basic Information → App Credentials

KHALA_API_URL=http://localhost:8000  # Khala API 주소 (Docker 내부: http://khala-app:8000)
```

---

## 3. 설치 및 실행

```bash
# slack 의존성 설치
pip install -e '.[slack]'

# Khala API가 먼저 실행 중이어야 함
docker compose up -d

# Slack Bot 실행
python -m khala.slack.app
```

정상 시작 로그:
```
2026-03-15 12:00:00 khala.slack.app INFO Khala Slack Bot 시작 (Socket Mode)
```

### Docker로 실행 (선택)

docker-compose.yml에 서비스를 추가할 수 있다:

```yaml
khala-slack:
  build: .
  command: python -m khala.slack.app
  env_file: .env
  depends_on:
    khala-app:
      condition: service_healthy
  restart: unless-stopped
```

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

Khala 봇에게 DM을 보내면 멘션 없이 바로 질문할 수 있다.

```
결제 서비스 장애 원인 분석해줘
```

### 스레드 응답

모든 답변은 원본 메시지의 **스레드**에 달린다. 채널이 어지러워지지 않는다.

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
| 답변 길이 | 3,800자 초과 시 자동 truncate |
| 근거 표시 | 상위 5개까지 |
| 출처 링크 | 3개까지 |
| 그래프 관계 | designed 3개 + observed 3개까지 |
| API 타임아웃 | 60초 |

### 에러 시

```
⚠️ 오류: Khala 데이터베이스에 연결할 수 없습니다
```

LLM 호출 실패 시에도 근거 snippet은 그대로 제공된다 (CLAUDE.md 규칙 준수).

---

## 6. 아키텍처

```
사용자 → Slack → Socket Mode → khala.slack.app
                                    │
                              handle_mention()
                              handle_dm()
                                    │
                              _extract_query()
                                    │
                              POST /search/answer
                              (httpx → Khala API)
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
khala/slack/
├── __init__.py
├── app.py          # Slack Bolt AsyncApp + Socket Mode 진입점
├── bot.py          # 이벤트 핸들러 + API 호출
└── formatter.py    # KhalaResponse → Slack Block Kit 변환
```

---

## 7. 트러블슈팅

### Bot이 응답하지 않음
1. `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN` 확인
2. Event Subscriptions에서 `app_mention`, `message.im` 구독 확인
3. Socket Mode가 활성화되어 있는지 확인
4. Khala API (`http://localhost:8000/status`)가 정상인지 확인

### "데이터베이스 연결 실패" 에러
- `docker compose up -d`로 인프라가 실행 중인지 확인
- `KHALA_API_URL` 환경 변수가 올바른지 확인

### 답변이 "검색할 내용을 입력해주세요"
- `@khala` 뒤에 실제 질문을 포함해야 함
- `@khala`만 보내면 안내 메시지가 표시됨
