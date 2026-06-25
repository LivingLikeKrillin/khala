# 팀 도그푸딩 배포 런북 — 로컬 구동 + 터널 노출

PFPlay 팀이 Nexus를 **실제로 사용**하게 만드는 최단 경로. 내 로컬 머신에서 스택을 돌리고,
터널로 외부에 HTTPS URL을 뚫어 팀에게 열어준다. 인프라 0, 견고한 1차 도그푸딩.

> 이 문서는 *운영 런북*이다. 제품 사용법(질문/근거 패널/신뢰 배지)은
> [Nexus 웹 사용 가이드](https://… /ko/tools/nexus-web/)를 팀에게 안내한다.

## 보안 모델 (먼저 읽기)

- **enforced 모드 + 토큰 게이트**: `config.yaml`의 `auth.mode: enforced`라 토큰 없이는 익명
  접속 시 **PUBLIC 문서만** 보인다. PFPlay 기획/정책 문서는 결정론적 분류 엔진
  (`nexus/nexus/ingest/classifier.py`)이 **기본 `INTERNAL`** 로 매긴다 → 토큰 인증한 팀원만
  열람. 비밀/PII가 감지되면 자동으로 `RESTRICTED`/격리되어 검색에 절대 안 뜬다.
- **enforced 부팅 가드**: principal의 `token_sha256`이 `REPLACE_ME` 플레이스홀더면 서버가
  **부팅을 거부**한다(known-credential 출하 방지). 즉 실제 토큰을 발급해 넣기 전엔 안 뜬다.
- **터널은 `:8000`만**: 앱 포트만 뚫는다. `5432`(db)·`11434`(ollama)는 절대 터널하지 않는다.

## 사전 준비

- Docker Desktop, (선택) [go-task](https://taskfile.dev)
- 터널 도구 — [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
  (quick tunnel, 계정 불필요) 또는 Tailscale Funnel
- **Notion 통합 토큰** + 적재할 PFPlay 페이지 id (기획/정책 문서 루트)
- (선택) `ANTHROPIC_API_KEY` — LLM 답변 생성용. 없으면 근거 검색은 되고 서술 답변만 비활성.

---

## 1. 스택 기동

```bash
cd nexus
cp .env.example .env          # (선택) ANTHROPIC_API_KEY 설정
task up                       # 또는: docker compose up -d   (핵심 컨테이너만)
task models                   # 최초 1회: 임베딩 모델(nomic-embed-text) 받기
```

→ `http://localhost:8000` 동작 확인. (아직 토큰 미발급이면 enforced 부팅 가드에 걸릴 수 있으니
2단계 먼저 끝내고 재시작.)

## 2. 팀 토큰 발급 (1인 1토큰)

토큰은 평문(팀원에게 전달) + 해시(`config.yaml`에 저장) 짝으로 다룬다. 한 토큰을 **한 번** 만들어
같은 값을 전달·해시한다:

```bash
# 팀원 1명당 반복
T=$(docker compose exec -T nexus-app nexus auth gen-token | tr -d '\r')
echo "→ 이 토큰을 해당 팀원에게 (비밀): $T"
echo "$T" | docker compose exec -T nexus-app nexus auth hash-token   # → token_sha256 출력
```

출력된 해시(접두사 없는 64자 hex)를 `nexus/config.yaml`의 `auth.principals`에 추가한다
(tenant·clearance 고정):

```yaml
auth:
  mode: enforced
  allowed_origins:
    - "https://<터널-공개-URL>"      # 3단계에서 확정
  principals:
    - name: "alice"
      token_sha256: "a1b2c3…(64자 hex)"   # hash-token 출력 그대로 (sha256: 접두사 없음)
      tenant: "pfplay"
      clearance: "INTERNAL"
    - name: "bob"
      token_sha256: "d4e5f6…(64자 hex)"
      tenant: "pfplay"
      clearance: "INTERNAL"
```

> `config.yaml`은 `.:/app`로 **마운트**되어 라이브다 → 편집 후 **재시작만** 하면 된다(재빌드 불필요):
> `docker compose restart nexus-app`. `tenant: pfplay`는 4단계 적재 tenant와 **반드시 일치**해야
> 팀원이 그 문서를 본다.

## 3. CORS origin 허용

브라우저 앱이 `Authorization` 헤더를 보내려면 origin allowlist가 필요하다(`"*"` 불가). 3단계에서
터널 URL이 확정되면 `config.yaml`의 `auth.allowed_origins`에 그 **공개 HTTPS URL**을 넣고 재시작.

## 4. PFPlay Notion 문서 적재

`NOTION_TOKEN`은 compose env에 없으니 `exec -e`로 주입한다. tenant는 `pfplay`로 고정:

```bash
docker compose exec -e NOTION_TOKEN="secret_…" -T nexus-app \
  nexus ingest-notion --tenant pfplay --roots "<pageid1>,<pageid2>"
# 출력: ingested=… idempotent=… empty=… skipped=… watermark=…
```

- 분류는 **자동 INTERNAL**(비밀/PII는 RESTRICTED/격리). caller가 분류를 올릴 수 없다 — 서버가 결정.
- 증분 갱신: 이전 출력의 `watermark` 값을 `--since <ISO8601>`로 넘기면 변경분만.
- 파일시스템 문서(설계 산출물 등)도 같이: `docker compose exec nexus-app nexus ingest ./docs`.

## 5. 터널로 외부 노출 (`:8000`만)

```bash
cloudflared tunnel --url http://localhost:8000
# → https://<무작위>.trycloudflare.com 같은 공개 HTTPS URL 발급
```

이 URL을 3단계 `allowed_origins`에 넣고 `docker compose restart nexus-app`. (durable URL이 필요하면
named tunnel로 승격; quick tunnel은 세션마다 URL이 바뀐다.)

> **공유 LAN 주의**: 기본 compose는 `5432`·`11434`를 호스트에 게시한다. 사무실 LAN에 노출되는 게
> 꺼려지면 방화벽으로 막거나, `docker-compose.yml`의 해당 `ports`를 `127.0.0.1:5432:5432`처럼
> 루프백 바인딩으로 바꾼다(이 변경은 로컬 dev 기본을 건드리니 별도 판단).

## 6. 팀에 공유

각 팀원에게 (1) 공개 터널 URL, (2) 본인 토큰을 전달. 웹은 그 토큰을 Bearer로 자동 사용한다.
사용법은 **Nexus 웹 사용 가이드** 링크로 안내(질문하기·근거 패널·신뢰 배지·"못 찾으면 거부는 기능").

### 인증 sanity check
- 토큰 없이 공개 URL 접속 → **PUBLIC만/빈 결과**여야 정상(= INTERNAL 게이트 작동).
- 토큰으로 접속 → PFPlay INTERNAL 문서가 근거와 함께 답에 등장.

## 7. 목소리를 데이터로 (단, 정량 신호만)

팀이 **무엇이 안 잡혔는지**의 정량 신호가 이미 수집된다 — 단 **쿼리 원문은 저장 안 한다**
(`search_log`는 `query_sha256` 해시 + `query_len`만, 프라이버시 설계). 즉 *얼마나·어떤 패턴으로*
실패하는지는 보이지만 *무슨 질문이었는지 literal* 은 못 본다.

```bash
# 집계 건강도: no-answer 율, 그래프 빈응답 율, LLM 실패 율, 평균 스니펫, p95 지연
docker compose exec nexus-db psql -U nexus -d nexus -c "SELECT * FROM v_search_health;"

# 미적중/저점수 질의 패턴(원문 아님): 답 못 준 건, 점수, 스니펫 수, 라우트
docker compose exec nexus-db psql -U nexus -d nexus -c \
  "SELECT ts, route, no_answer, top_score, n_snippets, query_len FROM search_log \
   WHERE no_answer ORDER BY ts DESC LIMIT 50;"
```

높은 `no_answer_rate`/낮은 `top_score` = 코퍼스 공백 또는 다음 기능(리랭킹/그래프랭킹 등)의 방아쇠.
**literal 한 "목소리"(어떤 질문이 왜 실패했나)는 로그가 아니라 팀에게 직접** 듣는다 — 이 런북의
1차 목표가 바로 그 직접 피드백 루프를 여는 것이다.

## 정지 / 업데이트

```bash
git pull && task update    # 이미지 재빌드·재기동 + DB 마이그레이션
task down                  # 정지
```
