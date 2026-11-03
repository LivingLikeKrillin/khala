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

> **인용 표기.** 이 문서의 파일 경로와 줄 번호는 전부 **2026-11-02 확인**이고, 파일 이동·개명으로
> 드리프트할 수 있다. 줄 번호가 안 맞으면 그 줄이 아니라 그 심볼을 찾아라.

## 1. Goal

khala 의 답변 품질을 고치는 순환을 **닫는다**. 조각은 다 있는데 이음매 셋이 끊어져 있다. 운영에서
나온 질문이 평가셋이 되는 경로가 없고, 변경이 라이브에 반영된 시각이 기록되지 않으며, 변경 전후를
같은 질문군에서 나란히 볼 화면이 없다. 2026-11-02 의 평가(`research/2026-11-02-llmops-khala-evaluation.md`)는
이것을 「지었으되 보지 못한다」고 적었고, 이 SPEC 은 그 세 이음매를 잇는 **최소한의 설계**다.

「닫혔다」의 정의는 하나다. **보존된 실제 질문 하나가 재생(replay)에서 기권하고 → 사람이 라벨로
확정하고 → 변경이 세 버전 값 중 하나를 바꾸고 → 그 라벨이 새 버전에서 통과하며 → `search_log` 를
버전으로 가른 두 집계에서 전후가 나란히 읽힌다.** 이 한 가닥이 실제 트래픽으로 한 번 성립하면 닫힌
것이고, 그 전까지는 평가셋으로 도는 시뮬레이션이다(§3.7).

이 SPEC 은 **테넌트에 독립적**이다. 새 프로젝트의 테넌트가 정해지면 §7 의 이름만 채운다. 구현은
승인 뒤다 — critique → disposition → approve 원장 게이트(ADR-0003 §4 · ADR-0004). ADR-0002 의 수요
당김 규율은 이 SPEC 안에서 **U1 뒤의 2주 멈춤 규칙**(§3.1)으로 구현된다. 분모를 만드는 계측을 분모가
없다는 이유로 막으면 영원히 측정할 수 없고, ADR-0002 자신이 `search_log` 를 수요 신호 수집기로
지목한다.

## 2. What exists

### 2.1 관측 — 답마다 세 버전 값이 저장되지만, 각각 한계가 있다

- `search_log`(`nexus/init.sql:446`)에 `path` · `route` · `tenant` · `read_scope` · `no_answer` ·
  `llm_failed` · `n_citations` · `unverified_citations` 가 있고, migration 045/047/048 이
  `prompt_version` · `corpus_version` · `search_fingerprint` · `degraded` 를 더했다. 답 한 건에 한 행이다.
- `prompt_version`(`nexus/nexus/llm/prompt_version.py`)은 프롬프트 조립 모듈 8개 소스의 해시다.
  **모듈 자신이 적어 둔 한계 넷**: 목록의 모듈을 못 읽으면 빈 문자열이라 그 모듈을 고쳐도 값이 안
  바뀐다(`:80-82`); 설정으로 켜고 끄는 보강(정정 확인 · 페어 확장 · 참조 필 · 코드 값)은 이 값으로 못
  본다(`:30`); 8개 모듈이 **읽는** 바깥 도우미의 변경은 해시 밖이다; 그래서 08-29~09-23 의 572행이
  한 값이었다(`:18`). 이 값은 「프롬프트 조립 코드가 바뀌었다」의 **충분조건이지 필요조건이 아니다**.
- `search_fingerprint(config)`(`nexus/nexus/search/versions.py:34-57`)는 `configured_column` + 임베딩
  모델 + 활성 토크나이저 클래스명 + **`search` 설정 절 전체**다. `configured_column` 은 env 가 덮는다.
  따라서 이 값은 **런타임 설정의 함수**이고, 소스만으로 재현되지 않는다 — `.env` 만 바꿔도 갈린다.
- `corpus_version`(`versions.py:60`)은 테넌트의 `(rid, content_hash)` 집합의 해시다. 문서를 더하거나
  고치면 바뀌고, 조각내기·임베딩·검색 설정은 못 본다.
- `v_search_health`(`init.sql:480-494`)는 **7일 창 · `path, route` 그룹**이고 **비율 열**
  (`no_answer_rate` · `graph_empty_rate` · `llm_fail_rate` · `citation_fabrication_rate`)을 갖는다.
  2026-11-02 기준 7일 행 수는 3이다(전부 CLI). 테넌트도 버전도 차원에 없다.
- **principal 은 저장되지 않는다.** `signals.py:468,486` 에서 보존 여부 판단에만 쓰고 버린다
  (`query_retention.py:66`). 이 SPEC 은 그 설계를 바꾸지 않는다.

### 2.2 피드백 — 투표는 답변과는 조인되고, 질문·신원과는 조인되지 않는다

- `answer_offered` / `answer_vote`(migration 024). `answer_key` 는 128비트 CSPRNG 라 **질의 · 신원**
  과 조인할 길이 없다. 👎 사유는 `wrong_evidence` · `not_my_question` · `ignored_format` · `not_found`
  넷으로 고정이다.
- 그러나 **답변 본문과는 조인된다.** migration 036 의 `search_answer_text(tenant, answer_key,
  answer_text, chars)` 가 「투표를 답변에 붙이는 것」을 목적으로 같은 키를 PK 로 쓴다. 그 표의 주석은
  고지가 아직 질문 보존만 말하고 답변 보존은 말하지 않는다고 적는다(OPEN.md 의 사람 몫).
- 질문자에게 돌아가는 경로는 Slack 포인터 `channel_id` · `message_ts` 이고 **90일 뒤 NULL** 이다.
  `nexus.cli feedback --days N --tenant T` 가 그것을 뽑는다. 푸시는 없다.
- 결과: 👎 하나에서 기계가 얻을 수 있는 것은 **사유 · 사람이 본 답변 본문 · 90일짜리 스레드 포인터**
  셋이고, 질문 텍스트는 사람이 스레드를 열어야 나온다. 피드백 경로 자체가 `answer_key` 로 조인하므로
  (`feedback/store.py:145,169,213`) 「조인 금지」는 키 일반이 아니라 **질문 · 신원 쪽으로의 조인**에만
  건다.

### 2.3 질의 텍스트 보존 — 옵트인이고, 켜는 명령이 없고, 표면 넷 중 하나만 보존한다

- `query_retention` 행(테넌트 · `notice_shown` · `retain_days` · `principals` 허용목록)이 있을 때만
  `retain()` 이 텍스트를 남긴다. 게이트는 셋이다(`query_retention.py:76-88`): 허용목록 밖 principal →
  `out_of_scope`; 행은 있는데 `notice_shown` 이 비면 **principal 과 무관하게** `no_notice`; 행이 없으면
  `off`. 재작성문도 같은 표에 `kind='rewritten'` 으로 쌓인다(`signals.py:486-491`).
- 키는 `sha256(tenant‖NUL‖text)` 라 `search_log.query_sha256` 과 다른 값이고 **조인되지 않는다**
  (`query_retention.py:30-39`, 설계 목표).
- CLI `query-text` 는 `status | purge | export | disable` 만 있다. 켜는 것은 SQL INSERT 다
  (`nexus/tests/test_query_text_retention.py:80`). 라이브 허용 principal 은 `slack-bot` 하나다.
- **표면별 보존 가능성**: HTTP API 는 principal 을 넘긴다(`api.py:686,953,1615`). **CLI 는 넘기지
  않는다**(`cli.py:398-400`, 도구 트래픽이 실사용 집합을 오염시킨다는 이유). **A2A 도 넘기지 않는다**
  (`a2a/server.py:366-371`, 「이 표면이 아직 자기를 식별하지 못한다 — 계약을 넓히는 것이 먼저다」).
  MCP 서버(`mcp/server.py`)에 `record_search` 호출이 grep 에 안 잡혀 **보존 여부를 확인하지 못했다**.
  Slack 봇은 HTTP `/search/answer` 를 부른다(`slack/bot.py:271-274`).

### 2.4 평가 — 라벨 · 하니스 · 바닥은 있고, 라이브 테넌트용 라벨 자리도 있다

- 검색 라벨 정본 `nexus/tests/eval/ko/labels.yaml`(revision 2, pack `ko-k8s-2026-08-01`). gold 는
  **팩 상대 경로**다. 검색 하니스 `nexus/scripts/ko_eval_harness.py` 가 프로덕션 청커로 팩을 적재해
  측정하고, CI(`.github/workflows/ci.yml:341`, `tests/test_ko_eval_run_db.py:53-54,147-148`)가
  Recall@10 ≥ 0.76 · MRR@10 ≥ 0.55 를 **그 팩 코퍼스에서** 지킨다. 이 파일은 라이브 테넌트 문서를
  gold 로 받을 수 없다.
- 답변 라벨 `nexus/tests/eval/ko/answer-labels.yaml` 은 `must_contain` 과 **`corpus.tenant` 결속**
  (판정 문서 본문 해시 서명)을 가진다. 러너 `nexus/scripts/ko_eval_corpus_reach.py:78-98` 의
  `resolve_tenant` 는 라벨의 `corpus.tenant` 선언 또는 `--tenant` 를 쓰고, **둘 다 있으면 `--tenant`
  가 이기되 크게 말하며, 둘 다 없을 때만** `UndeclaredCorpus` 다.
- 라벨 provenance 는 **닫힌 집합**이다: `authored_from_doc` · `adjudicated` · `from_user_query`
  (`nexus/scripts/ko_eval_labels.py:47`, 미지 값은 검사가 거부). `from_user_query` 가 「사람이 실제로
  던진 질문에서 온 질의 — 천장을 낮추는 유일한 재료」로 정의돼 있고, `query-text export` 가 그 재료를
  내보내는 명령이다.
- 답변 하니스 `nexus/scripts/ko_eval_answer_run.py` 는 **LLM 을 부른다**(질의당 1회, 기본 40건).
  채점기 `ko_eval_answer_quality.py` 의 `attribute_facts` 가 검색 탓 / 서술 탓을 가르고, 라벨 저술
  검사 `label_authoring_check.py` 가 gold 성립 · 대조군 불성립을 판정한다. 3회 다수결과 실패 목록
  산출은 `khala-answer-quality-harness` 의 규칙이다.
- 라벨 스키마에 `answerable: false` 가 있다. 이 리포의 실측은 **기권의 다수가 근거 미적재**였다 —
  천장은 코퍼스다.

### 2.5 변경 게이트 — 설계에는 있고 프롬프트에는 없다

Arbiter 가 SPEC/ADR 을 막고 해시 원장을 CI 가 재검증한다. 프롬프트 · 검색 설정 · 코퍼스 변경은 PR
리뷰와 CI 바닥만 거친다. 세 버전 값이 바뀌었다는 사실은 **답 행에 찍힐 뿐** 어디에도 기록되지 않는다.

### 2.6 릴리스 — 절차는 메모리에만 있다

라이브 `nexus-app` 은 메인 체크아웃을 `--reload` 로 읽는다. 반영 순서(마이그레이션 → 머지 → ff →
migrate 기록)는 리포 밖 메모리에만 있다. 세대 선언 `index_generation_events`
(`index/generation.py:110-133`)는 **임베딩 세대**의 사건이고 릴리스 사건이 아니다. 미선언이면 경고 후
통과한다(`:127-133`).

## 3. Design

여섯 유닛이다. **순서는 U1 → 2주 판정 → U2 → U3 → U5 → U4** 이고, 2주 판정이 미달이면 U2 이하를
짓지 않는다(§6). 앞 판의 「분모를 먼저, 보는 눈을 그 다음」은 멈춤 규칙과 어긋났으므로 버렸다.

### 3.1 U1 — 유입: 보존이 켜진 HTTP principal 로 들어오게 한다

분모가 0 이면 나머지는 측정 대상이 없다. 유입원은 새 프로젝트를 만드는 **에이전트**다(D5 결정).

- **표면은 HTTP API 다.** 보존이 실제로 되는 유일한 표면이다(§2.3). 에이전트는 bearer 토큰(읽기 전용
  principal, `read_tenants` = 새 테넌트)으로 `/search/answer` 를 부른다. A2A · CLI · MCP 로 들어오는
  질문은 **이 SPEC 의 분모에 들어가지 않는다** — 그 표면의 계약을 넓히는 것은 별도 SPEC 이다.
- `query-text enable <tenant> --principal <p> --retain-days N --notice <ref>` 를 **추가**한다.
  `query_retention` INSERT 의 CLI 포장이고, **`--notice` 는 필수**다 — `retain()` 이 `notice_shown`
  없는 행을 principal 과 무관하게 거부하므로(§2.3) 고지 없이 켜는 길을 만들지 않는다. 에이전트
  principal 의 고지는 그 에이전트를 운용하는 사람에게 간다(그 프로젝트 리포의 CLAUDE.md 에 「이
  principal 의 질문은 N 일 보존된다」 한 줄).
- 에이전트의 질의는 사람이 준 프롬프트에서 파생되므로 **사람의 문장이 실려 올 수 있다.** 그래서
  「프라이버시 비용이 없다」고 하지 않는다. 처방은 짧은 `retain_days`(권고 30), 재작성문 포함 purge
  점검(§6), 사람 principal 은 지금처럼 고지 뒤 옵트인.
- 다른 프로젝트 리포의 CLAUDE.md 에 문구를 넣는 일은 **이 SPEC 의 유닛이 아니라 전제**다. khala CI
  가 검증할 수 없고 담당이 다르다. `TENANT_ONBOARDING.md` §8 이 그 전제를 적는다.
- `v_search_health` 는 **건드리지 않는다.** 비율 열을 가진 뷰에 차원을 더하면 분모 1~2 의 비율이
  그대로 찍힌다. 테넌트 차원은 U5 의 새 뷰에만 있다.
- **2주 판정**: U1 반영 뒤 14일에 그 테넌트의 `search_log` 행이 **주 10건 이상**이면 U2 로 간다.
  미만이면 U2 이하를 **시작하지 않고** 배선(토큰 범위 · CLAUDE.md 가 안 읽힘 · 에이전트가 다른
  표면으로 들어옴)을 먼저 본다. 이것이 ADR-0002 의 수요 당김을 이 SPEC 이 구현하는 자리다.

### 3.2 U2 — 선별: 세 유입원을 한 후보 큐로, 조인이 아니라 재생으로

후보는 **라벨이 아니다**. 사람이 리뷰해 라벨 파일에 들어가기 전까지는 후보다. §2 가 보인 대로
`search_log` 행 ↔ 질문 텍스트 ↔ principal 은 **어느 둘도 조인되지 않으므로**, 후보는 조인으로
만들지 않고 **보존된 텍스트를 다시 물어서** 만든다.

| 유입원 | 어디서 오나 | 후보가 되는 조건 | 텍스트와 답 |
|---|---|---|---|
| 보존 질문 재생 | `query-text export` → 각 질문을 `query --no-answer --tenant T` 로 재생 | 재생 결과가 `n_snippets=0` 또는 `degraded` | 텍스트는 export 에 있다. LLM 호출 없음, 지출 0 |
| 👎 | `nexus.cli feedback` | 사유 `wrong_evidence` · `not_found` | 질문 없음. **답변 본문**(`search_answer_text`)과 포인터 · 사유를 담고, 질문은 사람이 스레드를 열어 채운다(90일 안) |
| 하니스 실패 목록 | 3회 다수결 결과 | `정답문서✗`(시스템 탓)만 | 라벨 자체 |

- 재생은 **그 행이 아니라 그 질문**을 본다. 어제의 기권이 오늘 재생에서 기권하지 않으면 코퍼스가
  바뀐 것이고 후보가 아니다. 그것이 조인을 포기하고 얻는 것이다.
- 후보의 `provenance` 는 **`from_user_query`** 다. 새 값을 만들지 않는다(§2.4). 에이전트가 만든
  질문이라는 사실은 `authored_by: agent` 로 적는다 — 치우침을 숨기지 않고 적는다.
- 후보 파일 `candidates.yaml` 은 **리포 밖** `.local/eval/<tenant>/` 에 둔다(`.gitignore` 에
  `.local/` 추가). 각 후보는 `first_seen` 과 `expires_at = first_seen + retain_days` 를 가지며,
  `nexus.cli feedback --emit-candidates` 와 재생 명령이 돌 때마다 **만료 후보를 지운다**. DB 쪽
  `purge` · 90일 포인터 NULL · `disable` 철회가 파일에는 안 따라오므로 파일이 스스로 만료한다.
  `query-text disable <tenant>` 는 그 테넌트의 후보 파일도 지운다.
- 확정된 라벨은 **새 파일** `nexus/tests/eval/<tenant>/answer-labels.yaml` 에 들어간다.
  `answer-labels.yaml` 의 형식(`must_contain` · `corpus.tenant` 결속)을 그대로 쓰고 `corpus.tenant`
  를 **선언한다**. `labels.yaml`(팩 결속)에는 넣지 않는다. 라이브 테넌트 문서 본문은 리포에 올리지
  않고 **본문 해시만** 결속에 쓴다 — `answer-labels.yaml` revision 1 이 한 방식이다.
- `label_authoring_check.py` 가 후보를 라벨로 올릴 때의 관문이다. 기존 그대로 쓴다.
- ⛔ `answer_key` 에서 **질문 텍스트나 신원으로** 가는 조인을 만들지 않는다. 답변 본문으로의 조인은
  이미 있고 쓴다(§2.2).
- 성공 기준: `nexus/tests/eval/<tenant>/answer-labels.yaml` revision 1 에 `from_user_query` 라벨이
  **1건 이상**, `answerable: false` 라벨이 **0건 이상**(코퍼스 결함은 라벨이 아니라 적재 작업으로 간다).

### 3.3 U3 — 변경: 세 종류의 고침을 각자의 버전 값으로 기록하고 라벨로 확인한다

운영 실패의 다수는 코퍼스 결함이다(§2.4). 그래서 고침은 셋이고 각각 다른 버전 값을 움직인다.

| 고침 | 움직이는 값 | 어디서 재현되나 |
|---|---|---|
| 빠진 문서 적재 · 문서 수정 · supersede | `corpus_version` | 라이브 테넌트에서만(`corpus_version_of` 는 DB 행의 함수) |
| 프롬프트 조립 모듈 변경 | `prompt_version` | 소스에서 재현된다(단 §2.1 의 한계 넷) |
| 검색 설정 · 토크나이저 · 임베딩 컬럼 변경 | `search_fingerprint` | **라이브 설정·env 에서만** |

- **CI 대조는 `prompt_version` 에만** 건다: 8개 모듈을 건드린 PR 은 본문에 전후 값을 적고 CI 가
  재계산해 대조한다. `search_fingerprint` 는 CI 와 라이브가 다른 값을 내므로 **CI 로 대조하지 않는다**
  — 그 값의 경계는 U4 의 `release record` 가 라이브에서 적는다.
- 그 PR 은 **답변 하니스**(`ko_eval_answer_run.py`, 검색 하니스는 프롬프트 변경에 둔감하다)를
  `--limit` 로 해당 라벨 파일에 **3회** 돌려 실패 목록의 차이를 첨부한다. 백엔드는 PR 본문에
  **선언**한다 — 키리스 브리지(`NEXUS_LLM_PROVIDER=claude-code`)면 지출 0, 유료면 사전 허락
  (`dev-runs-must-not-spend`). 점수가 아니라 목록이다. 새로 깨진 라벨이 있으면 머지하지 않는다.
- 코퍼스 고침은 PR 이 아니라 적재 작업이다. 그 경우 「고침」의 기록은 U4 의 `release record` 한 행
  (`corpus_version` 이 바뀐 시각)이고, 확인은 U2 의 재생이다.
- 성공 기준: U2 의 `from_user_query` 라벨이 고침 뒤 하니스 3회에서 통과한다. 통과하지 않으면
  `attribute_facts` 가 검색 탓인지 서술 탓인지 가른다.

### 3.4 U4 — 릴리스: 라이브의 세 버전 값을 사람이 적는다

- `release_events(id, tenant NULL 허용, commit, prompt_version, search_fingerprint, corpus_version,
  generation, released_at, released_by)` 테이블. **새 테이블**이다 — `index_generation_events` 는
  임베딩 세대의 사건이고 릴리스는 다른 사건이다(§7.3 소유자 확인).
- `nexus.cli release record --by <who> [--tenant T]` 가 **컨테이너 안에서** 현재 값을 계산해 한 행
  넣는다. 컨테이너 안이어야 하는 이유는 `search_fingerprint` 가 라이브 env 의 함수이기 때문이다(§2.1).
  코퍼스 고침 뒤에도 같은 명령을 친다.
- **자동화하지 않는다.** 라이브가 `--reload` 라 반영 시각은 사람이 아는 순간이고 그것을 적는 것이
  목적이다. 배포 절차 문서의 이관은 **이 유닛에서 뺐다** — `TEAM_DOGFOOD_DEPLOY.md` 에 「마지막 단계로
  `release record`」 한 줄만 더한다. prod 오버레이(평가 제안 14)는 범위 밖이다.
- 성공 기준: U5 의 집계에서 버전 값이 바뀐 첫 행의 시각이 `release_events.released_at` 뒤에 있다.
  앞에 있으면 기록을 빠뜨린 것이다.

### 3.5 U5 — 전후 분해: 개수만, 억제 없이

- 뷰 `v_search_health_by_version` — `tenant, prompt_version, search_fingerprint, corpus_version`
  그룹, 창 **30일**. 열은 `n` · `no_answer_n` · `llm_failed_n` · `degraded_n` · `n_citations_sum` ·
  `unverified_citations_sum` · `first_ts` · `last_ts`. **비율 열이 없다.** 그러므로 억제할 것도
  없다 — 앞 판의 「n<10 이면 NULL」은 터진 것 · 빈 것 · 억제된 것을 같은 값으로 만들고 분자까지
  가리므로 버렸다. 비율을 내지 않는 D5 규칙은 뷰가 비율 열을 갖지 않는 것으로 지키고, 「분모 10
  전엔 비율을 입에 올리지 않는다」는 **읽는 사람의 규칙**으로 둔다.
- `nexus.cli health --by-version --tenant T` 가 그 뷰를 표로 찍고, `n < 10` 인 행에 `(표본 부족)`
  표시를 붙인다 — 값은 그대로 보이고 표시만 붙는다.
- 성공 기준: U3 의 고침 전후가 두 행으로 나란히 보이고, U2 라벨의 질문이 속한 쪽의 `no_answer_n`
  과 `n` 이 읽힌다.

### 3.6 U6 — 선택: A2A · MCP 표면의 principal 전달

§2.3 의 두 표면이 자기를 식별하면 분모가 넓어진다. **이 SPEC 의 성공 조건이 아니다.** U1 의 2주
판정이 미달이고 원인이 「에이전트가 A2A/MCP 로 들어온다」로 판명되면 그때 별도 SPEC 으로 쓴다.
A2A 쪽 코드 주석이 이미 「계약을 넓히는 것이 먼저다」라고 적어 두었다.

### 3.7 닫힘의 증명 — 한 가닥, 기계가 확인 가능한 조각으로

구현이 끝났다는 증거는 아래 한 줄이고 `ENGINEERING_LOG` 에 남긴다. 앞 판은 「질문 Q 가 `no_answer`
로 기록됨」을 요구했는데 그 조각은 어디서도 확인되지 않는다(§2). 그래서 **확인 가능한 조각만** 남긴다.

> 보존 질문 Q(테넌트 T, `query-text export` YYYY-MM-DD 에 있음)가 재생에서 `n_snippets=0` →
> 후보 → 라벨 qNNN(`tests/eval/T/answer-labels.yaml` revision R, `from_user_query`) → 고침
> (PR #N 또는 적재 YYYY-MM-DD)이 {prompt_version A→B | corpus_version A→B} → `release record`
> YYYY-MM-DD → 하니스 3회에서 qNNN 통과 → `v_search_health_by_version` 에 A 행과 B 행이 각각
> `n` 과 `no_answer_n` 을 가지고 나란함.

이 줄을 **한 번** 적을 수 있으면 루프는 닫힌 것이다. A 행과 B 행의 `n` 이 10 미만이면 그렇다고
적되, 닫힘의 조건으로 삼지 않는다.

## 4. Non-goals

- **트레이싱 플랫폼(Langfuse · Phoenix 등)을 들이지 않는다.** 분모 주 3건에 플랫폼은 관측이 아니라
  비용이다(평가 「하지 말 것 ①」).
- **LLM 심판을 켜지 않는다.** 충분성 심판은 라벨 100~200건 검증 전까지 꺼진 채다(제안 10).
- **자동 수정 · 자동 프롬프트 최적화를 하지 않는다.** 라벨은 사람이 확정하고 변경은 PR 또는 적재다.
- **principal 을 `search_log` 에 저장하지 않는다.** 보존 키와 `query_sha256` 을 조인 가능하게 바꾸지
  않는다. `answer_key` 에서 질문 · 신원으로 가는 조인을 만들지 않는다.
- **사람 principal 의 보존 기본값을 바꾸지 않는다.** 고지 뒤 옵트인은 그대로다.
- **A2A · MCP · CLI 의 보존 계약을 이 SPEC 에서 넓히지 않는다**(U6 은 선택이고 별도 SPEC 이다).
- **`v_search_health` 를 고치지 않는다.** prod 오버레이 · 이미지 빌드 · 자동 배포도 범위 밖이다.

## 5. Test plan

유닛마다 **일부러 깨뜨리는 검사**를 하나씩 둔다(`suspect-the-instrument-first`).

| 유닛 | 테스트 | 깨뜨리기 |
|---|---|---|
| U1 | `query-text enable` 뒤 그 principal 의 HTTP 질의가 `query_text` 에 남는다 | `--notice` 없이 enable → 명령이 거부된다; 허용목록 밖 principal → `out_of_scope` 카운터만 오르고 행 0; CLI 로 같은 질문 → 행 0 |
| U2 | export 10건 재생 → 기권 2건이 후보 파일에, `provenance: from_user_query`, `expires_at` 있음 | 후보의 `first_seen` 을 `retain_days` 전으로 고치고 다시 돌리면 그 후보가 지워진다; 리포 어디에도 `search_answer_text`/`answer_vote` 를 `query_text` 또는 `search_log` 와 조인하는 SQL 이 없음을 **그 두 쌍에 한정한** 검사로 단언 |
| U3 | 프롬프트 모듈 한 글자 변경 → CI 가 본문의 `prompt_version` 불일치로 실패 | 본문을 맞게 고치면 통과; `search_fingerprint` 를 본문에 적어도 CI 는 대조하지 않음을 단언 |
| U4 | 컨테이너에서 `release record` → 그 시각의 `search_log` 행과 세 값이 같다 | 호스트 셸에서 돌리면 `search_fingerprint` 가 다르다는 **경고와 함께 거부** |
| U5 | 뷰에 비율 열이 없음을 스키마로 단언; `n=9` 행도 모든 열이 값이다 | CLI 가 `n<10` 에 표시를 붙이고 `n=10` 에는 안 붙인다 |
| 전체 | §3.7 의 한 가닥을 **disposable 선언 테스트 테넌트**에서 끝까지 | — |

테스트 DB 는 스스로 disposable 을 선언해야 한다(`test-db-must-declare-disposable`).

## 6. Risks

- **분모가 끝내 0 이다.** 가장 큰 위험이고 코드로 못 푼다. U1 의 2주 판정이 미달이면 U2 이하를
  시작하지 않는다. 평가셋으로 도는 루프를 닫힌 것으로 보고하지 않는다.
- **에이전트의 질문에 사람의 문장이 실려 온다.** `retain_days` 30, 재작성문 포함 `purge` 가 도는지
  `query-text status` 로 월 1회 본다(안 도는 purge 는 증상이 없다, `purge_schedule.py:3`). 후보
  파일은 스스로 만료한다(§3.2).
- **에이전트가 만든 질문으로 라벨이 치우친다.** `authored_by: agent` 로 적고 다듬지 않는다.
- **👎 포인터 90일.** 월 1회 `feedback` 규칙(`khala-answer-feedback-loop`)을 전제한다.
- **`prompt_version` 이 너무 자주 바뀌거나, 바뀌어야 할 때 안 바뀐다.** §2.1 의 한계 넷 때문이다.
  30일 창에 버전이 많아 행이 흩어지면 U5 는 그대로 보여 주고(억제 없음), 해시 대상 조정은 **따로**
  제안한다. 바뀌어야 할 때 안 바뀌는 쪽(보강 설정 · 바깥 도우미)은 `search_fingerprint` 가 일부를
  받는다 — 설정 절 전체를 보기 때문이다.
- **`search_fingerprint` 가 PR 없이 갈린다.** `.env` 변경이 그렇다. 그래서 U4 를 라이브에서 사람이
  치게 했고, U3 의 CI 대조에서 그 값을 뺐다.
- **코퍼스 고침이 라벨을 무효화한다.** 문서 본문이 바뀌면 `corpus.tenant` 결속 해시가 어긋나
  재서명이 필요하다. 그것은 결함이 아니라 결속의 목적이다(`answer-labels.yaml` 머리말).

## 7. Open decisions (owner)

1. 새 프로젝트의 테넌트 이름과 principal 이름 — `TENANT_ONBOARDING.md` §0.
2. 에이전트 principal 의 `retain_days` — 권고 30. 고지 문구와 그 자리(그 프로젝트 CLAUDE.md).
3. `release_events` 를 새 테이블로 두는 것 — 권고 그대로. 반대면 `index_generation_events` 를 넓히되
   「세대」와 「릴리스」가 한 표에 섞인다는 비용을 적는다.
4. 후보 파일 위치 `.local/eval/<tenant>/` — 다른 자리를 원하면 여기.
5. 2주 판정의 문턱 **주 10건** — 더 낮추면 U5 의 30일 창에서 전후 각 행이 한 자리 수가 된다.
