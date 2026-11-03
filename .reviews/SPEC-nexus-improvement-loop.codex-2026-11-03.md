# Codex review of SPEC-nexus-improvement-loop (2nd draft)

- Reviewer: OpenAI Codex CLI 0.163.0, model gpt-6.1-sol, reasoning effort high, read-only sandbox, 2026-11-03.
- Input: the 2nd draft at commit 1a3f19e plus the Arbiter sidecar; Docker and the database were not reachable.
- Verdict: do not approve; approve after five fixes and after moving release recording past the first closure.
- The 3rd draft of the SPEC records in its section 0 which claims were re-verified against the code.

---

소스만 검토했습니다. “최근 7일 3행”, 라이브 허용 principal, 실제 컨테이너의 `--reload` 실행 여부는 독립 검증하지 못했습니다. 이는 저장소의 과거 조사 기록입니다. 특히 그 조사도 실행 중 command와 reload 동작은 미검증으로 남깁니다(`research/2026-11-02-llmops-khala-evaluation.md:164`). 아래에서 **spec 오류**와 **저장소 자체 결함**을 구분합니다.

1. **21개 중 핵심 원인이 남은 것은 I-001·I-003·I-007·I-009·I-011·I-018입니다.**

   `accepted`는 처분 수용이며 해결 증거는 아닙니다. 실제 수용 목록은 `.reviews/dispositions-SPEC-nexus-improvement-loop.json:2`부터 있습니다.

   | issue | 판정 | 2차 draft 검증 결과 |
   |---|---|---|
   | I-001 | 부분 잔존 | HTTP로 유입을 한정했지만 성공 판정은 tenant의 전체 `search_log` 행 수입니다. CLI·A2A 행도 같은 표에 들어가므로 보존 질문 없이 통과할 수 있습니다. MCP 판단도 틀립니다. |
   | I-002 | 해소 | 과거 실패 행과 텍스트를 연결한다는 요구를 버리고 현재 질문 replay로 바꿨습니다. 다만 replay의 입력·출력 문제는 아래 새 결함입니다. |
   | I-003 | 잔존 | §3.7의 replay 실패, 하니스 통과, A/B 집계가 동일 실행 조건으로 연결되지 않습니다. 각각 존재한다는 사실만 증명합니다. |
   | I-004 | 해소 | 답변 본문과의 조인을 인정했습니다. 실제 PK도 `(tenant, answer_key)`입니다(`nexus/migrations/036_answer_text_retention.sql:19`). |
   | I-005 | 해소 | `from_user_query`는 실제 허용값입니다(`nexus/scripts/ko_eval_labels.py:47`). 다만 모든 후보에 그 값을 붙이는 별도 오류가 생겼습니다. |
   | I-006 | 해소 | 공개 검색 팩에 운영 라벨을 섞는 문제는 별도 파일과 corpus binding으로 해결했습니다. 새 파일을 실행하는 manifest는 여전히 빠져 있습니다. |
   | I-007 | 부분 잔존 | `corpus_version` 변경을 추가했지만 “라벨 확정 → 누락 문서 적재” 순서는 기존 저술 관문과 충돌합니다. 관문은 이미 DB에 있는 gold 본문을 요구합니다(`nexus/scripts/label_authoring_check.py:117`). |
   | I-008 | 해소 | 사람 문장이 포함될 수 있음을 인정하고 notice를 필수화했습니다. 실제 gate도 principal과 무관하게 notice 부재를 거부합니다(`nexus/nexus/search/query_retention.py:81`). |
   | I-009 | 부분 잔존 | 컨테이너 실행은 환경 불일치를 줄이지만 실행 중 API와 같은 상태임을 보장하지 않습니다. 수동 기록 시각을 배포 경계로 읽는 오류도 남았습니다. |
   | I-010 | 해소 | 버전의 누락 가능성을 명시했습니다. 실제 구현도 프로세스당 한 번 소스를 읽으며 모듈 이름까지 해시에 넣습니다(`nexus/nexus/llm/prompt_version.py:91`, `:110`). |
   | I-011 | 잔존 | 금지 SQL의 검사 범위만 좁혔습니다. 텍스트에서 해시를 재계산하거나 중간 view·애플리케이션을 거치는 연결은 이 검사로 막지 못합니다. |
   | I-012 | 해소 | 표본 부족을 NULL로 표현하는 설계를 제거했습니다. |
   | I-013 | 해소 | 작은 표본에서도 분자·분모를 보이며 closure에 각 10건을 요구하지 않습니다. |
   | I-014 | 해소 | 기존 `v_search_health`를 변경하지 않습니다. 현재 view의 비율 열은 그대로입니다(`nexus/init.sql:480`). |
   | I-015 | 해소 | 승인 절차와 demand-pull의 ADR 인용을 분리했습니다. 다만 문턱의 근거는 여전히 없습니다. |
   | I-016 | 해소 | “U1 → 2주 판정 → 나머지”가 명시됐습니다(`specs/SPEC-nexus-improvement-loop.md:133`). |
   | I-017 | 해소 | 답변 하니스와 backend를 지정했습니다. 실행 대상 선택과 baseline 보존은 별도 새 결함입니다. |
   | I-018 | 잔존 | 파일 만료는 명령 재실행 때만 일어납니다. 실행하지 않으면 무기한 남으며, export 원본·하니스 산출물에는 그 정리조차 적용되지 않습니다. |
   | I-019 | 해소 | 외부 리포 편집을 전제로 옮기고 배포 절차 이관을 제외했습니다. `index_generation_events`와 release의 의미도 실제로 다릅니다(`nexus/nexus/index/generation.py:77`). |
   | I-020 | 해소 | `resolve_tenant` 자체의 설명은 정확합니다. CLI override가 우선하고 둘 다 없을 때만 거부합니다(`nexus/scripts/ko_eval_corpus_reach.py:92`). |
   | I-021 | 해소 | 공통 확인 날짜·드리프트 고지와 주요 스크립트 경로를 보정했습니다. |

   잔존 이슈의 중요한 근거는 다음과 같습니다. I-001의 `search_log`는 답변 전용 표가 아니라 모든 retrieval 경로의 표이고(`nexus/init.sql:443`), CLI도 실제 INSERT를 수행합니다(`nexus/nexus/cli.py:400`). I-009에서는 수동 명령 **이전**에 새 버전 요청이 정상 처리될 수 있으므로, “첫 행이 `released_at`보다 앞이면 기록 누락”이라는 판정은 성립하지 않습니다(`specs/SPEC-nexus-improvement-loop.md:223`). I-018에서는 기존 DB purge가 스케줄러에 연결된 것과 달리(`nexus/nexus/search/purge_schedule.py:87`), 제안한 파일 삭제는 명령 실행에만 의존합니다.

2. **새 결함은 다음과 같습니다.**

   1. **[spec 오류] “어느 둘도 조인되지 않는다”는 주장을 다시 도입했습니다.**  
      `retention_key`가 다르다는 사실은 평문에서 `sha256(query_text)`를 재계산하는 것을 막지 못합니다. `search_log.query_sha256`는 정확히 그 값입니다(`nexus/nexus/search/query_retention.py:29`, `nexus/nexus/search/signals.py:42`). 저장소는 이미 이 오류를 migration 023에서 설명하고 감사 행의 해시 쓰기를 중단했습니다(`nexus/migrations/023_audit_query_hash_stop_writing.sql:4`). 따라서 §2.3·§3.2는 “직접 공유하는 키를 두지 않는다” 정도로 낮춰야 합니다. 새로운 감사 행에서 principal 연결을 끊은 조치는 인정해야 하며, 현재 모든 요청이 principal까지 연결된다고 확대해서도 안 됩니다. SQL grep을 프라이버시 보증으로 삼아서는 안 됩니다.

   2. **[누락된 불변식] `read_tenants=T`만으로 U1의 보존 tenant가 T가 되지 않습니다.**  
      API는 실제 읽기 범위를 별도로 계산하면서 기록·보존용 `req.tenant`는 `principal.tenant`로 설정합니다(`nexus/nexus/api.py:824`, `:835`, `:954`). U1은 `read_tenants`만 지정합니다. 예컨대 `principal.tenant=default`, `read_tenants=(T,)`이면 T를 검색하면서 default의 보존 정책을 확인합니다. 첫 실험에서는 **`principal.tenant=T`, 읽기 범위도 T 하나, clearance도 고정**해야 합니다. U4에도 clearance와 읽기 범위가 필요합니다. `corpus_version`은 tenant 전체가 아니라 호출자가 읽을 수 있는 active 문서의 해시이기 때문입니다(`nexus/nexus/search/versions.py:68`, `:87`).

   3. **[저장소 결함을 spec이 놓침] export는 원문과 재작성문을 구분하지 않습니다.**  
      저장 경로는 `kind='user'/'rewritten'`를 구분하지만(`nexus/nexus/search/signals.py:486`), export SELECT에는 `kind`도 필터도 없습니다(`nexus/nexus/cli.py:1707`). 만료 조건도 없습니다. 현재 명령을 그대로 쓰면 재작성문을 실제 질문으로 승격하거나 purge가 늦어진 만료 텍스트를 가져옵니다. 기존 결함이며, 이 spec이 export를 핵심 입력으로 채택하는 이상 먼저 고쳐야 합니다.

   4. **[spec 오류] 제시한 replay는 운영 요청의 replay가 아닙니다.**  
      CLI는 clearance를 `INTERNAL`로 고정하고(`nexus/nexus/cli.py:333`), HTTP의 history 재작성·복수 채널·검색 글·문서 타입 제외 같은 입력을 재현하지 않습니다(`nexus/nexus/api.py:859`, `:874`, `:895`). CLI 화면에는 hit 수가 나오지만 `degraded`는 출력하지 않습니다(`nexus/nexus/cli.py:352`). 따라서 별도 명령 계약 없이 `degraded` 후보를 기계적으로 뽑을 수 없습니다. 또한 “어제 기권이 오늘 없어졌으면 corpus가 바뀐 것”이라는 §3.2의 단정도 틀립니다. vector 경로 장애 복구만으로 결과가 달라질 수 있습니다(`nexus/nexus/search/hybrid.py:371`). 첫 실험을 single-turn·고정 옵션으로 제한하고 이를 **현재 조건의 재검색**이라고 명시하는 편이 정확합니다.

   5. **[작동 불가] 새 라벨 파일만으로 답변 하니스를 실행할 수 없습니다.**  
      러너는 별도 manifest를 열어 gold 존재와 제목을 확인합니다(`nexus/scripts/ko_eval_answer_run.py:248`, `:259`). 새 tenant의 manifest 생성·갱신 절차가 없습니다. 이 러너는 설명에 등장하는 `resolve_tenant`도 호출하지 않고, `--tenant` 기본값과 서명 tenant를 직접 대조합니다(`:254`, `:500`). `--limit`는 특정 qid 선택이 아니라 answerable 목록의 **앞 N건**입니다(`:260`). 새 운영 라벨이 뒤에 있으면 3회 실행해도 그 라벨을 검사하지 않습니다. 입력 명령, manifest, 대상 qid, before/after 산출물 보존을 명시해야 합니다.

   6. **[spec 오류] 하니스 실패를 `from_user_query`로 재분류하면 provenance가 거짓이 됩니다.**  
      §3.2는 세 유입원을 합친 뒤 후보 provenance를 일괄 지정합니다. 기존 하니스 라벨에는 `authored_from_doc`가 실제로 있습니다(`nexus/tests/eval/ko/labels.yaml:37`). 후보는 원래 provenance를 보존해야 하며, 하니스 실패 라벨을 큐에 넣었다는 이유로 “실제 트래픽 라벨 1건”을 충족해서는 안 됩니다.

   7. **[누락된 보존 경계] “본문 대신 해시만 커밋”으로 공개 안전성이 보장되지 않습니다.**  
      라벨에는 실제 질문, `must_contain`, gold 경로, rationale이 들어갑니다. 더 직접적으로 하니스는 기본적으로 라벨 옆에 답변 본문 리포트를 씁니다(`nexus/scripts/ko_eval_answer_run.py:76`, `:225`, `:385`). 새 경로 `tests/eval/<tenant>/`는 현재 gitignore 대상인 `tests/eval/local/`와 다릅니다(`.gitignore:20`). 공개 Pack A의 커밋 허용 이유도 “본문이 없어서”가 아니라 **공개 corpus이기 때문**입니다(`nexus/tests/eval/ko/answer-labels.yaml:3`). 실질문·답변·원본 export는 local에 유지하고, 공개 라벨은 별도 공개 가능성 검토를 거쳐야 합니다.

   8. **[관측 의미 불일치] `no_answer_n`은 답변 품질이나 하니스 기권 수가 아닙니다.**  
      `no_answer`는 `len(hits)==0`입니다(`nexus/nexus/search/signals.py:235`). 생성의 `abstained`는 packet snippet 부재이며(`nexus/nexus/llm/answer.py:232`), 하니스에는 문장 기반 기권 판정도 있습니다(`nexus/scripts/ko_eval_answer_quality.py:400`). 엉뚱한 hit로 답한 실패가 고쳐져도 `no_answer_n`은 그대로일 수 있습니다. U5는 retrieval·generation·evidence-only를 구분해야 합니다. API도 이미 evidence-only에 별도 path를 부여합니다(`nexus/nexus/api.py:926`). 또한 `n_citations`와 `degraded`에는 정당한 미측정 NULL이 있으므로, 측정된 행 수 없이 합계만 보여 주면 비교 대상이 불분명합니다(`nexus/nexus/search/signals.py:94`, `:148`).

   9. **[저장소 결함] 두 기존 관문을 실제보다 강하게 믿습니다.**  
      첫째, `purge_pointers()`는 존재하지만 production 호출 경로가 없고 purge 스케줄러도 이를 호출하지 않습니다(`nexus/nexus/feedback/store.py:222`, `nexus/nexus/search/purge_schedule.py:87`). “90일 뒤 NULL”은 현재 실행 보장이 아닙니다. 둘째, `label_authoring_check.py`는 `ko_eval_labels.check`를 호출하지 않으며, 대조군이 gold여서 검사를 건너뛰어도 최종적으로 0을 반환할 수 있습니다(`nexus/scripts/label_authoring_check.py:36`, `:122`, `:132`, `:138`). 기존 결함을 별도로 수정하고, spec은 저술 검사와 서명·스키마 검사를 구분해야 합니다.

   10. **[§5의 판별력 부족] 성공 사례 외에 잘못된 비교를 통과시키는 검사가 필요합니다.**  
       U1의 “CLI로 같은 질문 → 행 0”은 앞선 HTTP 저장 행과 신규 쓰기를 구분하지 못하므로 고유 질문 또는 행 수·`seen_count` 변화로 검사해야 합니다. U2는 입력의 `first_seen` 수정 대신 clock을 진행시켜 만료·재생성 방지를 검사해야 합니다. U3는 대상 qid가 실제 실행됐는지 검사해야 합니다. U4의 “호스트면 fingerprint가 다름”은 환경에 따라 참·거짓이 달라지므로 위치가 아닌 **API가 관측한 값과의 불일치**를 검사해야 합니다(`nexus/nexus/search/versions.py:49`). U5는 표시 경계 외에도 다른 path·clearance·빈 버전·NULL 측정값이 섞인 fixture로 정확한 그룹별 개수를 검증해야 합니다.

3. **§3.7은 현재 형태로는 loop closure를 증명하지 못합니다.**

   가장 약한 연결은 **수정 후 하니스 통과와 라이브 B 집계 사이**입니다. CLI `--no-answer`는 `AnswerResult`를 만들지 않아 세 버전 값이 비어 있는 행을 기록합니다(`nexus/nexus/cli.py:362`, `nexus/nexus/search/signals.py:240`, `:269`). 답변 하니스는 `search_log`에 기록하지 않으며 그 분리를 명시합니다(`nexus/scripts/ko_eval_answer_run.py:481`). 따라서 Q가 replay에서 실패하고 B 하니스에서 통과해도, U5의 A/B 행은 전혀 다른 질문들로 구성될 수 있습니다. §1의 “같은 질문군”도 현재 그룹 키만으로는 성립하지 않습니다.

   더 싼 증명은 한 질문의 보호된 실행 기록입니다. 동일한 Q와 고정된 tenant·clearance·옵션으로 **변경 전 실제 API 응답**, 사람이 확정한 요구, **변경 후 동일 조건의 3회 결과**를 보존합니다. 각 기록에 세 버전 값, commit, provider/model, 라벨 revision을 붙입니다. API 응답은 이미 세 버전 값을 제공합니다(`nexus/nexus/api.py:1022`, `:1031`). 저빈도 전용 tenant에서는 통제된 호출 전후 그룹의 `n` 증가까지 확인하면 기록 연결도 검증할 수 있습니다.

   `release_events` 없이도 이 한 번의 사례와 집계 배선을 검증할 수 있습니다. 공개 `ENGINEERING_LOG`에는 qid·변경·결과만 남기고 원문은 보호된 산출물에 둡니다. 집계는 운영 관측이고, 동일 질문의 전후 비교가 개선 증거입니다. 또한 §3.7에서 빠진 `search_fingerprint A→B`도 복원해야 합니다(`specs/SPEC-nexus-improvement-loop.md:252`).

4. **HTTP를 기반으로 시작하고 A2A를 미루는 것은 타당하지만, MCP까지 미루는 것은 소스 오독입니다.**

   MCP는 독립 검색 구현이 아니라 `NEXUS_MCP_TOKEN`을 전달하는 HTTP client이고, `nexus_answer`는 `/search/answer`를 호출합니다(`nexus/nexus/mcp/server.py:33`, `:40`, `:209`). 따라서 승인된 프로젝트 principal 토큰을 사용하면 API에서 principal이 해석되고 같은 보존 gate를 통과합니다. `record_search`의 직접 호출이 없다는 grep 결과로 판단할 일이 아닙니다. MCP 경유와 직접 HTTP를 현재 `search_log`에서 구분할 수 없다는 제한은 있지만, 둘의 보존 계약을 별도로 구현할 필요는 없습니다.

   ADR-0004는 A2A를 end-user-operated agent의 입구로 정하면서도 **실제 소비자가 요청하기 전에는 확장하지 말라**고 함께 적습니다(`adr/ADR-0004-component-architecture-grounding-division.md:151`). 그러므로 새 agent가 이미 A2A를 요구한다는 증거 없이 계약을 넓힐 이유는 없습니다. 실제 A2A `AnswerFn`에 principal이 도달하지 않는 제한도 명확합니다(`nexus/nexus/a2a/server.py:367`).

   저는 **기존 MCP 또는 직접 HTTP 중 agent가 실제 사용하는 경로**를 허용하고, 전용 토큰으로 배선하겠습니다. 동시에 이 리포의 onboarding §8을 수정해야 합니다. 현재 전제 문서는 여전히 CLI `--no-answer`를 권장합니다(`nexus/docs/TENANT_ONBOARDING.md:180`). 이것을 그대로 두면 U1의 유입 설계와 정면으로 충돌합니다.

5. **멈춤 순서는 개선됐지만, “주 10건”은 이 목적에 맞는 문턱이 아닙니다.**

   14일은 관찰 일정으로 쓸 수 있습니다. 그러나 전체 로그 10행은 보존·서로 다른 질문·개선 가능한 실패 중 어느 것도 보장하지 않습니다. 같은 질문 반복이나 CLI 진단만으로도 통과합니다. 반대로 주 3건이어도 실제 실패 하나가 있으면 owner의 “한 번 닫기” 목적은 달성할 수 있습니다. §7.5는 U5의 표본 크기로 문턱을 정당화하지만(`specs/SPEC-nexus-improvement-loop.md:311`), U5는 비율을 내지 않고 closure도 10건을 요구하지 않습니다.

   순서는 다음처럼 바꾸겠습니다.

   1. U1과 즉시 smoke test로 **질문이 실제 보존되는지** 확인합니다.
   2. 14일 동안 유효한 서로 다른 원문 질문 수와 보존 실패를 확인합니다.
   3. 개선 가능한 실제 사례가 하나 생기면 최소 U2로 사람이 전수 검토합니다.
   4. 변경 전에 baseline 응답과 버전별 SQL 결과를 보존합니다.
   5. U3와 수정 후 검증으로 한 사례를 닫습니다.
   6. 반복 사용 필요가 확인되면 U5 CLI와 U4 테이블을 만듭니다.

   현재 U3는 아직 만들지 않은 U4를 corpus 변경 기록으로 요구하므로 의존 순서도 맞지 않습니다(`specs/SPEC-nexus-improvement-loop.md:207`). 처음에는 보호된 실행 기록으로 해결하는 편이 작습니다. 또한 30일 rolling window 밖으로 A가 사라지기 전에 baseline을 남겨야 합니다. 14일 판정은 “10행 미만이면 개발 금지”보다 **무유입·보존 실패·후보 없음 중 무엇인지 판정하는 일정**이어야 합니다.

6. **추가해야 할 것과 빼야 할 것은 다음과 같습니다.**

   해야 할 것:

   1. **실행 조건을 고정해야 합니다.** principal의 귀속 tenant·읽기 범위·clearance가 다르면 다른 corpus을 비교합니다.
   2. **export에 `kind`, 만료 검사를 연결해야 합니다.** 재작성문과 만료 원문을 실제 트래픽 라벨로 오인하지 않아야 합니다.
   3. **누락 문서 사례의 순서를 명시해야 합니다.** 요구 확정과 live corpus binding을 분리하지 않으면 적재 전에 저술 관문을 통과할 수 없습니다.
   4. **manifest와 qid 선택·고유 실행 tag를 명시해야 합니다.** 대상 미실행과 3회 리포트 덮어쓰기를 막아야 합니다.
   5. **공개 라벨과 보호된 원문·리포트의 경계를 정해야 합니다.** 해시 결속은 데이터 공개 허가가 아닙니다.
   6. **포인터 purge와 라벨 관문의 기존 결함을 처리해야 합니다.** 설계가 의존하는 안전장치가 실제로 작동해야 합니다.
   7. **변경 전후 provider/model과 실패 판정을 기록해야 합니다.** 모델은 env로 바뀌지만 세 버전 값에는 포함되지 않습니다(`nexus/nexus/providers/llm.py:352`).

   하지 말아야 할 것:

   1. **MCP에 별도 principal 전달 기능을 만들지 않아야 합니다.** 이미 HTTP 토큰 전달로 해결됩니다.
   2. **모든 후보 provenance를 바꾸지 않아야 합니다.** 유입 경로와 원래 라벨의 출처는 다릅니다.
   3. **`degraded`를 곧바로 품질 수정 라벨로 승격하지 않아야 합니다.** 일시적 장애 복구는 prompt·검색 설정·corpus 변경과 별개입니다.
   4. **첫 closure 전에 release 테이블과 PR 본문 해시 대조를 필수화하지 않아야 합니다.** 실행 증거보다 관리 절차를 먼저 늘립니다.
   5. **A/B 집계의 나란한 존재를 품질 향상으로 읽지 않아야 합니다.** 동일 질문과 실행 조건을 통제하지 못합니다.

7. **전체 판정은 do not approve입니다.** 방향과 범위 축소는 적절하고 21개 지적 중 다수도 실제로 해결했습니다. 그러나 현재 완료 조건은 서로 연결되지 않은 증거로 충족될 수 있으며, 가장 흔한 corpus 누락 사례는 라벨 승격 순서에서 막힙니다. 보존 가능한 principal·tenant 배선, 원문 export, 실행 가능한 라벨/manifest 절차, 보호된 산출물 수명, 동일 조건의 전후 증명을 먼저 고쳐야 합니다. 이 다섯 가지를 반영하고 U4를 첫 closure 이후로 줄인 판이라면 승인할 수 있습니다.