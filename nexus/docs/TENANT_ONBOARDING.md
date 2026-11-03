---
title: 테넌트 온보딩 런북 — 새 프로젝트의 문서를 khala 에 넣는 절차
doc_type: runbook
---

# 테넌트 온보딩 런북 — 새 프로젝트의 문서를 khala 에 넣는 절차

**한 장짜리 절차가 없었다.** 2026-11-02 에 khala 자신에게 「새 테넌트를 추가하고 문서를 적재하는
절차」를 물으니 배포 런북(`TEAM_DOGFOOD_DEPLOY.md`) 조각 다섯이 흩어져 나왔다. 이 문서는 그 조각을
**새 프로젝트 하나를 테넌트로 올리는 순서**로 다시 묶은 것이다. 명령은 전부 2026-11-02 기준
`python -m nexus.cli --help` 와 `docker-compose.yml` 에서 확인한 것만 적었고, 확인하지 못한 것은
그렇다고 적었다.

**테넌트가 무엇인가.** 코퍼스의 경계이자 **읽기 범위의 단위**다. 문서는 `documents.tenant` 로
갈리고, 읽는 쪽은 principal 토큰의 `read_tenants` 로 갈린다. 요청이 보내는 테넌트 값은 무시된다
(`auth/scope.py`). 그래서 「테넌트를 만든다」는 행위는 따로 없다 — **그 이름으로 처음 적재하는
순간 생기고, 그 이름을 읽을 수 있는 principal 을 발급해야 비로소 누가 본다.**

---

## 0. 적재 전에 정할 것 (소유자 결정)

| 결정 | 왜 먼저인가 | 기본 권고 |
|---|---|---|
| **테넌트 이름** | `documents.rid` 가 `tenant:상대경로` 에서 결정적으로 만들어진다. 나중에 바꾸면 전 문서가 새 문서가 된다 | 소문자 영문, 조직·개인·제품의 실명 금지(공개 리포) |
| **소스 형태** | 로컬 `.md` 폴더와 Notion 두 경로만 있다. 둘은 명령이 다르다 | 리포 안 `docs/` 폴더 |
| **재적재 주기** | 주기 재적재 컨테이너는 **하나 = 테넌트 하나**다(아래 §3) | 1시간(기본값) |
| **누가 읽나** | principal 마다 `read_tenants` 와 clearance 상한이 있다 | 에이전트용 읽기 전용 principal 하나 + Slack 은 필요할 때 |
| **공개 가능성** | 리포는 공개라 테넌트 이름·문서 제목이 PR·로그에 드러난다 | 비공개면 중립 이름 + §5 지문 목록 추가 |
| **질의 텍스트 보존** | 꺼져 있으면 👎·기권 질문이 라벨 재료가 못 된다 | **에이전트 principal 에만 켠다**(사람은 고지 뒤 옵트인) |

---

## 1. 소스 마운트와 임베딩 세대 — 컨테이너 안에서만 적재한다

⛔ **호스트 셸에서 `nexus ingest` 를 돌리지 마라.** 임베딩 세대(모델 · 컬럼 · 백엔드)는 env 로
오고 그 env 는 컨테이너에만 있다. 호스트에서 돌리면 `config.yaml` 기본값(768/nomic)으로 해석해
**검색되지 않는 컬럼**에 넣는다(`docker-compose.yml` 의 reingest 블록 주석, 2026-09-18 실측).

소스 폴더는 `.env` 의 `INGEST_SRC_PATH` 로 `nexus-app` 과 `nexus-reingest` 양쪽에
`/ingest-src` 로 마운트된다. 2026-11-02 라이브는 `…/[projects] picasso/docs` 다. 두 번째
프로젝트를 올리려면 **마운트를 하나 더 다는 compose 변경**이 필요하다(§3 의 한계와 같은 뿌리).

```bash
# .env 를 바꾼 뒤 — ⛔ `compose restart` 는 env 를 다시 읽지 않는다
cd nexus && docker compose -f docker-compose.yml up -d nexus-app
```

적재 전 **새 테넌트의 세대를 선언**한다. 선언은 테넌트별이고 append 다. 선언이 없으면 적재는
**경고만 내고 통과**한다(fail-open, `index/generation.py:127-133`) — 선언해 두어야 어긋난 세대의
실행이 거부된다(2026-08-10 에 선언 없이 호스트에서 돌려 768 컬럼에 들어간 사고가 이 명령의 유래다).

```bash
docker exec nexus-app python -m nexus.cli generation declare --tenant <tenant> \
    --column embedding_1024 --model KURE-v1 --by <who>
docker exec nexus-app python -m nexus.cli generation show
```

---

## 2. 첫 적재

```bash
# 로컬 폴더 — Collect → Classify → Chunk → BM25 → Vector → Graph
docker exec nexus-app python -m nexus.cli ingest /ingest-src --tenant <tenant>

# 해시 무시 전체 재적재가 필요할 때만
docker exec nexus-app python -m nexus.cli ingest /ingest-src --tenant <tenant> --force
```

Notion 이 소스면 `task ingest:notion ROOTS="<pageId>,…"` 다(`TEAM_DOGFOOD_DEPLOY.md` §5). 삭제 반영은
`FLAGS="--reconcile --dry-run"` 으로 계획을 먼저 본다.

**적재가 먹는 문서 모양**은 `WRITING_FOR_RETRIEVAL.md` 에 따로 적었다. 문서를 쓰는 에이전트에게
그 문서를 먼저 읽히는 것이 재적재를 줄이는 가장 싼 방법이다.

적재 직후 확인 셋:

```bash
docker exec nexus-app python -m nexus.cli status
docker exec nexus-app python -m nexus.cli persistence-health
docker exec nexus-app python -m nexus.cli query "이 프로젝트의 목적은" --tenant <tenant> --no-answer
```

세 번째는 LLM 을 부르지 않는다(지출 0). 결과가 0건이면 코퍼스가 아니라 **임베딩 컬럼**을 먼저
의심하라 — 2026-09-18 에 사이드카 없이 적재가 돌아 366조각이 전부 거부된 적이 있다.

---

## 3. 주기 재적재 — 컨테이너 하나가 테넌트 하나다

```yaml
# docker-compose.yml  nexus-reingest (profile: reingest)
REINGEST_TENANT:           ${REINGEST_TENANT:-}        # 기본값 없음 — 비면 시동 거부
REINGEST_SRC:              ${INGEST_SRC_PATH:-}         # 기본값 없음 — 비면 시동 거부
REINGEST_INTERVAL_SECONDS: ${REINGEST_INTERVAL_SECONDS:-3600}
```

기본값이 없는 것은 의도다. 비면 `./docs`(khala 자기 문서)로 폴백해 **남의 코퍼스에 우리 문서를
주기적으로 밀어 넣는** 사고를 막기 위해서다.

**한계.** 서비스 하나에 테넌트 하나 · 소스 하나다. 2026-11-02 라이브는 `picasso` 가 쓰고 있다.
두 번째 테넌트를 주기 재적재하려면 compose 에 서비스를 하나 더 선언해야 한다(env 이름이
전역이라 `REINGEST_TENANT_2` 류의 분리가 같이 필요). **이 변경은 아직 없다** — 첫 프로젝트는 수동
`ingest` 로 시작하고, 주기화는 그 다음이다.

사이드카가 안 떠 있으면 그 회차를 **건너뛴다**(실행 직전에 묻는다). 조용히 도는 것보다 낫다.

---

## 4. 읽기 권한 — principal 이 테넌트를 정한다

```bash
docker exec nexus-app python -m nexus.cli auth --help     # gen-token 등
```

- **에이전트용**: 읽기 전용 principal 하나를 발급하고 `read_tenants` 에 새 테넌트를 넣는다. 이
  principal 이름이 곧 유입 통계의 분모 식별자가 되므로 프로젝트별로 따로 둔다.
- **개발 셸**: `.env` 의 `NEXUS_DEV_READ_TENANTS` 에 추가 + `NEXUS_DEV_CLEARANCE_VERIFIED` 날짜.
- **Slack**: 봇은 `NEXUS_SLACK_READ_TENANTS` 에 적힌 테넌트만 본다. 봇에 `NEXUS_SLACK_TENANT` 를
  주면 **아무 일도 안 하면서 무언가 하는 것처럼 보인다**(compose 주석). 유효 clearance 는
  min(principal, 요청값)이라 `NEXUS_SLACK_CLEARANCE` 를 봇 쪽에도 같이 줘야 한다 — 이 줄이 빠졌던
  동안 봇은 모든 질문에 `hits=0` 을 200 OK 로 돌려줬다.
- **CLI `--tenant`**: 로컬 CLI 는 테넌트를 직접 고른다. 문서 쓰는 에이전트가 자기 결과를 확인할
  때 쓰는 문이다.

---

## 5. 공개 리포의 지문 — 이름이 새지 않게

`scripts/fingerprint_scan.py` 가 `git add` 뒤 추적 파일 전체를 본다. 잡는 것은 둘이다.

- `ORG_NAMES` 의 조직 이름(소문자 부분일치). 2026-11-02 현재 종료된 파트너 프로젝트 이름 하나가
  들어 있다 — 그 이름은 이 문서에도 적을 수 없다. 그것이 이 검사가 하는 일이다. **새 프로젝트가
  비공개면 그 이름을 여기 추가한다** — 추가하는 순간 리포 어디에도 그 이름을 못 적게 된다는
  뜻이므로, 테넌트 이름은 처음부터 중립어로 짓는다.
- Notion 마커(`notion` · `page_id` · `root_id` …)와 같은 줄에 있는 32자 16진. 합성 ID 는
  `ALLOWED_IDS` 에 **근거와 함께** 올린다.

---

## 6. 문서↔코드 앵커 — 코드를 서술하는 문서라면

두 기제가 있고 쓰임이 다르다.

- `doc-anchors.yml` + `python scripts/check_doc_drift.py`: **khala 자기 문서**가 **khala 코드**를
  가리킬 때. 경로는 이 리포 상대 경로라 외부 프로젝트에는 못 쓴다.
- `nexus.cli code scan | bind | drift`: 적재된 청크에 코드 심볼 앵커를 붙인다(LLM 호출 없음).
  코드는 `/code-src` 마운트에서 읽는다. **2026-11-02 라이브의 `/code-src` 는 종료된 프로젝트의
  코드다.** 새 프로젝트 코드로 바꾸는 것은 compose 마운트 변경이고 소유자 결정이다. 바꾸기 전에는
  `code` 명령을 새 테넌트에 돌리지 마라 — 엉뚱한 코드에 바인딩된다.

---

## 7. 첫 평가셋 — 라벨은 리포에, 문서는 라이브에

평가 라벨 형식은 `tests/eval/ko/labels.yaml` 이 정본이다(SPEC-nexus-korean-retrieval-eval §4.2).
규칙 셋만 옮긴다.

1. **질의는 문서 쪽에서 만든다.** 문서를 고르고 사람이 칠 법한 질문을 쓰되 제목을 베끼지 않는다.
2. **gold 는 경로의 집합**이고 기대 어휘 칸은 없다 — 토크나이저 비교를 불가능하게 만든 결함이
   그것이었다.
3. `provenance` · `authored_by` · `reviewed_by` · `reviewed_revision` 을 채운다. 리뷰 안 된 라벨은
   라벨이 아니다.

⛔ **내부 문서를 평가 팩으로 리포에 넣지 않는다.** 공개 리포라 재배포가 된다. 하니스의 팩
(`ko-k8s-2026-08-01`)이 공개 k8s 문서인 이유가 그것이다. 새 프로젝트의 라벨은 리포에 두되 **문서는
라이브 테넌트에서** 측정한다 — 그 측정 경로는 `SPEC-nexus-improvement-loop` 가 정한다.

첫 목표는 10~20문항이다. 숫자를 내려면 라벨 100건 이상이 필요하고(보고서 2026-11-02 §평가), 그
전까지는 **실패 목록**이 산출물이다.

---

## 8. 유입을 만든다 — 테넌트는 읽히지 않으면 없는 것과 같다

이 리포의 CLAUDE.md 가 「조직 지식은 khala 를 먼저 치라」고 적어 두고도 두 달간 0회 쓰였다.
부를 방법이 없었기 때문이다. 새 프로젝트에선 **처음부터** 셋을 같이 한다.

1. 그 프로젝트 리포의 CLAUDE.md 에 같은 문구를 넣되, 입구는 **MCP(`NEXUS_MCP_TOKEN`) 또는 HTTP
   bearer 토큰**으로 적는다. ⛔ **CLI `docker exec … query` 를 권하지 마라** — CLI 는 principal 을
   넘기지 않아 질문이 보존되지 않고(`cli.py:398-400`), 그러면 아래 3 의 분모에 안 잡힌다. 이 리포의
   CLAUDE.md 가 CLI 를 권하는 것은 khala 자기 작업용이다. MCP 서버는 토큰을 넘기는 HTTP 클라이언트라
   API 가 principal 을 풀고 보존이 된다(`mcp/server.py:33-40`).
2. 에이전트 principal 에 질의 텍스트 보존을 켠다. principal 은 **`tenant=<tenant>` · `read_tenants`
   하나 · clearance 고정**으로 발급한다 — API 가 보존 정책을 `principal.tenant` 로 찾기 때문이다
   (`api.py:822-835`). 켜는 명령은 **아직 없다** — `query-text` 에는 `status | purge | export | disable`
   만 있고, 켜는 것은 `query_retention` 행 삽입이다(`tests/test_query_text_retention.py:80` 의 INSERT 가
   모양). `notice_shown` 이 비면 principal 과 무관하게 거부되므로 고지 참조를 넣어야 한다. 사람
   principal 은 고지 뒤 옵트인 원칙을 지킨다. 에이전트의 질문에도 사람이 준 문장이 실릴 수 있으니
   보존 기간은 짧게(권고 30일).
3. 첫 주에 `nexus.cli feedback --tenant <tenant>` · `evidence-share` · `doc-age` 를 한 번씩 돌려
   **분모가 0 이 아닌지** 본다. 0 이면 코퍼스 문제가 아니라 배선 문제다.

---

## 9. 프로젝트가 끝났을 때

- 검색에서 내리되 지우지 않는다: `nexus.cli doc --help`(hide/restore), `supersede`/`unsupersede`.
- 보존 텍스트는 `query-text disable <tenant>` — 저장 텍스트와 옵트인 행을 **함께** 지우며 되돌릴
  수 없다.
- 재적재 컨테이너와 `/code-src` 마운트가 그 프로젝트를 가리키고 있으면 env 를 비우고 `up -d`.
  2026-11-02 현재 `/code-src` 가 그 상태다.

---

## 부록 — 2026-11-02 라이브 배선 한 장

| 항목 | 값 |
|---|---|
| 임베딩 세대 | KURE-v1 · `embedding_1024` · 사이드카(`NEXUS_EMBEDDING_BACKEND=sidecar`) |
| 테넌트 | `default`(제품 정책 · khala 자기 문서) · `design_docs` · `picasso`(주기 재적재) |
| `/ingest-src` | picasso `docs/` |
| `/code-src` | 종료된 프로젝트의 플랫폼 코드 |
| Slack 봇 | `NEXUS_SLACK_READ_TENANTS` 의 테넌트만, clearance 상한 PUBLIC |

이 표는 적재 시점의 사실이다. 바뀌면 이 표가 먼저 거짓말을 시작하므로, 바꾼 사람이 고친다.
