---
target: SPEC-nexus-audit-query-hash
critiqued_hash: sha256:a01db09bb8ef803db899921bd66f1c0378ec5f2f985831010cccd7e42750b740
critiqued_at: '2026-08-14T08:42:55Z'
issues:
- issue_id: I-001
  category: missing-invariant
  severity: high
  description: I1("새 감사 행에 질의에서 유도된 값이 없다")과 I3("query_len 은 그대로다")가 정면으로 모순된다. query_len
    은 질의의 결정적 함수이고, §7 스스로 그것이 남는 결합 채널이라고 인정한다. 따라서 I1 은 설계 자체로 성립 불가능한 불변식이며, 검사(sha256·소금본·절단본
    부재)만 통과시키려면 'query_len 은 예외'를 암묵적으로 두어야 하는데 그 예외가 문서 어디에도 명시돼 있지 않다. I1 의 표제를
    '역산 가능한 고엔트로피 지문이 없다'처럼 실제 검사 범위로 낮추고 query_len 을 명시적 허용 항목으로 적어야 한다.
  status: rejected
  disposition_reason: 이전 라운드에서 이미 본문에 반영됨(위협 모델 §3.0·잔여 채널 §7·옵션 A 개명) — 재지적.
- issue_id: I-002
  category: untestable-requirement
  severity: high
  description: 'I5("principal 을 가진 어떤 표에도 질의 유도값 컬럼이 생기지 않음을 스키마 전수 조회로 단언")는 검사가
    불가능하다. 스키마 조회로 얻는 것은 컬럼 이름·타입뿐이고, 어떤 컬럼이 ''질의 유도값''인지는 값의 출처를 봐야 안다. 즉 I5 를 구현하면
    필연적으로 이름 기반 판정이 되는데, 그것은 I2 의 ''컬럼 이름이 아니라 값으로 검사한다''와 §5.2 의 ''컬럼 이름이 다르다를 안전이라
    부르지 않는다''가 금지한 바로 그 방식이다. 게다가 I5 는 ''새 감사 표·A2A metadata·애플리케이션 로그''까지 대상으로 삼는데
    로그는 스키마 조회로 볼 수 없다. 검사 가능한 형태(예: 감사 기록 함수의 입력에 query 문자열이 전달되지 않음을 호출 경로 검사로 단언)로
    다시 쓰거나 불변식에서 내려야 한다.'
  status: rejected
  disposition_reason: 이전 라운드에서 이미 본문에 반영됨(위협 모델 §3.0·잔여 채널 §7·옵션 A 개명) — 재지적.
- issue_id: I-003
  category: missing-invariant
  severity: high
  description: §3.3 은 '컬럼을 nullable 로 바꾼다'고만 적고 어느 선언을 바꾸는지 말하지 않는다. §3.1 표는 스키마 선언
    지점이 init.sql:439 와 db.py:110 둘이라고 스스로 밝혔는데, 마이그레이션만 추가하고 init.sql/db.py 를 두면 신규
    배포(빈 DB 를 init.sql 로 만드는 경로)는 여전히 NOT NULL 컬럼을 만들고 NULL 을 쓰는 새 코드가 첫 감사 기록에서 실패한다.
    이는 리포에서 반복 재발한 '정본과 사본이 갈리는' 결함 형태다. 유닛 U1 에 두 선언 동기화와 '빈 DB 를 init.sql 로 세운 뒤
    감사 행 1건 기록' 검사를 넣어야 한다.
  status: rejected
  disposition_reason: 이전 라운드에서 이미 본문에 반영됨(위협 모델 §3.0·잔여 채널 §7·옵션 A 개명) — 재지적.
- issue_id: I-004
  category: adr-contradiction
  severity: medium
  description: '§0 은 ADR-0008 §3 항목 3 의 게이트가 이 문서에 적용되지 않는다고 SPEC 스스로 논증한다. 그러나 ADR-0008
    §3 항목 3 이 명시적으로 고정한 절차는 ''게이트는 디렉터가 발화를 선언하고 그 방향의 첫 SPEC 에 기록되는 것이지, SPEC 이 논증으로
    만들어 내는 것이 아니다(it is not argued into existence by the SPEC)''이다. 면제 역시 같은 절차의 대상이며,
    SPEC 이 자기 면제를 논증하는 형태는 ADR 이 금지한 방향의 거울상이다. §3.2 의 ''결정: 디렉터 · 2026-08-14'' 처럼
    면제도 디렉터 선언으로 기록하는 한 줄이 필요하다.'
  status: rejected
  disposition_reason: 이전 라운드에서 이미 본문에 반영됨(위협 모델 §3.0·잔여 채널 §7·옵션 A 개명) — 재지적.
- issue_id: I-005
  category: risky-assumption
  severity: medium
  description: §7 의 search_log 제외 근거가 §3.0 위협 모델과 어긋난다. '그 표로 확인할 수 있는 것은 이 질문이 있었다인데
    search_query_text 가 평문으로 이미 갖고 있다 → 새로 알려주는 것이 없다'는 추론은 두 표를 모두 읽는 적대자 (a) 에게만
    성립한다. §3.0 이 '가장 큼'이라고 평가한 적대자 (b)(수출본만 보는 자)에게 search_log 덤프는 무염 지문 + 비용·토큰·sufficiency·no_answer
    까지 딸린 훨씬 큰 표면이고, 후보 목록 대입으로 '어떤 질문이 있었나'가 그대로 확인된다. 제외 결정 자체는 유지할 수 있으나 근거를 (b)
    기준으로 다시 쓰거나, principal 부재만을 근거로 좁혀야 한다.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: unverifiable-claim
  severity: medium
  description: §3.1 은 `grep -rn "query_sha256" --include=*.py --include=*.sql --include=*.js
    .` 를 돌리고 '리포 전체'라고 적었다. --include 세 개는 .ts/.tsx(Probe·Observer 는 TypeScript),
    .md, .sh, .yml, 노트북, 대시보드 정의를 전부 제외한다. '조회·조인·집계가 없다'는 표의 핵심 근거가 실제로는 세 확장자에 한정된
    결과이며, U1 의 위험도 '낮음' 판정이 그 위에 서 있다. 확장자 제한 없이 재실행하고 명령과 결과를 갱신해야 한다.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: risky-assumption
  severity: medium
  description: §3.2 권고 근거 3 '지금이 제일 싸다 — a2a_audit 은 2행이다. 이 결정은 미룰수록 비싸진다'는 이 문서의
    처분과 모순된다. §2 와 I4 가 기존 행을 손대지 않는다고 못 박았으므로 수리 비용은 행 수와 무관하다(코드 수정 + 테스트 뒤집기 +
    각주). 행이 2행이든 200만 행이든 A 의 작업량은 같다. 미루면 비싸지는 것은 '수리 비용'이 아니라 '그 사이에 쌓이는 무염 지문 행의
    수', 즉 노출량이다. 근거를 그렇게 바꿔 적지 않으면 비용 논거가 검증되지 않는다.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: risky-assumption
  severity: medium
  description: §1.4 의 '재계산을 막는 것은 둘뿐이다(비밀, 또는 결정적 함수를 아예 저장하지 않는 것)'는 검증되지 않은 전칭 이지선다이고,
    이 문서의 설계가 스스로 반증한다. I3 은 query_len 을 남기는데 그것은 질의의 결정적 함수다 — 즉 실제 기준은 '결정적 함수 저장
    금지'가 아니라 '재식별에 충분한 엔트로피를 남기지 않기'다. 손실 함수(길이 버킷·k-익명 버킷)나 접근이 분리된 곳에 둔 행별 난수 소금도
    후보로 존재한다. '둘뿐'을 유지하려면 왜 손실 함수 계열이 배제되는지 적어야 하고, 아니면 문장을 엔트로피 기준으로 다시 써야 한다.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: untestable-requirement
  severity: medium
  description: §5.1 의 양성 대조군이 §3.3.2 와 충돌한다. 대조군은 '옛 방식의 무염 지문을 가진 감사 행'을 만들어야 하는데,
    §3.3.2 는 그 값을 만드는 nexus/a2a/audit.py::query_sha256 함수를 지운다. 결과적으로 대조군은 테스트 파일에
    손으로 다시 적은 sha256 을 넣게 되고, 이 검사가 증명하는 것은 '탐지기가 내가 방금 심은 값을 찾는다'뿐이다. 프로덕션 경로가 미래에
    다른 모양의 지문(다른 다이제스트·정규화 후 해시·절단본)을 쓰기 시작해도 이 대조군은 그대로 통과한다. 대조군을 '기록 경로에 질의 문자열을
    흘리는 결함을 일부러 재도입한 상태에서 검사가 빨간불이 되는가'로 짜야 실제 그물이 된다.
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: scope-creep
  severity: medium
  description: §2 비목표는 '바꾸는 것은 질의 지문 한 칸'이라고 범위를 못 박았는데, I5 는 '어떤 표에도'라는 리포 전역 상시
    제약과 새 감사 표·A2A metadata·애플리케이션 로그까지 포괄하는 스키마 전수 검사를 도입한다. 이는 한 칸 수리가 아니라 감사 데이터
    전반에 대한 정책 신설이고, 유닛 표(U1 '낮음')의 위험 산정에도 반영돼 있지 않다. I5 를 이번 범위의 검사(감사 기록 함수 하나에
    대한 회귀 검사)로 좁히거나, 별도 유닛/후속 SPEC 으로 분리해야 한다.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: undefined
  severity: medium
  description: §8 은 '서명된 문서를 사후에 철회하는 절차가 리포에 없다'고 인정하면서 누가 서명하는가·원 서명이 무효가 되는가·원
    SPEC status 를 바꾸는가를 미정의로 남긴다. 그런데 §3.3.4 와 §6 U1 은 그 미정의 절차의 산출물(승인·서명된 SPEC 두
    개에 대한 철회 각주)을 이번 유닛의 인도물로 포함한다. '승인된 뒤에 단다'는 시점만 정할 뿐 각주의 형식·서명 주체·원본 status 처리를
    정하지 않으므로, U1 의 완료 판정 기준이 없고 각주를 검사하는 불변식도 없다. 최소한 각주의 필수 필드(철회 대상 문장 인용·철회 SPEC
    id·서명자)와 원 SPEC status 를 건드리지 않는다는 명시가 필요하다.
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: unverifiable-claim
  severity: medium
  description: §1.3 의 표제 '승인된 SPEC 의 중심 논거가 거짓이다'가 본문과 어긋난다. 본문은 인용문이 '키에 대해서는 참'이라고
    스스로 인정하고, 거짓인 것은 인용문 자체가 아니라 그 문장에서 도출된 더 넓은 안전성 결론이라고 적는다. 서명된 문서를 사후 철회하는 근거로는
    '인용문이 거짓'과 '인용문에서 과잉 일반화한 결론이 거짓'의 차이가 결정적이다. 표제와 §3.3.4 각주 문구를 후자로 정확히 좁히지 않으면,
    철회 기록 자체가 §3.2 마지막 줄('고쳐지지 않은 결함은 기록이라도 정확해야 한다')이 요구하는 정확도를 어긴다.
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: unverifiable-claim
  severity: low
  description: §3.2 권고가 '근거는 셋이다'라고 선언한 뒤 1번과 3번만 남기고 2번은 같은 자리에서 철회한다(번호도 1,3 으로
    건너뛴다). 살아 있는 근거는 둘인데 문장은 셋이라고 말한다. 결정 문서에서 근거 수가 본문과 불일치하면 나중에 이 결정을 재검토하는 사람이
    사라진 근거를 찾게 된다. '근거는 둘이다'로 고치고 철회된 항목은 별도 각주로 내려야 한다.
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: unverifiable-claim
  severity: low
  description: nexus/a2a/audit.py:27, tests/test_a2a_audit.py:119, init.sql:439, db.py:110
    등 행 번호 고정 인용이 시점 표기 없이 쓰였다. ADR-0008 말미가 채택한 리포 규약은 'Khala 쪽 참조(경로·심볼·행 범위)는 시점
    기록이며 드리프트한다'를 명시하는 것이다. 특히 §1.1 의 등식 근거인 test_a2a_audit.py:119 는 §3.3.3 이 이 유닛에서
    뒤집을 바로 그 단언이라, 문서가 머지되는 순간 인용이 자기 자신에 의해 낡는다. 인용에 '2026-08-14 기준' 문구를 달아야 한다.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-14T14:23:00Z'
---

