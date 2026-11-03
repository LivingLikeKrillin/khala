---
target: SPEC-nexus-improvement-loop
critiqued_hash: sha256:a2520645fad1c71c09dcb2894fc7a6f1de0667e0be5edc0754a404e41c1607bb
critiqued_at: '2026-11-03T08:22:40Z'
issues:
- issue_id: I-001
  category: missing-invariant
  severity: high
  description: §3.4 닫힘 조건 ③ 은 `fix.md` 가 지목한 버전 값만 다르고 나머지 둘은 같아야 한다고 요구하지만, `corpus_version_of`
    는 읽기 범위 안 active 문서 (rid, content_hash) 의 함수(§2.1)이고 T 는 에이전트 트래픽이 계속 들어오는 라이브
    테넌트다. before 는 과거 트래픽 시점, after 는 고침 뒤이므로 그 사이에 문서 한 건만 적재·개정·supersede 되어도 프롬프트
    전용 고침에서 `corpus_version` 이 함께 움직여 ③ 이 거짓이 된다. SPEC 에 before~after 구간의 코퍼스 동결(또는
    before 를 스냅샷 테넌트에서 재취득) 불변식이 없어, 가장 흔한 경우에 닫힘이 구조적으로 불가능하다.
  status: open
  disposition_reason: null
- issue_id: I-002
  category: risky-assumption
  severity: high
  description: before 는 1회, after 는 3회 다수결(§3.4 ②)이라 표본이 비대칭이다. 답변 하니스가 같은 라벨에서 회차마다
    흔들린다는 것은 이 리포가 이미 관측한 사실인데, before 단일 실행이 우연히 실패한 회차였다면 고침 없이도 ②가 참이 된다. before
    도 같은 조건 3회(또는 before 실패의 재현성 요구)를 두지 않으면 「닫힘」은 개선이 아니라 분산을 측정한 기록일 수 있다.
  status: open
  disposition_reason: null
- issue_id: I-003
  category: untestable-requirement
  severity: high
  description: 닫힘 조건 ④ 「공급자·모델이 전후 같다」는 검증 불가능하게 정의돼 있다. §2.1 이 적은 대로 모델 id 는 응답에도
    `search_log` 에도 없고, 기록되는 값은 `NEXUS_LLM_PROVIDER`·`NEXUS_LLM_MODEL` 을 **기록하는 쪽
    프로세스의 env** 에서 읽은 자기 신고다. 라이브 app 은 별도 컨테이너/체크아웃에서 돌므로 기록자의 env 가 응답을 실제로 생성한
    프로세스의 env 와 같다는 보장이 없다. 같은 이유로 `before.json` 의 git commit 도 서빙한 코드와 묶이지 않는다. 응답/기록에
    모델 id 를 싣지 않는 한 ④ 는 기계로 판정할 수 없다.
  status: open
  disposition_reason: null
- issue_id: I-004
  category: missing-invariant
  severity: high
  description: 첫 닫힘의 유일한 증거는 `tests/eval/local/<tenant>/runs/<qid>/` 인데(§3.6 이 U5
    를 미룬 근거), 같은 §3.3 이 그 디렉터리 전체에 `expires_at` + 두 트리거 만료와 `query-text disable` 시
    통째 삭제를 걸고 `.gitignore` 로 커밋도 금지한다. 실행 기록에 대한 보존 예외가 없어 증거가 읽히기 전에 자동 삭제될 수 있고,
    남는 것은 `ENGINEERING_LOG` 한 줄뿐이라 사후에 닫힘 조건 ①~④ 를 재판정할 수 없다.
  status: open
  disposition_reason: null
- issue_id: I-005
  category: adr-contradiction
  severity: high
  description: §1 은 「ADR-0002 의 수요 당김은 U1 뒤의 14일 판정으로 구현된다」고 선언하지만, §3.2 는 그 판정이 「문턱이
    아니라 분류」이며 「주 10건 문턱은 버렸다」고 명시한다. ADR-0002 gate ⓐ 와 I-007 처분은 수요 신호를 **관측·기록된 비율이
    설정된 문턱을 롤링 윈도에서 넘는 것**으로 정의하고, ADR-0003 「design now, build on the gate」는 정성적 의지가
    gate ⓐ 를 대체하지 못한다고 못박았다. 문턱을 제거한 분류를 게이트 구현이라고 적은 것은 ADR-0002/0003 과 정면으로 어긋난다
    — 문턱을 버리는 선택 자체는 가능하지만 ADR 개정이나 소유자의 게이트 발동 선언이 필요하다.
  status: open
  disposition_reason: null
- issue_id: I-006
  category: missing-invariant
  severity: medium
  description: 프라이버시 불변식이 DB 에만 걸려 있다. U0-a 는 `query_retention` 의 `retain_days` 만료를
    export 에서 거르지만, `runs/<qid>/*.json` 에는 질문 원문뿐 아니라 **답변 본문과 `evidence_snippets`
    전체**가 복사되고, 그 파일의 `expires_at` 은 `retain_days`·고지(`--notice`) 범위와 묶여 있지 않다. 즉
    DB 에서 purge 된 뒤에도 같은 사람 문장이 파일로 남을 수 있다. 「파일 만료 ≤ 해당 행의 `first_seen + retain_days`」
    같은 불변식이 필요하다.
  status: open
  disposition_reason: null
- issue_id: I-007
  category: undefined
  severity: medium
  description: '`qid` 가 정의되지 않았다. §3.4 는 `runs/<qid>/` 와 하니스 신규 플래그 `--qid` 를 쓰고 §5
    는 「리포트의 qid 목록으로 단언」한다고 하지만, qid 가 라벨 id 인지 `query_sha256` 인지 보존 행 키인지, 누가 발급하는지,
    라벨 파일의 어느 필드와 묶이는지가 없다. 이 키가 라벨·실행 기록·`ENGINEERING_LOG` 세 곳을 잇는 유일한 식별자라 미정의가
    그대로 구현 분기를 만든다.'
  status: open
  disposition_reason: null
- issue_id: I-008
  category: undefined
  severity: medium
  description: U4 의 `llm_failed_n` 과 U2 판정의 `abstained` 는 출처가 제시되지 않았다. §2.1 이 나열한
    `search_log` 칸은 세 버전 값·`degraded`·`no_answer`·`n_citations`·`unverified_citations`
    이고, 생성 기권은 `llm/answer.py:232` 내부 동작으로만 적혀 있다. §3.5 는 스스로 「이 집계는 생성 실패를 못 본다」고
    하면서 `llm_failed_n` 열을 두어 자기모순이며, `abstained` 가 API 응답 필드인지(§3.3 표는 응답 필드처럼 쓴다)
    확인된 바가 없다. 둘 다 존재 확인 또는 신규 기록 설계가 선행돼야 한다.
  status: open
  disposition_reason: null
- issue_id: I-009
  category: untestable-requirement
  severity: medium
  description: '§3.3 의 「생성 실패」 판정이 「스니펫은 있는데 `abstained` **또는 사람이 본 답이 요구를 안 담음**」이라
    사람의 눈에 기준 없이 걸려 있다. 반면 §5 의 U2 테스트는 「부류가 응답 필드로 재현된다」만 단언하므로, 세 부류 중 하나는 테스트가
    덮지 않는다. 닫힘 조건 ①이 이 부류 판정에 의존하므로 판정 기준(예: `facts_present` 로 before 를 같은 채점기에 통과시키기)을
    기계화해야 한다.'
  status: open
  disposition_reason: null
- issue_id: I-010
  category: missing-invariant
  severity: medium
  description: U1 의 즉시 smoke test 와 U2 의 「현재 조건의 재검색」이 운영 트래픽과 **같은 principal·같은 보존
    경로**로 들어가는데, 합성 질문을 표시하는 수단이 없다. §6 은 「시뮬레이션을 닫힘으로 보고하지 않는다」고 선언하지만, export·후보
    목록·`from_user_query` 라벨에서 자가 생성 질문과 에이전트 실사용 질문을 가를 필드가 없다. 14일 판정 ①/③ 의 분류와 「실제
    트래픽 라벨 1건」 기준이 모두 이 구분에 의존하므로 보존 행에 출처 표식이 필요하다.
  status: open
  disposition_reason: null
- issue_id: I-011
  category: risky-assumption
  severity: medium
  description: §3.3 「빠진 문서 사례의 순서」는 요구(`must_contain`)를 먼저 후보로 적고 그 다음 문서를 적재·`extend`
    하도록 한다. 즉 요구가 **앞으로 넣을 문서에 맞춰** 작성되고, 저술 검사도 그 문서가 DB 에 있어야 통과한다. 그러면 after 3회
    통과는 거의 자동이고(teaching to the test) ②가 품질 개선의 증거로서 약해진다. 요구 문장이 운영 질문(또는 👎 사유)에서
    유도됐음을 보이는 독립 근거 — 예컨대 보존된 원문에서 추출했고 적재 문서를 보기 전에 서명했다는 기록 — 를 조건에 넣어야 한다.
  status: open
  disposition_reason: null
- issue_id: I-012
  category: missing-invariant
  severity: medium
  description: 닫힘 조건 ①~④ 가 「같은 조건」을 버전 값 세 개와 공급자·모델로만 정의한다. §3.3 이 못박은 single-turn·고정
    `top_k`·고정 route·history 없음, 그리고 §3.2 의 `read_tenants=(T,)`·고정 clearance 는 조건에
    들어가 있지 않다. `top_k` 나 route 가 달라도 세 버전 값은 바뀌지 않으므로(`search_fingerprint` 는 설정 절의
    함수, 요청 옵션의 함수가 아니다) 요청 옵션이 섞인 비교가 ①~④ 를 통과할 수 있다. `before.json`/`after-*.json`
    의 요청 옵션·principal 동일성을 조건 ⑤로 명시해야 한다.
  status: open
  disposition_reason: null
- issue_id: I-013
  category: adr-contradiction
  severity: medium
  description: §1 은 구현을 critique → disposition → approve 게이트 뒤로 두면서 §7-3 은 U0 셋을 승인
    전에 먼저 보내기를 권고한다. U0-b 처럼 이 SPEC 과 무관한 결함이면 몰라도, U0-c(`label_authoring_check` 가
    `check(..., require_corpus_binding=True)` 를 부르게 함)는 U2 성공 기준인 「서명된 `from_user_query`
    라벨 1건」의 판정 기준 자체를 바꾸는 **이 설계의 게이트 조각**이다. 승인 전에 그것을 구현하면 ADR-0003 §4·ADR-0004
    가 인용한 게이트를 스스로 우회한다.
  status: open
  disposition_reason: null
- issue_id: I-014
  category: risky-assumption
  severity: medium
  description: §3.2 는 「MCP(토큰 하나가 principal 하나)」를 전제하지만, 공유 MCP 토큰 하나를 여러 에이전트/세션이
    쓰면 principal 은 하나로 뭉쳐지고 §3.2 가 인정한 대로 HTTP 와 MCP 는 `search_log` 에서 구별되지 않으며 principal
    은 저장조차 되지 않는다(§2.1). 그러면 U2 의 「보존된 질문을 **같은 principal 로** 재검색」은 사실상 「같은 토큰으로」이고,
    원래 질문을 보낸 에이전트의 표면·옵션·대화 맥락이 달랐을 가능성을 배제하지 못한다. 보존 행에 표면/토큰 식별자를 남기지 않는 한 재검색이
    같은 조건이라는 주장은 전제일 뿐이다.
  status: open
  disposition_reason: null
- issue_id: I-015
  category: unverifiable-claim
  severity: medium
  description: §1 의 「이것이 실제 트래픽에서 한 번 성립하면 닫힌 것이다」는 n=1 로 순환의 닫힘을 선언한다. 한 질문·한 고침·세
    실행은 그 경로가 **한 번 통했다**를 보이지만 순환이 재현된다는 근거는 아니며, SPEC 스스로 U4 를 「증명이 아니다」로 내렸으므로
    반복 가능성에 대한 증거가 설계 안에 하나도 남지 않는다. 「닫혔다」를 「경로가 끝까지 한 번 관통했다」로 낮춰 적거나, 두 번째 질문의 독립
    재현을 닫힘 정의에 포함해야 한다.
  status: open
  disposition_reason: null
- issue_id: I-016
  category: undefined
  severity: low
  description: 「각 파일은 `expires_at` 을 가지고」(§3.3)가 기제 없이 적혀 있다. 파일 안 필드인지 사이드카인지 디렉터리
    메타인지 미정이고, 같은 디렉터리의 `answer-labels.yaml` 은 Pack B 서명 대상이라 서명 뒤 필드를 더하면 서명이 깨진다.
    만료 메타는 서명 바깥(사이드카)에 두어야 하며 SPEC 이 그 자리를 지정해야 한다.
  status: open
  disposition_reason: null
- issue_id: I-017
  category: untestable-requirement
  severity: low
  description: 14일 판정 분류 ③(후보 없음)의 처분이 「좋은 소식이고, 다음 14일」로 끝나 종료·중단 규칙이 없다. 분모가 있는데
    실패 부류가 계속 0 이면 U2 이하가 무한히 연기되며, 그 상태가 「닫을 것이 없다」인지 「선별 기준이 너무 좁다」인지 가를 기준도 없다.
    반복 횟수 상한과 그때의 처분(기준 재검토 또는 중단)을 적어야 판정이 검사 가능해진다.
  status: open
  disposition_reason: null
approved_by: null
approved_at: null
---

