---
target: SPEC-nexus-improvement-loop
critiqued_hash: sha256:683442ed10a774e5440898815cf8a33b7a45379bb53f635a556c7bc71b50fb49
critiqued_at: '2026-11-03T06:11:07Z'
issues:
- issue_id: I-001
  category: risky-assumption
  severity: high
  description: 'U1 의 분모가 A2A 표면에서는 구조적으로 0 이다. `nexus/nexus/a2a/server.py:366-371`
    은 `record_search` 에 **principal 을 넘기지 않는다**(주석이 명시: "허용목록에 오를 수 없으므로 A2A 질문은 보존되지
    않는다 — 계약을 넓히는 것이 먼저다"). `retain()` 은 `principal not in allowed` 면 `out_of_scope`
    로 끝난다(`query_retention.py:80-84`). 반면 ADR-0004 §5 는 A2A 를 「end-user-operated agent
    가 khala 에 닿는 입구」로 못박았다. 새 프로젝트의 에이전트가 A2A 로 들어오면 `search_log` 행은 쌓이는데 질의 텍스트는
    한 건도 안 남아, U1 성공 기준(주 10건)은 통과하면서 U2 는 재료가 0 이 된다. SPEC 은 principal 을 싣는 표면이 HTTP(`api.py:686,954,1615`)와
    그것을 토큰 하나로 감싸는 MCP(`mcp/server.py:33-36`, `NEXUS_MCP_TOKEN` ⇒ 테넌트·등급 하나)뿐이라는 사실과
    그 배선 조건을 적지 않았다.'
  status: open
  disposition_reason: null
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: §3.2 표의 둘째 줄(기권·약한 근거)에 **행↔텍스트를 잇는 기제가 없다**. SPEC 자신이 §2.1 에서 「principal
    은 `search_log` 에 저장되지 않는다」, §2.3 에서 보존 키가 `sha256(tenant‖NUL‖text)` 라 `search_log.query_sha256`
    과 「조인되지 않는다」(`query_retention.py:30-39` 가 그것을 설계 목표로 못박음)고 적고도, 후보 조건을 「`search_log.no_answer`·`degraded`
    행 중 보존이 켜진 principal 의 질문」으로 쓴다. 테넌트에 principal 이 하나뿐이어도 (a) 어느 행이 어느 보존 텍스트인지,
    (b) `query-text export` 가 뱉은 질문 중 어느 것이 기권한 질문인지 가릴 수단이 없다. `export` 는 `query_text,
    seen_count, first_seen, last_seen` 만 낸다(`cli.py:1706-1712`). 결과적으로 U2 의 둘째 유입원은
    「기권한 질문」이 아니라 「그 테넌트의 모든 질문」만 줄 수 있다.
  status: open
  disposition_reason: null
- issue_id: I-003
  category: untestable-requirement
  severity: high
  description: §3.6 「닫힘의 증명」 한 가닥이 위 기제 공백 때문에 구성 불가능하다. 그 줄은 「질문 Q(테넌트 T, principal
    P)가 YYYY-MM-DD 에 `no_answer` 로 기록됨」을 요구하는데, 세 조각(질문 텍스트 · principal · 그 특정 행)
    중 어느 둘도 같은 자리에서 확인되지 않는다 — principal 은 저장 안 되고(§4 비목표), 텍스트 키는 조인 불가다. 따라서 이 SPEC
    의 완료 정의 자체가 사람이 기억으로 메우는 서술이 되고, 「루프가 닫혔다」가 반증 불가능한 주장이 된다. 닫힘을 증명하려면 (예) 기권 행에
    보존 키를 같이 찍는 결정이 선행해야 하고, 그 결정은 §2.1·§2.3 의 프라이버시 설계와 정면으로 거래해야 한다 — SPEC 은 그 거래를
    열지도, 거절하지도 않았다.
  status: open
  disposition_reason: null
- issue_id: I-004
  category: unverifiable-claim
  severity: high
  description: §2.2 의 「`answer_key` 는 질의 · 답변 · 신원 **어느 것과도** 조인할 수 없다」는 거짓이다. migration
    036(`036_answer_text_retention.sql:19-29`)이 `search_answer_text(tenant, answer_key,
    answer_text, chars)` 를 PK `(tenant, answer_key)` 로 만들었고, 그 주석이 목적을 「투표를 답변에 붙이는
    것」이라고 적는다. 따라서 §3.2 의 「👎 는 텍스트가 없으므로 포인터와 사유만 담긴 **빈 후보**가 생긴다」도 과소 서술이다 — 질문
    텍스트는 없지만 **사용자가 본 답변 본문**은 꺼낼 수 있고, 그것이 `wrong_evidence` 후보의 가장 값싼 재료다. 2.2 가
    낡은 상태를 전제로 U2 설계가 90일 Slack 왕복에 전부를 걸고 있다.
  status: open
  disposition_reason: null
- issue_id: I-005
  category: undefined
  severity: high
  description: '`provenance: from_production` 은 **없는 값**이고, SPEC 은 같은 문단에서 「`label_authoring_check.py`
    를 기존 그대로 쓴다」고 한다. 라벨 provenance 는 닫힌 집합이다: `PROVENANCE = ("authored_from_doc",
    "adjudicated", "from_user_query")`(`nexus/scripts/ko_eval_labels.py:47`)이고 검사가
    미지 값을 거부한다(같은 파일 227-229). 게다가 그 자리를 위한 용어가 이미 있고 — `from_user_query` 는 주석에 「천장을
    낮추는 유일한 재료」로 정의돼 있으며 `query-text export` 가 사람에게 그 값을 쓰라고 안내한다(`cli.py:1717-1719`)
    — 용어 발명 금지 규칙(정본 `GLOSSARY.md`·`COMMON_TERMS.md`)에도 걸린다. U2 성공 기준(`from_production`
    라벨 1건 이상)은 현재 코드에서 검증 실패로 끝난다.'
  status: open
  disposition_reason: null
- issue_id: I-006
  category: missing-invariant
  severity: high
  description: '운영 라벨이 **어느 라벨 파일에** 들어가는지가 비어 있고, 유일하게 지목된 파일은 그것을 받을 수 없다. `nexus/tests/eval/ko/labels.yaml`
    은 `revision: 2` · `pack: ko-k8s-2026-08-01` 에 묶여 있고 gold 는 **팩 상대 경로**다. CI 바닥(`tests/test_ko_eval_run_db.py:53-54,147-148`,
    Recall@10 ≥ 0.76 · MRR@10 ≥ 0.55)이 그 팩 코퍼스에서 돈다. 그런데 U2 성공 기준은 「첫 라벨 리비전 올림(revision
    3 이상)에 운영 라벨 1건 이상」이다 — 라이브 테넌트 문서를 gold 로 가진 라벨을 이 파일에 넣으면 공개 팩 실행에서 그 라벨은 영원히
    불성립이라 바닥 검사가 빨개진다. §2.4 가 「문서는 라이브 테넌트에서 측정해야 한다」고 적고도 **별도 라벨 파일 · `corpus.tenant`
    선언 · 바닥값 분리**를 설계하지 않았다.'
  status: open
  disposition_reason: null
- issue_id: I-007
  category: risky-assumption
  severity: high
  description: '루프의 전제가 「운영 실패는 프롬프트·검색 변경으로 고쳐진다」인데, 이 리포의 실측은 반대를 말한다 — 천장은 코퍼스이고(기권의
    다수는 근거가 적재돼 있지 않은 경우) 라벨 스키마에는 그래서 `answerable: false` 칸이 있다(`labels.yaml`). U3
    는 `prompt_version` 과 `search_fingerprint` 변경만 다루고, `corpus_version`(migration
    047, `search/versions.py:60`)이 바뀌는 변경 — 즉 「빠진 문서를 적재했다」 — 에 대응하는 유닛이 **없다**. 가장
    흔한 실패 유형이 루프 밖에 있으면 §1 의 「한 가닥」은 드문 경우에만 성립하고, U3 성공 기준(「운영 라벨이 변경 뒤 통과」)은 대개
    통과 불가다.'
  status: open
  disposition_reason: null
- issue_id: I-008
  category: risky-assumption
  severity: high
  description: U1 의 「에이전트의 질문에는 사람의 프라이버시 비용이 없으므로 에이전트 principal 은 **기본 허용**」은 두
    군데서 위험하다. ① 에이전트의 질의는 사람이 준 프롬프트에서 파생되므로 사람의 문장이 그대로 실려 올 수 있고, 재작성문까지 같은 표에 `kind='rewritten'`
    으로 쌓인다(`signals.py:486-491`). ② 코드 게이트와 어긋난다 — `retain()` 은 principal 과 무관하게 `notice_shown`
    이 비면 `no_notice` 로 거부한다(`query_retention.py:82-88`). 즉 「기본 허용」이란 것이 없고 언제나 고지
    참조가 필요한데, SPEC 은 `--notice <ref>` 를 받으면서 동시에 「기본 허용」이라고 적어 **무엇이 고지로 들어가는지**(에이전트에게
    고지한다는 것이 무슨 뜻인지)를 정의하지 않는다.
  status: open
  disposition_reason: null
- issue_id: I-009
  category: risky-assumption
  severity: high
  description: U3 의 CI 대조와 U4 의 `release record` 는 **런타임 설정에 의존하는 값**을 소스에서 재현할 수
    있다고 가정한다. `search_fingerprint(config)`(`search/versions.py:34-57`)는 설정 파일의 `search`
    절 전체 + env 가 덮을 수 있는 `configured_column(cfg)` + 활성 토크나이저 클래스명으로 계산된다. 따라서 (a)
    CI 는 라이브와 다른 설정·env 에서 값을 내므로 PR 본문 대조가 라이브 경계를 보장하지 않고, (b) `.env` 만 바꿔도 PR 없이
    값이 갈리고, (c) 워크트리/셸에서 돈 `release record` 는 컨테이너의 값과 다를 수 있다 — 배포가 메인 체크아웃을 `--reload`
    로 읽는 이 환경에서 이미 알려진 함정이다. 그런데 U4 성공 기준은 불일치를 「기록을 빠뜨린 것」 **한 가지 원인**으로 단정한다. 설정
    환경 불일치·`--reload` 재기동이라는 다른 두 원인을 가릴 방법이 없다.
  status: open
  disposition_reason: null
- issue_id: I-010
  category: unverifiable-claim
  severity: medium
  description: §2.1 의 「`prompt_version` 은 … 코드가 바뀌면 값이 바뀐다」는 모듈 자신이 적어 둔 한계를 지운 과장이다.
    `llm/prompt_version.py` 는 ① 목록의 모듈을 못 읽으면 **빈 문자열**을 쓰고 그 경우 그 모듈을 고쳐도 값이 안 바뀐다(`_module_source`
    주석), ② 설정으로 켜고 끄는 보강(정정 확인 · 페어 확장 · 참조 필 · 코드 값)은 「이 값으로 못 본다」, ③ 8개 모듈이 **읽는**
    바깥 도우미 변경은 해시 밖, ④ 값은 모듈 소스만이 아니라 모듈 **이름**까지 포함해 찍는다(`fingerprint(*ASSEMBLY_MODULES,
    *_assembly_sources())`)고 명시한다. 「8개 소스의 sha256 앞 12자」라는 SPEC 의 서술과 「바뀌면 바뀐다」는 단언을
    그대로 두면, U3 가 버전 불변을 「프롬프트 불변」으로 읽는 오독을 만든다.
  status: open
  disposition_reason: null
- issue_id: I-011
  category: untestable-requirement
  severity: medium
  description: U2 의 깨뜨리기 항목 「`answer_key` 로 조인하는 SQL 이 리포에 없음을 grep 으로 단언」은 구성상 성립하지
    않는다. 피드백 경로 자체가 `answer_key` 로 조인한다 — `feedback/store.py:145`(`answer_offered`
    조회), `:169`(`answer_vote` 삽입), `:213`(`COUNT(DISTINCT v.answer_key)`), 그리고 `search_answer_text`
    가 같은 키로 서 있다. 이 단언은 항상 실패하거나, 실패를 피하려 패턴을 좁히는 순간 아무것도 지키지 않는 검사가 된다. 지켜야 할 불변식은
    「조인이 없다」가 아니라 「**질의 텍스트 또는 신원**에 닿는 조인이 없다」이고, 그것은 grep 이 아니라 스키마 수준 단언(그 키를 가진
    표의 집합을 고정)으로 써야 한다.
  status: open
  disposition_reason: null
- issue_id: I-012
  category: missing-invariant
  severity: medium
  description: 'U5 의 「n<10 이면 나머지를 NULL」은 **터진 것과 빈 것과 억제된 것을 같은 값으로** 만든다. `search_log`
    에는 이미 정당하게 NULL 인 열이 있고(예: 가격 없는 실행의 `cost_usd`, `v_search_health:490-491`), `corpus_version`
    은 「모른다」를 빈 문자열로 적는다. 뷰를 읽는 사람이 NULL 을 보고 「표본 부족」인지 「계측기가 안 돌았다」인지 가릴 칸이 없다. 억제
    사실을 명시하는 열(예: `suppressed boolean` 또는 `n_min_required`)이 없으면 U5 의 테스트(「9→10 경계에서
    NULL 이 값으로 바뀐다」)는 억제 규칙만 확인하고 계측 실패를 못 가린다.'
  status: open
  disposition_reason: null
- issue_id: I-013
  category: missing-invariant
  severity: medium
  description: U5 는 자기 원칙을 스스로 깬다. 「분자와 분모를 따로 내고 비율은 읽는 사람이 낸다」고 선언하면서, n<10 일 때
    **분자까지** NULL 로 가린다 — 가려야 하는 것은 비율이고 분자·분모는 D5 규칙이 금지한 대상이 아니다. 그 결과 (a) 표본이 쌓이는
    중인 그룹에서 아무 자료도 못 읽고, (b) §3.6 의 증명이 「양쪽 각각 n≥10」에만 걸려, 주 10건 분모에서 30일 창 안에 변경
    전후 각 10행을 확보해야 하는 매우 좁은 조건이 유일한 통로가 된다. §6 이 적은 「버전이 10개면 전부 NULL」 위험이 바로 이 설계에서
    나온다.
  status: open
  disposition_reason: null
- issue_id: I-014
  category: missing-invariant
  severity: medium
  description: 'U1 의 「`v_search_health` 에 `tenant` 차원을 더한다」가 U5 의 금지를 되살린다. 그 뷰는 비율
    열을 그대로 갖고 있다 — `no_answer_rate` · `graph_empty_rate` · `llm_fail_rate` · `citation_fabrication_rate`(`nexus/init.sql:480-494`).
    차원을 하나 더하면 그룹이 더 쪼개지고, 7일 창에 행 3건인 현실에서 **분모 1~2 의 비율**이 그대로 찍힌다. SPEC 은 U5 에만
    「분모 10 전엔 비율 없음」을 걸고 U1 이 건드리는 기존 뷰에는 같은 규칙을 걸지 않았다. 또한 구현 제약이 적혀 있지 않다: Postgres
    `CREATE OR REPLACE VIEW` 는 기존 열의 이름·순서를 바꾸거나 중간에 끼울 수 없으므로(끝에 추가만 가능) `tenant`
    를 그룹 키로 넣으려면 DROP/재생성 마이그레이션과 기존 소비자(`nexus health` · schema_health · 테스트) 갱신이
    필요하다.'
  status: open
  disposition_reason: null
- issue_id: I-015
  category: adr-contradiction
  severity: medium
  description: '§1 의 「구현은 승인 뒤다(ADR-0002 의 게이트 절차)」는 ADR 을 잘못 가리킨다. ADR-0002 에는 승인
    절차가 없다 — 거기 있는 게이트는 인지부채 창구를 **관측된 신호**에 묶는 수요 당김 게이트(gate ⓐ)이고, critique → disposition
    → approve 원장 게이트는 ADR-0003 §4 / ADR-0004 가 말하는 Arbiter·specledger 루프다. 더 무거운 쪽은
    내용이다: ADR-0002 의 수요 당김 규율("show the signal")과 그것이 A2A 를 멈춘 전례에 비추면, 7일 3행(전부 CLI)인
    분모 위에 다섯 유닛을 올리는 것이 바로 그 전례의 모양이다. SPEC 은 U1 을 분모 게이트로 두어 이를 다루려 하지만, 어느 ADR 의
    어느 게이트가 발동 조건인지 문서가 틀린 이름을 적고 있어 승인 심사의 기준이 모호해진다.'
  status: open
  disposition_reason: null
- issue_id: I-016
  category: risky-assumption
  severity: medium
  description: 권고 순서가 자기 안전장치보다 앞선다. §6 은 「U1 성공 기준이 2주 뒤에도 미달이면 나머지를 **멈추고** 배선부터
    본다」고 적는데, §3 의 권고 순서는 U1 → **U5** → U2 → U3 → U4 다. 즉 2주 판정이 나오기 전에 U5(뷰 + CLI
    + 마이그레이션)를 짓는다. 「분모를 먼저, 보는 눈을 그 다음」이라는 근거는 타당하나, 멈춤 규칙과 순서 권고가 같은 문서에서 어긋나면 실제로는
    멈출 수 없는 상태가 된다(이미 지은 것을 되돌리는 결정이 되므로). 순서를 「U1 → 2주 판정 → 나머지」로 명시하거나, U5 를 판정
    전 허용 범위(뷰만, CLI 는 뒤)로 쪼개야 한다.
  status: open
  disposition_reason: null
- issue_id: I-017
  category: undefined
  severity: medium
  description: U3 의 「하니스를 3회 돌려 실패 목록의 차이를 첨부한다」가 **어느 하니스인지** 정하지 않았고, 둘 중 하나를 고르면
    요구가 무의미해진다. 검색 하니스(`scripts/ko_eval_harness.py`, Recall@10·MRR@10)는 검색 단계만 재므로
    프롬프트 조립 변경에 **원리적으로 둔감**하다 — 프롬프트를 바꿔도 실패 목록이 그대로일 수 있다. 답변 쪽(`ko_eval_answer_run.py`
    · `ko_eval_answer_quality.py`)을 뜻한다면 LLM 호출 3회분의 **백엔드 선언과 지출**(키리스 브리지 여부, 동시성·타임아웃)과
    소요 시간이 PR 게이트 비용으로 들어가는데 SPEC 에 한 줄도 없다. 「점수가 아니라 목록」이라는 규칙만으로는 실행 가능한 요구가 아니다.
  status: open
  disposition_reason: null
- issue_id: I-018
  category: missing-invariant
  severity: medium
  description: 후보 파일에 **만료와 자리**가 없다. §7.4 가 위치를 미결로 남긴 상태에서 U2 의 산출물(`labels.candidates.yaml`)은
    내부 질문 텍스트를 담고, 거기에는 DB 쪽에 걸린 보호가 하나도 따라붙지 않는다 — `retain_days` 만료(`query_retention.purge`
    는 `first_seen` 기준, 고아 행도 만료 처리)도, 👎 포인터의 90일 NULL 도, `disable` 철회도 파일에는 적용되지 않는다.
    §6 은 보존 텍스트의 보안을 위험으로 적으면서 처방을 DB 쪽 `purge` 점검에만 두었다. 또한 U2 가 `search_answer_text`(만료
    없음, 고지가 답변 보존을 아직 언급하지 않아 소유자 몫으로 열려 있음 — `036_answer_text_retention.sql:15-17`)를
    재료로 쓰게 되면 §4 의 「사람 principal 의 보존 기본값을 바꾸지 않는다」와 실질적으로 어긋난다.
  status: open
  disposition_reason: null
- issue_id: I-019
  category: scope-creep
  severity: medium
  description: U1·U4 가 이 리포가 검증할 수 없는 일을 포함한다. U1 은 **다른 프로젝트 리포의 CLAUDE.md** 에 문구를
    넣는 것을 유닛의 일부로 두는데, 그 파일은 khala CI 밖이고 담당이 다르다(성공 기준 미달의 첫 원인으로 SPEC 이 지목하는 「CLAUDE.md
    가 안 읽힘」을 이 SPEC 은 관측할 수단이 없다). U4 는 새 표 + `release record` 를 넘어 `TEAM_DOGFOOD_DEPLOY.md`
    의 배포 절차 이관까지 포함하고, 그 표가 기존 `index_generation_events`(`index/generation.py:110-133`)와
    겹치는지는 §7.3 에서 아직 미결이다. 미결 결정에 의존하는 산출물이 같은 유닛 안에 있다.
  status: open
  disposition_reason: null
- issue_id: I-020
  category: unverifiable-claim
  severity: low
  description: §2.4 의 「그 경로(`ko_eval_corpus_reach.resolve_tenant`)는 라벨이 `corpus.tenant`
    를 선언하지 않으면 **돌지 않는다**」는 정확하지 않다. 그 함수는 `--tenant` 가 주어지면 선언이 없어도 그 값으로 돌고(선언과
    다르면 경고만 하고 CLI 가 이긴다), `UndeclaredCorpus` 는 **둘 다 없을 때만** 난다(`nexus/scripts/ko_eval_corpus_reach.py:78-98`).
    라이브 테넌트 측정의 안전장치를 실제보다 강하게 적어 두면, 라벨에 선언을 넣지 않고 `--tenant` 로만 돌리는 — 2026-09-05
    사고와 같은 모양의 — 경로가 열려 있다는 사실이 가려진다.
  status: open
  disposition_reason: null
- issue_id: I-021
  category: unverifiable-claim
  severity: low
  description: 인용 좌표가 섞여 있고 드리프트 고지가 없다. 스크립트는 `nexus/scripts/` 아래인데 SPEC 은 `scripts/ko_eval_harness.py`
    · `scripts/label_authoring_check.py` 로 적고, 라벨은 `nexus/tests/eval/ko/labels.yaml`
    로 바르게 적는다. 또 `search_log`(`nexus/init.sql:446`)와 `v_search_health`(실제 `init.sql:480`)처럼
    줄 번호를 든 인용에 「그날의 체크아웃 기준」이라는 말은 있으나, ADR-0002 가 I-004 처분으로 채택한 **시점 인용 표기**(「2026-11-02
    확인, 파일 이동·개명으로 드리프트할 수 있다」)를 각 셀에 달지 않았다. 다음 독자가 줄 번호로 확인하려다 틀린 자리를 읽는다.
  status: open
  disposition_reason: null
approved_by: null
approved_at: null
---

