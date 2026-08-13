---
target: SPEC-nexus-multi-turn-narration
critiqued_hash: sha256:593f6b6122e9514b4ddb5c404c1e10e3090bc3222bdf266bd34b5252ba6c53d3
critiqued_at: '2026-08-13T11:36:39Z'
issues:
- issue_id: I-001
  category: adr-contradiction
  severity: high
  description: SPEC-nexus-multi-turn-retrieval §4 I3 은 '이력은 답변 프롬프트에 들어가지 않는다' 를 **구조적
    불변식**으로 박았고, 그 검사는 문자열 검사가 아니라 프롬프트 조립 함수의 **호출 인자에 이력이 없음을 직접 단언**한다. 이 SPEC
    의 U3(§3.2)는 직전 assistant 답변을 바로 그 프롬프트에 넣는다 — 즉 기존 불변식과 그 검사를 정면으로 깨뜨린다. §1.2
    는 '그 SPEC 의 범위에서 옳은 결정이었다' 고 언급만 할 뿐, I3 을 개정·대체(supersede)한다는 처분도, 기존 검사를 무엇으로
    바꾸는지도 적지 않는다. ADR-0008 §3.3 이 요구하는 'SPEC 마다 자기 게이트' 절차와 별개로, 선행 SPEC 의 불변식을 조용히
    무효화하는 것은 기록되지 않은 계약 파기다.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: '''직전 답변'' 이 **실제로 Nexus 가 이 요청자에게 생성해 준 답변인지** 검증하는 불변식이 없다. 이력은 검색
    SPEC 과 마찬가지로 클라이언트가 보내는 값이므로, 임의의 텍스트를 assistant 턴으로 위조해 보내면 시스템이 그것을 `[출처: …]`
    인용과 함께 다시 말하고 `derived_from_prior_answer: true` 배지를 붙여 준다. §3.3 이 막으려던 세탁의 가장
    싼 경로가 모델 환각이 아니라 **클라이언트 위조**인데, 턴 ID·서명·서버측 대조 중 어느 것도 요구되지 않는다.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: missing-invariant
  severity: high
  description: 직전 답변에 **테넌트·principal·clearance 결속**을 요구하는 불변식이 없다. 서술형 경로는 검색을 타지
    않으므로 검색 SPEC I4 의 정책 필터(`tenant`/`classification <= clearance`/`quarantine`/`status`)가
    적용될 자리가 없는데, §4 I1~I7 중 어느 것도 그 공백을 메우지 않는다. 슬랙 스레드에서 높은 등급 사용자의 답변에 낮은 등급 사용자가
    '그거 요약해줘' 를 붙이면 등급 우회가 된다. §8 이 '다중 저자' 를 미해결로 적어 두었으나, U3 는 그 해결을 선행조건으로 걸지 않고
    착수 가능하게 되어 있다.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: untestable-requirement
  severity: high
  description: I3('앞 답변에 없던 사실을 보태지 못한다')는 검사 방법을 §5.2 에 위임하는데, §5.2 표에는 그 검사가 **없다**.
    표의 행은 형식 준수 4개와 대조군 2개뿐이고, 괄호로 적힌 '숫자 검증기 재사용' 은 숫자만 덮으므로 고유명사·날짜 아닌 주장·인과 진술은
    전혀 잡지 못한다. 스스로 'I2 보다 강한 요구' 라고 선언한 불변식이 판정 규칙 없이 남는다.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: risky-assumption
  severity: high
  description: §3.1 의 '오분류의 두 결과가 모두 안전하다' 는 논증이 이 설계의 근간인데 성립하지 않는다. (1) 검색형 질문이
    서술형으로 잘못 분류되면 문서에 있는 답 대신 앞 답변만 보고 답하게 되므로, §1.1 이 '더 나쁘다' 고 규정한 **조용히 딴 답** 이
    정확히 재생산된다 — 실패 모양이 바뀌지 않았다. (2) '새 사실을 만들 재료가 없다' 는 것도 거짓이다. 모델의 파라메트릭 지식은 재료로
    남아 있고(자체 하니스에서 런당 파라메트릭 정답 2~4건이 관측된다), 이를 막는 것은 프롬프트 지시일 뿐 '코드가 좁힌' 것이 아니다.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: missing-invariant
  severity: high
  description: §3.3 이 `validate_citations` 의 대조 대상을 근거 패킷에서 직전 답변으로 바꾸면 검증기가 보장하던
    성질이 사라진다. 현행 `nexus/nexus/llm/citations.py` 는 인용된 제목이 **이번 턴에 실제로 보여준 문서 제목 집합**에
    있는지를 본다. 직전 답변 텍스트를 기준으로 삼으면 (a) 1턴에서 이미 미검증이던 인용이 2턴에서 검증됨으로 승격되고, (b) 인용이 아니라
    본문에 언급만 된 제목도 통과하며, (c) 그 제목이 여전히 존재·active·열람가능한 문서인지에 대한 대조가 사라진다. §3.3 이 막겠다고
    선언한 세탁을 검증기 변경 자체가 새로 연다.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: missing-invariant
  severity: high
  description: §3.4 는 재작성기가 '(질의, 떼어낸 요청)' 둘을 돌려주게 바꾸지만, 그 두 번째 값에 대한 어떤 상한·검증·주입
    규칙도 정하지 않는다. 현행 `nexus/nexus/search/rewrite.py::_acceptable` 은 단일 라인·`MAX_CHARS=400`·`MAX_GROWTH=3.0`
    로 재작성 결과를 코드가 판정하는 **안전망**인데, 출력이 두 값이 되면 이 판정이 어떻게 재정의되는지 미기재다. 또 '떼어낸 요청' 은
    답변 프롬프트로 들어가면서도 I5(구분자 자료 블록·지시 불복종)의 적용 대상이 아니다 — 앞 답변에만 걸려 있다.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: risky-assumption
  severity: high
  description: §5.3 부분 채택의 '§3.4 는 앞 답변을 프롬프트에 넣지 않으므로 세탁 위험이 원리적으로 없다' 는 틀렸다. '떼어낸
    요청' 은 사용자 원문을 그대로 자른 문자열이 아니라 **전체 이력 블록을 읽은 LLM 이 생성한 텍스트**이므로, 이력에서 유래한(또는 지어낸)
    문장이 답변 프롬프트로 들어가는 경로가 U2 만으로도 열린다. 이는 검색 SPEC I3 이 '구조적으로 없다' 고 주장한 바로 그 경로이고,
    §6 표가 U2 위험을 '낮음 (앞 답변 미사용)' 으로 표기한 근거도 무너진다.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: untestable-requirement
  severity: high
  description: §5.2 의 세탁 대조군은 '거짓 사실이 **인용과 함께** 나타나면 실패' 로 정의돼, 인용 없이 거짓 사실만 재진술되는
    경우를 잡지 못한다 — 그런데 §3.3 규칙상 서술형 답변은 새 인용을 못 만들므로 실패가 발화하려면 심어 둔 거짓 사실에 인용까지 함께 심어야
    하고, 그 조건이 명시돼 있지 않다. 더구나 §5.3 은 '0건' 을 채택 조건으로 걸면서 **시행 횟수·표본 크기를 정하지 않는다.** §5.1
    이 스스로 10회 잡음 측정을 규율로 세운 문서에서, 확률적 사건에 대한 0/N 관측은 상한을 주지 못한다.
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: untestable-requirement
  severity: medium
  description: §5.2 의 기계 판정 조건들이 기계 판정으로 성립하지 않거나 무력하다. '답변 줄 수 ≤ 3' 은 개행 없는 장문 한
    줄이 통과한다(§1.1 이 문제 삼은 실패가 그대로 통과). '2번 항목 문자열이 있고 1·3번은 없다' 는 항목 간 문자열이 겹치면 판정
    불능이고, 애초에 '항목' 을 직전 답변에서 어떻게 추출하는지 정의가 없다. '제일 중요한 것' 행의 '문장/항목 중 하나를 지목한다' 도
    기계 규칙이 아니다. 라벨셋 크기와 통과율 계산 규칙도 미기재라 §5.3 의 '잡음 폭 이상' 비교가 성립하지 않는다.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: undefined
  severity: medium
  description: 서술형으로 분류된 턴에 **검색을 여전히 도는지**가 어디에도 없다. 이 하나가 정해지지 않으면 근거 패킷의 존재 여부,
    U4 의 대조 대상(패킷이 비었을 때의 동작), `search_log` 에 무엇이 남는가(신호 오염), 지연·비용, 그리고 I7 의 '검색은
    안 바뀐다' 가 무엇을 뜻하는지가 전부 미정으로 남는다.
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: undefined
  severity: medium
  description: §3.2·I6 의 '길이 상한' 에 숫자가 없고, 기존 정본인 `nexus/nexus/search/history.py`(MAX_TURNS=8,
    MAX_BYTES=8KiB, 초과 시 413 거절)와의 관계도 미정이다. 두 문서가 초과 처리 방식마저 반대다 — 검색 SPEC I5 는 **거절**,
    이 SPEC I6 는 **오늘 경로로 강등**. 같은 요청이 이력 상한은 넘고 직전 답변 상한은 안 넘는(또는 그 반대) 조합에서 무엇이 이기는지
    알 수 없다.
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: undefined
  severity: medium
  description: I7 의 '`hybrid_search` 가 받는 **인자**를 바꾸지 않는다' 가 시그니처를 말하는지 인자 **값**을
    말하는지 불분명하다. 값이라면 §3.4 가 재작성 프롬프트를 고치는 순간 재작성된 질의 문자열이 달라질 수 있어 위반 가능성이 있고, 시그니처라면
    그물에 이가 없다 — 검색 품질 회귀가 통과한다. §5.2 의 '검색형 대조군' 도 답변 수준 비교라 재작성 질의 자체의 변화를 잡지 못한다.
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: unverifiable-claim
  severity: medium
  description: §1.1 의 실측 3건은 각 1회 관측으로 보이며(반복 횟수 미기재), 같은 문서 §5.1 이 '5회는 폭을 과소평가했다,
    10회로 재라' 는 규율을 세운 것과 어긋난다. '1125자 → 1304자' 같은 길이 변화는 잡음 폭을 모르는 상태의 단일 관측이라 방향조차
    보장되지 않는다. 이 SPEC 전체를 부르는 근거가 SPEC 자신의 계측 기준을 통과하지 못한다.
  status: accepted
  disposition_reason: null
- issue_id: I-015
  category: adr-contradiction
  severity: medium
  description: §0.1 의 backstop 불발화 판단이 ADR-0008 §5 를 축약 인용한다. ADR 원문의 방아쇠는 '새 검색 채널,
    두 번째 인덱스 백엔드, 토크나이저·임베딩 모델 변경, 기존 두 소스를 넘는 커넥터 작업' 이고 상위 조건은 '검색 스택을 **실질적으로 확장하는
    작업의 착수 시점에 재독**' 이며 **owner 는 LivingLikeKrillin** 이다. 이 SPEC 은 재작성기(검색 경로 코드)와
    인용 검증기를 고치면서 방아쇠 해당 여부를 스스로 판정해 종결한다 — ADR-0008 §3.3 이 '게이트는 디렉터가 선언한다' 고 정한 것과
    같은 이유로, 불발화 판정도 SPEC 이 혼자 내릴 것이 아니다.
  status: accepted
  disposition_reason: null
- issue_id: I-016
  category: scope-creep
  severity: medium
  description: §3.4 는 '서술' 이 아니라 **모든 이력 있는 턴**(검색형 포함)의 답변 프롬프트를 바꾸고, 다른 SPEC 이 소유한
    재작성기의 반환 계약까지 바꾼다. §0 의 게이트 범위가 아직 비어 있는 상태에서 범위를 서술형 밖으로 넓히는 것이고, 비목표의 '검색을 바꾸지
    않는다 — 건드리는 것은 답변 프롬프트가 무엇을 보는가 하나뿐' 이라는 자기 선언과도 어긋난다.
  status: accepted
  disposition_reason: null
- issue_id: I-017
  category: risky-assumption
  severity: medium
  description: §7 의 '섞인 요청은 검색형으로 처리된다(안전한 쪽)' 는 설계 성질처럼 적혀 있으나 강제 기제도 검사도 없다 — 모델
    분류가 그렇게 해 주기를 바라는 기대다. §5.2 의 라벨셋에도 혼합 요청 행이 없어, 이 안전 가정은 채택 판정 시점에 한 번도 측정되지
    않는다.
  status: accepted
  disposition_reason: null
- issue_id: I-018
  category: missing-invariant
  severity: low
  description: I4 는 표시 의무를 '슬랙·웹' 으로만 걸어, A2A/MCP 등 에이전트 소비 표면에 대한 요구가 없다. 컴포넌트 모델상
    A2A 가 에이전트 정문이고 응답 필드는 실려 나가므로, 소비자 쪽에서 서술형 답변이 문서 기반 답변과 구별되지 않을 수 있다. 슬랙 렌더링도
    Block Kit 3000자 상한 이력이 있어 '보여준다' 의 검사 형태가 정해져야 한다.
  status: accepted
  disposition_reason: null
- issue_id: I-019
  category: undefined
  severity: low
  description: '§8 의 ''직전 답변이 기권이었을 때''(예: ''찾을 수 없습니다'') 가 미해결로 남아 있는데, U3 는 이 경우의
    동작 정의 없이 착수 가능하다. 요약 대상이 비어 있으면 모델이 채워 넣을 유인이 가장 큰 자리이므로, 미해결로 두는 것과 U3 착수 가능은
    양립하지 않는다.'
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-13T12:05:10Z'
---

