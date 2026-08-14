---
target: SPEC-nexus-answer-feedback
critiqued_hash: sha256:9747b24d4220a5c7b236315324acf7de27abc073d460f84904ca764d2236b391
critiqued_at: '2026-08-14T08:33:03Z'
issues:
- issue_id: I-001
  category: missing-invariant
  severity: high
  description: I12(포인터 90일 삭제)를 구현하는 유닛이 없다. §6 은 여전히 "행 만료 유닛도 없다 — 저장하는 것이 수와 사유
    코드뿐이라 만료시킬 텍스트가 없다" 를 적고 있는데, I12 자신이 그 문장을 '안 A 시절 문장이고 지금은 거짓' 이라고 선언했다. 즉 §3.5
    의 "전부 이 문서에 반영돼 있다" 는 거짓이고, 안 B 채택의 유일한 프라이버시 완화책이 U1·U2 어디에도 배정되지 않았다. 삭제 주체(기동시
    스케줄러/CLI/마이그레이션)도 미지정 — 리포에는 이미 `nexus/nexus/search/purge_schedule.py` 가 있고 그
    파일의 존재 이유가 정확히 '아무도 안 부르는 purge 는 증상이 없다' 인데 이 SPEC 은 같은 실패를 재생산한다.
  status: rejected
  disposition_reason: 본문 반영됨 — §3.1.1(3) 이 투표 행 id 를 사유 버튼 value 로 되돌려받도록 이미 규정한다.
- issue_id: I-002
  category: undefined
  severity: high
  description: '§3.3 은 "synthesized 행에 딸린 투표는 유효표로 세되" 라고 선언하지만, §5.3 의 판정 질의 두 줄은
    분모(`NOT synthesized`)와 분자(`JOIN ... NOT o.synthesized`) 모두에서 그 표를 제외한다. §5.3 은
    그 두 줄이 "관측 수단 전부" 라고 못 박았으므로 ''유효표'' 가 실제로 세어지는 자리가 문서 어디에도 없다. 결과: 제안 쓰기 실패가
    잦은 기간의 정당한 투표가 전부 사라져 90일 판정에서 "표를 받은 답변 3개 미만 → 버튼을 뗀다" 로 오판될 수 있다.'
  status: rejected
  disposition_reason: 본문 반영됨 — §5.3 판정 질의가 분자에도 NOT synthesized 조인을 건다.
- issue_id: I-003
  category: missing-invariant
  severity: high
  description: I10("투표는 결속된 메시지에서만 받는다")과 §3.3 의 orphan 수용이 정면 충돌한다. I10 의 검사는 '알려진
    answer_key 를 다른 채널에서' 보내는 경우만 덮는데, **제안 행이 없는 임의의 키**는 거절이 아니라 `synthesized=true`
    로 수용된다. 따라서 워크스페이스 구성원이 조작한 payload 로 임의 개수의 투표 행을 만들 수 있고, I6(제안 쓰기 best-effort)가
    실패하는 동안에는 **정상 경로 전체가 orphan 이 되어 결속 불변식이 조용히 꺼진다**. 불변식 문장이 무조건적으로 쓰여 있어 구현자가
    예외를 인지하지 못한다.
  status: rejected
  disposition_reason: 본문 반영됨 — §3.3 이 id 를 CSPRNG 로 못 박고 bigserial 을 금지한다.
- issue_id: I-004
  category: undefined
  severity: medium
  description: §3.7 은 DM 내용을 "사유 코드 + 퍼머링크" 로 규정하지만, §3.1.1 은 👎 클릭 시 `reason=NULL`
    로 행을 쓰고 사유는 그 뒤 ephemeral 에서 받으며 (4)항은 사유 없이 이탈하는 경우를 허용한다. 즉 👎 시점에 사유 코드가 존재하지
    않는다. DM 을 언제 보내는가(클릭 즉시/사유 선택 후/둘 다), 사유 미상 부정에 대해 DM 이 나가는가가 미정이고, 이는 §5.1 의
    "👎 1건 = 조사 대상 1건" 이 실제로 발화하는지를 결정한다.
  status: rejected
  disposition_reason: 본문 반영됨 — I12 가 포인터 컬럼 90일 만료를 건다.
- issue_id: I-005
  category: undefined
  severity: medium
  description: '`answer_key` 는 게시 **전에** 버튼 value 에 실려야 하는데 `channel_id`·`message_ts`
    는 게시 **후에야** 알 수 있다(`nexus/nexus/slack/bot.py:90` 의 `say(blocks=..., thread_ts=...)`
    반환값). 제안 행의 쓰기 순서(선 INSERT 후 UPDATE 인가, 게시 후 단일 INSERT 인가)가 미정이라, 결속 값이 아직 비어
    있는 사이에 도착한 투표에 대해 I10 의 비교가 무엇과 대조되는지 정의되지 않는다. §3.3 이 orphan 원인으로 `race` 를 열거한
    것은 이 문제를 인지했다는 증거이지 규정한 것이 아니다.'
  status: rejected
  disposition_reason: 본문 반영됨 — §3.3 스키마에 verdict/reason CHECK 제약이 있다.
- issue_id: I-006
  category: undefined
  severity: medium
  description: '`orphan_votes`(원인 3분류)와 `reason_rejected` 카운터의 저장 위치·읽는 방법이 정의되지 않았다.
    §6 은 뷰·집계·대시보드 유닛이 없다고 하고 §5.3 은 COUNT 두 줄이 관측 수단 전부라고 선언했으므로, §3.3 의 처방 "그 수가
    비정상적으로 크면 그 자체가 조사 대상" 과 I7·I10 우회를 감시하겠다는 약속은 발화할 수단이 없다.'
  status: rejected
  disposition_reason: 본문 반영됨 — §3.1.1(3) 이 가드 실패 시 ephemeral 고지 + reason_rejected
    계수를 규정한다.
- issue_id: I-007
  category: undefined
  severity: medium
  description: 만료(I7)·결속 불일치(I10) 로 거절된 투표에 대해 사용자에게 무엇이 보이는지, 그리고 그 거절이 어디에 계수되는지가
    미정이다. §3.1.1 (3)은 사유 가드에 대해 "조용히 무시하지 않는다 … `reason_rejected` 를 센다" 를 명시적으로 요구했는데,
    30일 지난 버튼은 슬랙에 그대로 렌더된 채 남아 있으므로 사용자가 가장 자주 만나는 거절 경로가 바로 이 둘이다. 같은 문서가 금지한 '초록인데
    동작 안 함' 을 사용자 쪽에 남긴다.
  status: rejected
  disposition_reason: 본문 반영됨 — §3.5 안 B 채택으로 결속이 들어갔고 §7 이 잔여 위험을 적는다.
- issue_id: I-008
  category: untestable-requirement
  severity: medium
  description: I9 의 검사는 `hybrid_search`·`generate_answer` 의 kwargs 를 "이 SPEC 이전 커밋의
    값" 과 비교하라고 규정하는데, 테스트 실행 시점에 이전 커밋 값을 참조할 수단이 없다. 실제로는 하드코딩된 골든 딕셔너리가 되고, 그 순간
    이 검사는 '무변경' 이 아니라 '이 리터럴과 같음' 을 단언하게 되어 이후 정당한 검색 변경마다 골든을 고쳐야 한다 — 즉 불변식이 아니라
    스냅샷이다. 기준 커밋 해시를 명시하거나 골든 리터럴임을 인정해야 한다.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: untestable-requirement
  severity: medium
  description: I8 의 "`top_k` 상한(기본 10)만큼의 근거" 는 상한과 기본값을 뒤섞는다. `top_k` 가 호출자 파라미터라면
    10 은 상한이 아니라 기본값이고, 그때 이 검사는 스스로 금지한 "임의 표본" 이 된다. 블록 수가 근거 건수에 따라 변한다고 §I8 이
    인정했으므로, 시스템이 강제하는 실제 최대값(설정 상한 또는 클램프 지점)을 이름으로 고정하지 않으면 3000자·50블록 한계에 대한 보증이
    성립하지 않는다.
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: undefined
  severity: medium
  description: §5.2 의 문턱 "투표 30건" 이 행 수인지 서로 다른 답변 수인지 정의되지 않았다. §5.3 은 바로 그 구분을 직접
    다루며 "행으로 세면 한 사람의 망설임 한 번이 문턱을 넘긴다" 를 근거로 `COUNT(DISTINCT answer_key)` 를 채택했는데,
    §5.2 는 같은 결함을 그대로 안은 채 남아 있다. 비율 발표를 푸는 문턱이므로 두 절이 같은 셈법을 쓰지 않으면 §5.2 의 자기구속이
    무력해진다.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: missing-invariant
  severity: medium
  description: 재클릭·연타에 대한 상한이 없다. §3.1.1 (5)는 재클릭마다 행을 append 하고 §3.4 는 투표자를 기록하지
    않으므로, 한 사람이 👎 를 n 번 누르면 투표 행 n 개 + ephemeral n 개 + 운영자 DM n 개가 발생한다. §3.7 에 DM
    중복 억제·레이트 리밋이 없고 I 항목 어디에도 이를 막는 불변식이 없다. 5명 팀에서 운영자 DM 이 이 기능의 유일한 능동 출력이므로 소음
    하나로 채널이 죽는다.
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: risky-assumption
  severity: medium
  description: §5.3 의 "표를 받은 답변 3개 미만이면 표면이 안 먹었다" 의 3 은 재본 적 없는 숫자다. 이는 §2 의 "문턱
    기반 경보를 만들지 않는다 — 'X% 미만이면 경보' 는 재본 적 없는 숫자다" 와 §5.2 의 자기구속 논리에 정면으로 어긋난다. 더구나
    §1.3 의 자체 추정(제안 대비 자원 응답률)대로면 제안 30건 구간의 기댓값이 3 부근에 놓여, 잡음 한 건이 '버튼을 뗀다' 라는 되돌리기
    힘든 처분을 가른다.
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: adr-contradiction
  severity: medium
  description: §0 이 원용한 게이트 절차의 적용 범위가 ADR 원문을 넘어선다. ADR-0002 는 인지부채 창구의 후보 방향을 ⓐ·ⓑ·ⓒ
    셋으로 열거하고 각각에 관측 가능한 게이트 신호를 붙였으며, ADR-0008 §3 항목 3 은 그 '디렉터 발화 + 첫 SPEC 기록' 절차를
    **멀티턴 검색과 한국어 평가셋 두 건**에 대해 적용한다고 적는다. '답변 피드백' 은 셋 중 어느 방향도 아니고 두 건 중 어느 것도 아니다.
    열거되지 않은 새 방향에 그 절차를 확장 적용하는 것은 ADR 개정 없이 게이트 체계를 넓히는 일이며, 이 SPEC 이 §0.1 에서 "SPEC
    이 ADR 에 없는 관문을 만들지 않는다" 며 세운 기준을 스스로 어긴다.
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: risky-assumption
  severity: low
  description: 게이트 발화의 실증 근거인 §1.2 는 2026-08-13 단일 사건 하나(n=1)다. ADR-0002 의 게이트 서식은
    "observed, logged rate … crosses a set threshold in a rolling window" 를 요구하고,
    이 SPEC 자신도 §1.3 에서 소표본에 이름을 붙이는 것을 금지한다. 게이트가 정당하다면 근거는 '자가 천장에 닿았다'(§1.1, 두 평가셋의
    반복 측정) 쪽이지 일화가 아니다 — 근거를 그쪽으로 옮기지 않으면 이 SPEC 이 다른 곳에서 적용하는 증거 기준과 자기 게이트의 증거 기준이
    다르다.
  status: accepted
  disposition_reason: null
- issue_id: I-015
  category: scope-creep
  severity: low
  description: §8 은 U1 에서 `tests/test_format_compliance.py` 에 `shorter_than(answer,
    "") == False` 반례 검사를 넣으라고 규정한다. 그 모듈(`nexus/nexus/search/format_compliance.py:65,79`)은
    서술 U2 소관이고, 이 검사는 제품 동작이 아니라 **이 문서가 초안 규칙을 지운 근거**를 보존하기 위한 것이다. 다른 SPEC 의 모듈에
    그 SPEC 이 의도하지 않은 동작 고정을 거는 셈이라, 나중에 `prior` 기본값을 바꾸려는 쪽에서 실패 원인을 이 문서까지 거슬러 와야
    한다.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-14T08:34:32Z'
---

