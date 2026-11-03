---
id: SPEC-nexus-improvement-loop
type: spec
title: Improvement loop — a production question becomes a label, a change becomes
  a version, and the two halves are compared by version
status: in_review
date: '2026-11-02T16:01:49Z'
linked_adrs:
- ADR-0002
- ADR-0003
- ADR-0004
- ADR-0006
tags:
- nexus
- evaluation
- observability
- llmops
---

# Improvement loop — a production question becomes a label, a change becomes a version, and the two halves are compared by version

> **인용 표기.** 파일 경로와 줄 번호는 전부 **2026-11-02~03 확인**이고, 파일 이동·개명으로 드리프트할
> 수 있다. 줄 번호가 안 맞으면 그 줄이 아니라 그 심볼을 찾아라.
>
> **판.** 4판이다. 1판 → Arbiter 비평 1차 21건(사이드카는 커밋 `1a3f19e` 의
> `.reviews/SPEC-nexus-improvement-loop.md`; 2차 비평이 같은 파일을 덮어썼다) → 2판 → 외부 모델(Codex)
> 검토(`.reviews/SPEC-nexus-improvement-loop.codex-2026-11-03.md`, 「승인 불가」) → 3판 → Arbiter 비평
> 2차 17건(현재 사이드카) → 4판. 3판이 Codex 로 바꾼 것은 §0.1, 4판이 2차 비평으로 바꾼 것은 §0.2.

## 0. 판마다 무엇이 틀렸었나

### 0.1 2판 → 3판 (Codex 검토, 코드로 재확인)

1. **MCP 는 미루지 않아도 됐다.** MCP 서버는 `NEXUS_MCP_TOKEN` 을 넘기는 **HTTP 클라이언트**이고
   `nexus_answer` 는 `/search/answer` 를 부른다(`nexus/nexus/mcp/server.py:33-40,209`). principal 은 API 가
   푼다. 보존된다.
2. **`read_tenants=T` 만으로는 T 의 보존 정책을 보지 않는다.** 기록·보존용 `req.tenant` 는
   **`principal.tenant`** 다(`nexus/nexus/api.py:822-835`).
3. **「어느 둘도 조인되지 않는다」는 과장이었다.** `search_log.query_sha256` 은 평문의 sha256 이다
   (`signals.py:42`). 맞는 말은 「직접 공유하는 키를 두지 않는다」까지다.
4. **CLI 재생은 운영 요청의 재생이 아니다.** clearance INTERNAL 고정(`cli.py:333`), `degraded` 미출력
   (`cli.py:352`), `--no-answer` 행은 세 버전 값이 빈다(`cli.py:362`, `signals.py:240,269`).
5. **답변 하니스는 `search_log` 에 쓰지 않고**(`ko_eval_answer_run.py:481`) 매니페스트를 요구하며
   (`:248,259`) `--limit` 은 앞 N 건이다(`:260`).

### 0.2 3판 → 4판 (Arbiter 비평 2차)

1. **「닫혔다」를 낮췄다.** n=1 은 순환의 재현이 아니라 **경로가 한 번 관통했다**는 것이다(I-015). 재현은
   두 번째 질문이다.
2. **ADR-0002 의 게이트를 구현한다는 주장을 지웠다.** ADR-0002 의 gate ⓐ 는 **이해도 계측**(comprehension
   meter) 게이트이고 관측된 문턱을 요구한다(`adr/ADR-0002-reframe-system-command-debt.md:145,152`). 14일
   판정은 그 게이트가 아니라 **이 SPEC 자신의 멈춤 규칙**이다(I-005).
3. **before 도 3회**다. 전후 표본이 비대칭이면 분산을 개선으로 읽는다(I-002).
4. **코퍼스는 고침 구간에서 움직이지 않아야 한다.** `corpus_version` 은 읽기 범위 안 active 문서의 함수라
   라이브 적재 한 건으로도 ③ 이 깨진다. before 는 고침 **직전**에 재취득하고 구간 중 적재를 멈춘다(I-001).
5. **공급자·모델은 판정 조건에서 뺐다.** 응답에도 `search_log` 에도 모델 id 가 없어 기록은 자기 신고다
   (I-003). 기계 판정은 2026-11-02 평가 제안 1(응답·기록에 모델 id)이 들어온 뒤다.
6. **실행 기록은 두 겹**이다. 원문·답변·스니펫은 `retain_days` 와 함께 만료하고, 해시·버전·개수·판정만 든
   **환원본**은 남는다(I-004 · I-006).
7. **같은 조건의 정의에 요청 옵션과 principal 을 넣었다**(조건 ⑤, I-012). 합성 질문은 표식 접두어로 가른다
   (I-010). `qid` 를 정의했다(I-007). 만료 메타는 서명 밖 사이드카다(I-016). 분류 ③ 에 상한을 두었다(I-017).
8. **U0-c 는 승인 뒤로**(I-013). U0-a·b 만 설계와 무관한 결함이다. 공유 MCP 토큰은 전제에서 금한다(I-014).
9. **`llm_failed` 는 `search_log` 에 있고**(`init.sql:468`), `abstained` · `abstain_reason` 은 API 응답
   필드다(`api.py:977-978`). 2차 비평 I-008 의 「출처 미제시」는 맞고 「없다」는 틀렸다. 생성 실패 판정은
   사람 눈이 아니라 `facts_present` 로 기계화했다(I-009). 「요구를 먼저 적고 문서를 넣는」 순서에는 요구가
   운영 질문에서 유도됐다는 **시각 증거**를 붙였다(I-011).

## 1. Goal

khala 의 답변 품질을 고치는 순환의 **경로를 끝까지 한 번 관통**한다. 조각은 다 있는데 이음매 셋이
끊어져 있다. 운영 질문이 평가 라벨이 되는 경로가 없고, 고침의 전후를 **같은 조건**으로 대 본 기록이
없고, 변경 전후를 버전으로 가른 집계가 없다.

「관통했다」의 정의: **보존된 실제 질문 하나에 대해, 고침 직전 3회와 고침 뒤 3회의 응답이 같은 조건으로
보호된 실행 기록에 남고, 고침이 지목한 버전 값만 다르고, 사람이 확정한 요구가 앞 3회에서 다수 불성립 ·
뒤 3회에서 다수 성립한다.** 두 번째 질문이 독립적으로 같은 경로를 지나면 그때 「재현됐다」고 적는다.
집계(U4)는 운영 관측이고 증명이 아니다.

구현은 승인 뒤다 — critique → disposition → approve 원장 게이트(ADR-0003 §4 · ADR-0004). 14일 판정
(§3.2)은 이 SPEC 의 멈춤 규칙이고 ADR-0002 의 게이트가 아니다.

## 2. What exists

### 2.1 관측

- `search_log`(`nexus/init.sql:446`): `path` · `route` · `tenant` · `read_scope` · `no_answer`(= `len(hits)==0`,
  `signals.py:235`) · **`llm_failed`**(`init.sql:468`) · `n_citations` · `unverified_citations`, migration
  045/047/048 의 `prompt_version` · `corpus_version` · `search_fingerprint` · `degraded`. **API 응답도 세 버전
  값과 `abstained` · `abstain_reason` 을 돌려준다**(`api.py:977-978,1022-1031`).
- `prompt_version` 의 한계 넷(`llm/prompt_version.py:18,30,80-82`). `search_fingerprint` 는 런타임 설정의
  함수(`search/versions.py:34-57`). `corpus_version_of` 는 **읽기 범위 안 active 문서**의 함수
  (`versions.py:60-87`) — 라이브 적재 한 건에 움직인다.
- **LLM 공급자·모델은 응답에도 기록에도 없다.** `NEXUS_LLM_MODEL` env(`providers/llm.py:352`). 평가 제안 1.
- `v_search_health`(`init.sql:480-494`): 7일 · `path, route` · 비율 열. 7일 행 3(전부 CLI).
- **principal 은 저장되지 않는다**(`signals.py:468,486`).

### 2.2 피드백

- `answer_key`(CSPRNG)는 질의·신원과 직접 공유하는 키가 없고, **답변 본문과는 조인된다**
  (`search_answer_text`, migration 036:19). 사유 넷 고정.
- Slack 포인터 90일 NULL 은 설계일 뿐 `purge_pointers()`(`feedback/store.py:222`)를 부르는 곳이 없다.

### 2.3 질의 텍스트 보존

- 게이트 셋(`query_retention.py:76-88`): 허용목록 · `notice_shown` · 행 존재. 켜는 CLI 없음.
- `kind='user'|'rewritten'`(migration 020:32). **`export` 는 `kind` 도 만료도 안 본다**(`cli.py:1707-1709`).
- HTTP 와 MCP 는 보존된다. CLI(`cli.py:398-400`)·A2A(`a2a/server.py:366-371`)는 안 된다.

### 2.4 평가

- 공개 팩 라벨은 **공개 코퍼스라서** 커밋된다(`answer-labels.yaml:3`). 라이브 테넌트는 **Pack B**
  (`scripts/ko_eval_packb.py`): 스냅샷 테넌트 + `tests/eval/local/` 매니페스트, `.gitignore:20`. `extend` ·
  `align`, ⛔ `freeze` 재호출 금지.
- 답변 하니스(`ko_eval_answer_run.py`): 라벨 + 매니페스트(`:248,259`), `corpus.tenant == --tenant`(`:254`),
  `--limit` 앞 N 건(`:260`), 리포트는 라벨 옆(`:76,225,385`), LLM 질의당 1회, `search_log` 에 안 씀(`:481`).
- provenance 닫힌 집합(`ko_eval_labels.py:47`). `label_authoring_check.py` 는 `ko_eval_labels.check` 를
  안 부르고(`:37`) gold 본문이 DB 에 있어야 한다(`:117`). 채점기 `facts_present(must_contain, text)`
  (`ko_eval_answer_quality.py:116`), `attribute_facts`(`:133`).

### 2.5 변경 게이트 · 릴리스

Arbiter 는 SPEC/ADR 만 막는다. 라이브는 `--reload`. `index_generation_events` 는 세대의 사건이다.

## 3. Design

**순서: U0(a·b) → U1 → 14일 판정 → U2(U0-c 포함) → U3(첫 관통) → U4 → U5.**

### 3.1 U0 — 설계와 무관한 리포 결함 둘 (각각 작은 PR, 승인 전 가능)

| # | 결함 | 고침 |
|---|---|---|
| U0-a | `query-text export` 가 `kind` 와 만료를 안 본다 | `--kind user` 기본, `first_seen + retain_days` 지난 행 제외, `--exclude-prefix` (합성 표식, §3.2), 출력에 `kind` · `first_seen` |
| U0-b | `purge_pointers()` 호출처 없음 | `purge_schedule.run_once` 에 연결(평가 제안 17) |

**U0-c(저술 검사가 스키마·서명 검사를 부르게 함)는 U2 의 판정 기준을 바꾸는 이 설계의 조각이라
승인 뒤 U2 안에서 한다**(2차 비평 I-013).

### 3.2 U1 — 유입과 14일 멈춤 규칙

- **principal**: `tenant=T` · `read_tenants=(T,)` · clearance 고정(권고 INTERNAL). **토큰은 에이전트(세션)
  하나에 하나.** 공유 토큰은 principal 을 뭉쳐 U3 의 「같은 조건」을 깨므로 전제에서 금한다(I-014).
- **표면**: 직접 HTTP 또는 MCP. A2A 는 넓히지 않는다(ADR-0004:151).
- `query-text enable <tenant> --principal <p> --retain-days N --notice <ref>` 추가, `--notice` 필수.
  `retain_days` 권고 30. 「프라이버시 비용 없음」이라 하지 않는다.
- **합성 질문 표식**: smoke test 와 U2 재검색은 질문 앞에 고정 접두어 `[khala-synthetic]` 를 붙인다.
  U0-a 의 `--exclude-prefix` 와 후보 생성이 그 행을 뺀다. 보존 행에 출처 칸을 더하지 않는다 —
  principal 을 저장하지 않는 설계와 같은 이유다(I-010).
- **즉시 smoke test**: enable 직후 표식 붙은 고유 질문 하나 → export(`--exclude-prefix` 끄고)에 `kind=user`
  로 보이는지.
- **14일 판정 = 분류**: ① 무유입 → 배선 · CLAUDE.md · 토큰 범위. ② 보존 실패 → `out_of_scope` ·
  `refused_no_notice` 카운터. ③ 후보 없음 → 다음 14일. **③ 이 3회 연속이면 U2 의 세 부류 기준을
  재검토하고, 6회 연속이면 이 SPEC 을 멈추고 소유자에게 돌린다**(I-017). 「주 10건」 문턱은 두지 않는다.
- 그 프로젝트 리포 CLAUDE.md 의 「khala 를 먼저 치라」는 **전제**이고 입구는 MCP/HTTP 토큰이다
  (`TENANT_ONBOARDING.md` §8).

### 3.3 U2 — 선별: 현재 조건의 재검색, 세 부류, 보호된 자리

- 후보는 보존 질문(표식 없는 `kind=user`)을 **같은 principal 토큰 · single-turn · 고정 `top_k` · 고정 route ·
  history 없음**으로 HTTP `/search/answer` 에 다시 보내 만든다. 「현재 조건의 재검색」이라 부른다.
- 부류 셋, 전부 **기계 판정**(I-009):

  | 부류 | 판정(응답 필드) | 보통의 고침 |
  |---|---|---|
  | 검색 실패 | `evidence_snippets` 0건 | 코퍼스 · 검색 설정 |
  | 생성 실패 | 스니펫 ≥1 이고 (`abstained == true` 또는 후보 요구에 대한 `facts_present` 가 다수 거짓) | 프롬프트 · 코퍼스 |
  | 근거 틀림 | 👎 `wrong_evidence`, 또는 `unverified_citations > 0` | 검색 설정 · 랭킹 · supersede |

  `degraded` 만 찍힌 건은 후보가 아니다(`hybrid.py:371`, 일시 장애).
- provenance: 보존 질문 · 스레드에서 채운 👎 → `from_user_query`; 하니스 실패 라벨 → 원래 값 유지, 「실제
  트래픽 라벨」에 세지 않는다.
- **`qid`**: 라벨 파일 `answer-labels.yaml` 의 `id`(기존 `qNNN` 꼴). 후보 단계의 임시 식별자는
  `cand-<retention_key 앞 8자>` 이고, 라벨로 올릴 때 `qid` 를 발급하며 후보 파일에 매핑을 남긴다. `runs/<qid>/`
  와 `--qid`, `ENGINEERING_LOG` 가 이 하나를 쓴다(I-007).
- **자리**: `tests/eval/local/<tenant>/`(이미 `.gitignore`). 후보 · export 원본 · 하니스 리포트 · 실행 기록.
  **만료 메타는 사이드카 `expiry.json`**(파일별 `expires_at`)이고 서명 대상 `answer-labels.yaml` 안에는
  넣지 않는다(I-016). `expires_at ≤ 해당 보존 행의 first_seen + retain_days`(I-006). 만료는 후보 생성 명령과
  `purge_schedule` 두 트리거가 지운다. `query-text disable` 은 **원문을 담은 파일**을 지우고 환원본(§3.4)은
  남긴다.
- **U0-c 를 여기서 한다**: `label_authoring_check.py` 가 `ko_eval_labels.check(..., require_corpus_binding=True)`
  를 먼저 부르고 실패면 0 을 돌려주지 않는다.
- Pack B: T 를 `freeze` 로 스냅샷(매니페스트), 라벨은 `tests/eval/local/<tenant>/answer-labels.yaml` 에
  `corpus.tenant=<스냅샷>` 서명. 더할 때 `extend`, 서명 뒤 `align`.
- **빠진 문서 사례의 순서와 증거**(I-011): 요구는 보존된 원문(또는 👎 답변 본문)에서 **먼저** 뽑아 후보에
  `requirement_from: <cand id>` · `requirement_signed_at` 을 적고 `answerable: false` 로 둔다 → 문서 적재 →
  `extend` → 저술 검사 → `answerable: true`. 적재 시각이 `requirement_signed_at` 뒤여야 한다. 그 순서가
  뒤바뀐 라벨은 「문서에 맞춰 쓴 요구」이고 첫 관통의 질문으로 쓰지 않는다.
- 성공 기준: 서명된 `from_user_query` 라벨 1건 이상.

### 3.4 U3 — 관통: 한 질문의 보호된 실행 기록, 두 겹

`tests/eval/local/<tenant>/runs/<qid>/`:

- **원문 겹**(만료 대상): `before-1..3.json` · `after-1..3.json` — 요청 옵션 전체 · principal 의 `tenant` ·
  clearance · 토큰 이름 · 응답 전체(답변 · `evidence_snippets` · 세 버전 값 · `abstained` · `unverified_citations`).
- **환원본 겹**(남는다): `record.json` — qid · 날짜 · 고침 종류(코퍼스/프롬프트/검색 설정) · PR 또는 적재
  명령 · 전후 세 버전 값 · 전후 `facts_present` 결과 6개 · 요청 옵션 해시 · 응답 해시 6개 · git commit ·
  라벨 revision · 공급자·모델 **자기 신고**(env, 판정에 쓰지 않음). 원문 없음.
- **관통 조건**(기계 판정):
  ① before 3회 중 2회 이상이 U2 의 세 부류 중 하나.
  ② after 3회 중 2회 이상 요구 성립(`facts_present` 다수).
  ③ `record.json` 이 지목한 버전 값만 전후 다르고 나머지 둘은 **before 3회 · after 3회 전부 같다.**
  ⑤ 요청 옵션 해시 · principal `tenant` · clearance · 토큰 이름이 6회 전부 같다(I-012).
  (④ 공급자·모델은 **기록만** 한다 — 평가 제안 1 이 들어오면 조건으로 올린다.)
- **③ 을 지키는 절차**(I-001): before 는 고침 **직전 한 시간 안**에 받는다. 고침 구간(before-1 → after-3)
  동안 T 에 적재·개정·supersede 를 하지 않는다(T 는 수동 적재라 멈출 수 있고, 주기 재적재가 걸려 있으면
  그 컨테이너를 그 구간만 멈춘다). 코퍼스 고침이면 지목 값이 `corpus_version` 이고 그 적재 하나만 한다.
- 하니스는 **회귀 검사**로 따로 돈다: 고침 PR 에 `ko_eval_answer_run.py --qid <qid>`(추가 필요) 3회 실패
  목록 차이, 백엔드 선언(키리스면 지출 0), 실행별 `--out-dir`.
- `ENGINEERING_LOG` 한 줄(공개): qid · 고침 종류 · 지목 값 · 전후 3회 결과. 원문 없음.
- `prompt_version` PR 본문 대조(CI)는 첫 관통 뒤.

### 3.5 U4 — 운영 관측: 버전별 집계 (첫 관통 뒤)

- `v_search_health_by_version` — `tenant, path, prompt_version, search_fingerprint, corpus_version`, 30일.
  열: `n` · `no_answer_n`(검색 비었음) · `llm_failed_n`(`init.sql:468`) · `degraded_n` · `n_citations_measured` ·
  `n_citations_sum` · `unverified_citations_sum` · `first_ts` · `last_ts`. **비율 없음, 억제 없음.**
- 한계를 뷰 주석에 적는다: **생성의 기권(`abstained`)은 `search_log` 에 없어** 이 집계가 못 본다. 생성
  실패의 집계는 라벨 하니스 몫이다.
- `nexus.cli health --by-version --tenant T`, `n<10` 에 `(표본 부족)` 표시. `v_search_health` 는 그대로.

### 3.6 U5 — 릴리스 기록 (두 번째 관통 뒤, 선택)

`release_events` · `release record` 는 2판 그대로이되 첫 관통의 조건이 아니다. `record.json` 이 commit 과
세 값을 들고 있다.

## 4. Non-goals

- 트레이싱 플랫폼 · LLM 심판 · 자동 수정 · 자동 프롬프트 최적화 없음.
- principal 을 `search_log` 에, 출처 칸을 보존 행에 저장하지 않는다. 보존 키와 `query_sha256` 을 직접 공유하는
  키로 만들지 않는다. `answer_key` 에서 질문 · 신원으로 가는 조인을 만들지 않는다.
- 사람 principal 의 보존 기본값 · A2A 보존 계약 · MCP 의 별도 principal 전달 · `v_search_health` 를 바꾸지 않는다.
- 원문 겹을 커밋하지 않는다. 라벨의 공개 승격은 §7-5 의 사람 검토 뒤에만.
- `degraded` 를 후보로 승격하지 않는다. A/B 집계 두 행을 개선으로 읽지 않는다. **n=1 을 「재현」이라 부르지 않는다.**
- ADR-0002 gate ⓐ(이해도 계측)를 이 SPEC 이 구현한다고 주장하지 않는다.

## 5. Test plan

| 유닛 | 테스트 | 깨뜨리기 |
|---|---|---|
| U0-a | `rewritten` 1 + 만료 1 + 표식 1 + 정상 1 → export 정상 1 | 필터 빼면 4 |
| U0-b | 91일 포인터 → `run_once` 뒤 NULL | 안 돌리면 그대로 |
| U1 | 표식 고유 질문 HTTP → export(표식 포함) `kind=user` · `seen_count=1`; 재전송 → `seen_count=2`, 행 수 동일 | `--notice` 없는 enable 거부; CLI 로 다른 고유 질문 → export 에 없음; 공유 토큰 두 세션 → 전제 위반을 런북 검사가 잡음(문서 검사) |
| U2 | 후보 3건의 부류가 응답 필드와 `facts_present` 로 재현 | `degraded` 만 → 0; `expiry.json` 의 `expires_at` 을 지나게 clock 을 옮기면 두 트리거 모두 삭제; `requirement_signed_at` 이 적재 시각보다 **뒤**인 라벨은 저술 검사가 거부; U0-c 뒤 서명 없는 라벨은 0 이 아닌 코드 |
| U3 | fixture 12파일(before×3 · after×3 · record · expiry 등)에서 ①②③⑤ 참 | before 중 2회가 성립이면 ① 거짓; 지목 외 값이 한 회차만 달라도 ③ 거짓; `top_k` 다른 after 하나 → ⑤ 거짓; 원문 겹 만료 뒤 `record.json` 으로 ①②③⑤ 를 **재판정**할 수 있음을 단언 |
| U4 | path · clearance · 빈 버전 · NULL 측정값 섞인 fixture 에서 그룹별 개수 · `n_citations_measured` 정확 | 비율 열 없음(스키마); `n=9` 도 전부 값 |
| 전체 | disposable 테스트 테넌트에서 §3.4 디렉터리를 끝까지 만들고 네 조건을 기계 판정 | — |

## 6. Risks

- **분모 0**: 14일 판정 ① 이면 U2 이하를 시작하지 않는다.
- **사람 문장**: `retain_days` 30 · U0-a · 사이드카 만료 ≤ 보존 만료 · `query-text status` 월 1회.
- **같은 조건 실패**: ③·⑤ 가 거짓이면 기록은 남되 「한 고침」이 아니다. 섞인 비교를 통과시키지 않는다.
- **고침 구간의 적재 정지**가 운영과 충돌할 수 있다. T 가 수동 적재인 첫 프로젝트에서만 이 절차를 쓴다.
- **`prompt_version` 한계 넷**: 프롬프트 고침인데 값이 안 바뀌면 ③ 이 거짓 — 해시 대상을 따로 고친다.
- **Pack B 재서명 비용**: 코퍼스 고침마다 `extend`/`align`.
- **③ 무한 연기**: 상한 3회/6회(§3.2).

## 7. Open decisions (owner)

1. 테넌트 T · principal 이름 · 고정 clearance(권고 INTERNAL) · 에이전트별 토큰 발급 방식.
2. `retain_days`(권고 30) · 고지 문구와 자리.
3. U0-a·b 를 승인 전 별도 PR 로(권고: 먼저). U0-c 는 승인 뒤.
4. 보호 디렉터리 `tests/eval/local/<tenant>/` 와 환원본 `record.json` 의 보존 기간(권고: 무기한).
5. 공개 라벨 승격 기준 — 기본 올리지 않음.
6. U5 를 지을 조건 — 권고: 두 번째 관통 뒤. 「재현됐다」의 선언도 그때.
