---
target: SPEC-nexus-design-corpus-cutover
critiqued_hash: sha256:7f1b2b6051a2c437e56c0f8e0f36f875aa243da754bfa97163b2b8ff29126097
critiqued_at: '2026-08-31T01:30:11Z'
issues:
- issue_id: I-001
  category: unverifiable-claim
  severity: high
  description: §1 의 SQL 은 §1 의 표를 만들어 낼 수 없다. `documents LEFT JOIN chunks` 로 행이 청크
    단위로 불어난 뒤 `sum(CASE WHEN EXISTS(...) THEN 1 ELSE 0 END)` 이 청크 행마다 평가되므로 `docs/`
    의 '정본 있음' 값은 115 가 아니라 1,517 근처가 나온다(문서당 1회가 아니라 청크당 1회). 표의 `115/115 · 6/6 ·
    1/1` 은 이 쿼리의 출력이 아니다. 계수를 두 번 틀렸다고 스스로 적은 SPEC 이 세 번째 계측기도 검증 없이 인용하고 있고, C-1
    의 `122문서 1,582청크` 전체가 이 표에 얹혀 있다.
  status: open
  disposition_reason: null
- issue_id: I-002
  category: unverifiable-claim
  severity: high
  description: '''노션은 이 술어에 안 걸린다''(§1) 와 C-1 의 ''노션을 하나도 안 잡는다'' 는 제시된 측정으로 증명되지
    않는다. 쿼리가 `AND d.source_uri NOT LIKE ''%ext-notion%''` 로 노션 행을 그룹화 **전에** 제거했기
    때문에, 노션 문서 중 `default:docs/…` 접두를 가진 것이 있는지를 이 표는 원리적으로 보여 줄 수 없다. 사본 술어의 거짓양성
    위험이 정확히 그 배제된 집합에 있는데 그 집합을 안 본 채 결론을 냈다.'
  status: open
  disposition_reason: null
- issue_id: I-003
  category: unverifiable-claim
  severity: high
  description: '''전부 정본이 있다''(§1 마지막 칼럼)는 `e.title = d.title` 제목 일치로 판정됐는데, 같은 절의
    ⚠ 문단은 제목 일치를 ''같은 제목의 별개 문서를 못 가른다''며 근거로 기각한다. 그러면서 ''경로 술어는 양방향으로 확인된다(위 표의
    마지막 칸)'' 라고 바로 그 기각된 칸을 검증 근거로 인용한다 — 순환이다. 정본 존재는 rid·source_uri·content_hash
    같은 신원으로 대조돼야 하고, 지금 상태로는 정본 없는 사본을 내릴 위험(설계 문서가 영구 소실)이 열려 있다.'
  status: open
  disposition_reason: null
- issue_id: I-004
  category: missing-invariant
  severity: high
  description: '사본을 **만들어 낸 적재 경로**를 멈추는 조항이 없다. `default` 테넌트로 `docs/·modules/·repo/`
    를 넣던 수집 소스가 그대로면, 다음 적재가 같은 `tenant:filename` 신원으로 upsert 하면서(ADR-0006: documents
    는 제자리 upsert, 이력 없음) 은퇴한 122 문서를 되살리거나 청크를 재활성화한다. 그러면 §2 가 피하려던 정본·사본 겹침 창이 배포
    뒤에 조용히 재생성되고, 아무 완료 조건도 그것을 잡지 못한다(C-2 는 되돌림만, C-5 는 행 생존만 본다).'
  status: open
  disposition_reason: null
- issue_id: I-005
  category: undefined
  severity: high
  description: K-1('근거 조각의 등급 판정은 그 조각의 테넌트 어휘로 내려간다')은 오늘 존재하지 않는 것을 요구한다. 같은 절이
    `classification_level` 은 전역 enum 이라고 적고, §7 은 테넌트별 등급 어휘를 '두 번째 조직이 붙을 때' 로 미룬다.
    전역 enum 하나만 있는 상태에서 '테넌트 어휘로 내려가는 판정' 이 무엇인지 — 값 매핑인지, 조각별 필터 적용 위치인지, 두 테넌트의
    같은 enum 값이 다른 뜻일 때 어느 쪽을 따르는지 — 정의가 없다. P-2 가 이 미정의 조항의 충족을 선행 조건으로 걸어 두어, 무엇을
    하면 충족인지 판정할 수 없다.
  status: open
  disposition_reason: null
- issue_id: I-006
  category: adr-contradiction
  severity: high
  description: '§0.1 backstop 의 자기 판정(''새 검색 채널·인덱스 백엔드·토크나이저/임베딩·커넥터 없음 … 검색 알고리즘은
    그대로다'')이 이 SPEC 자신의 본문과 어긋난다: K-1 은 조각별 등급 판정을 검색 필터 경로에 넣고, §5.3 은 `search_log`
    스키마를 바꾸며, principal 하나가 두 코퍼스를 읽는 것 자체가 검색 범위의 확장이다. §3 의 ''검색 경로 변경 0'' 도 이와
    충돌한다. 게다가 ADR-0008 §3 은 ''게이트는 director 가 발화를 선언하고 SPEC 은 그것을 기록할 뿐, SPEC 이 논증으로
    만들어 내지 않는다'' 고 못박는데, 이 backstop 행은 SPEC 이 스스로 비적용을 논증한 문단이다.'
  status: open
  disposition_reason: null
- issue_id: I-007
  category: adr-contradiction
  severity: medium
  description: ADR-0002 는 debt-servicing 방향마다 'director 가 발화를 선언하고 그 방향의 첫 SPEC 에
    기록한' 수요 신호를 요구하고, ADR-0008 §3.3 이 이를 재확인한다. 이 SPEC 은 ADR-0008 backstop ruling
    만 pending 으로 두었을 뿐, **누가 `design_docs` 를 슬랙에서 필요로 했는지에 대한 관측 신호를 기록하지 않는다.** §5.3
    이 demand-pull 신호 오염을 걱정하면서 정작 이 작업 자체를 당긴 신호는 비어 있다.
  status: open
  disposition_reason: null
- issue_id: I-008
  category: missing-invariant
  severity: medium
  description: 은퇴 행을 남기기로 한 결정(§3 '지운다 아니라 남긴다')이 ADR-0006 의 `v_entropy_signals` 에
    미치는 영향이 다뤄지지 않았다. 사본은 정본과 내용·제목이 같으므로 신호 ②(cross-URI content_hash 충돌)와 ③(정규화 제목
    어간 충돌)이 122쌍을 공존 후보로 계속 센다. 뷰가 `status` 를 거르는지 여부에 대한 불변식도, 확인도 없다. ADR-0006 이
    그 신호를 Slice 2 의 demand-pull 방아쇠로 지정했으므로, 검증 없이 넘어가면 이 배포가 그 방아쇠를 122건만큼 오염시킨다.
  status: open
  disposition_reason: null
- issue_id: I-009
  category: undefined
  severity: medium
  description: §3 이 도입하는 `status='retired'`, `retire_reason='moved_to_tenant'`, `moved_to='design_docs'`
    의 스키마 근거가 없다. ADR-0006 이 기록한 현행 enum 은 `active`/`superseded` 계열이고 `superseded_by`
    만 추가됐다 — `retired` 가 이미 유효한 값인지, enum 확장이 필요한지, `retire_reason`·`moved_to` 컬럼이
    신설인지, 마이그레이션 번호가 무엇인지 어디에도 없다. '오늘의 `status='active'` 필터가 그대로 막는다 · 검색 경로 변경 0'
    이라는 핵심 주장이 이 미확인 전제 위에 서 있고, `status` 를 문자열로 읽는 다른 소비자(웹 렌더·API·리포트)에 대한 조사도 없다.
  status: open
  disposition_reason: null
- issue_id: I-010
  category: untestable-requirement
  severity: medium
  description: §5 의 판정 규칙이 시점별 회차 수를 정의하지 않는다. T0 만 5회 돌려 라벨별 통과율을 내라고 하고, T1·T2 의
    회차 수는 없다. 그러면 '통과율 5/5' 인 T0 와 1회짜리 T2 를 어떤 규칙으로 비교해 C-4 의 '같다' 를 판정하는지가 미정의다(다수결?
    전건 일치? 통과율 차?). 잡음을 range 로 추정하지 말라는 자기 경고를 지키면서도, 정작 비교 통계량을 정의하지 않아 판정이 사후 재량으로
    남는다.
  status: open
  disposition_reason: null
- issue_id: I-011
  category: untestable-requirement
  severity: medium
  description: '''한 번이라도 흔들린 라벨은 판정에서 뺀다''(§5)에 남은 라벨 수의 하한이 없다. 18개 중 다수가 흔들리면 비교
    표본이 한 자리로 떨어지고, 극단적으로 전부 제외되면 C-4(''흔들리지 않는 라벨 기준으로 T2 = T0'')는 공집합 위에서 공허하게 통과한다.
    최소 잔존 라벨 수와, 그 수 미만일 때의 처분(부착 보류)이 사전 등록에 빠져 있다.'
  status: open
  disposition_reason: null
- issue_id: I-012
  category: risky-assumption
  severity: medium
  description: C-3 와 T1 의 추론 — '설계 라벨 셋이 안 떨어지면 술어가 사본을 못 잡은 것' — 은 대안 설명을 배제하지 않는다.
    술어가 정확해도 남은 근거(§1 이 세어 둔 khala 자기 문서 9종 113청크, 노션 문서)로 같은 라벨이 통과할 수 있다. 그러면 술어가
    옳은데도 C-3 가 실패해 SPEC 이 스스로를 막고, 반대로 라벨이 떨어져도 그것이 '사본을 정확히' 잡았다는 증거는 아니다(과잉 삭제도
    똑같이 떨어뜨린다). 술어 검증은 답변 라벨이 아니라 잡힌 행 목록 자체로 해야 한다.
  status: open
  disposition_reason: null
- issue_id: I-013
  category: untestable-requirement
  severity: medium
  description: K-2 의 '두 테넌트의 등급 라벨 부여 정책이 같은지 대조' 에 비교 대상·같음의 기준·산출물이 정의돼 있지 않다. 정책
    문서를 읽는 것인지, 실제 부여된 값 분포를 대조하는 것인지, 같은 enum 값이 두 코퍼스에서 같은 노출 범위를 뜻하는지를 무엇으로 판정하는지
    없다. K-3('불가능하거나 다르면 부착하지 않는다')와 P-2 가 전부 이 미정의 판정에 매달려 있어, 통과·불통과를 사후에 아무렇게나 주장할
    수 있다.
  status: open
  disposition_reason: null
- issue_id: I-014
  category: undefined
  severity: medium
  description: '''제거 먼저'' 와 K-3 의 상호작용에 처분이 없다. K-3 가 ''부착하지 않는다'' 로 나왔을 때 이미 제거를
    진행했다면 설계 문서는 어느 코퍼스에서도 안 나오는 상태로 남는다. P-2 가 선행이라 순서상 피할 수 있다고 읽히지만, 그 경우 §2 의
    ''제거 후'' 시점 T1 측정 자체가 K-3 판정 뒤로 밀린다는 점이 어디에도 적혀 있지 않다. 또한 §2 의 창에 최대 길이·중단 기준·되돌림
    방아쇠가 없다(''DB 갱신 ~ 재기동'' 은 재기동이 실패했을 때의 상한을 주지 않는다).'
  status: open
  disposition_reason: null
- issue_id: I-015
  category: risky-assumption
  severity: low
  description: C-1 이 `122문서 1,582청크` 라는 시점 값을 완료 조건으로 박았다. 라이브 코퍼스이므로 T0 와 컷오버 사이의
    정상적인 재적재·신규 문서만으로도 조건이 깨지고, 그때 술어가 옳은데도 C-1 이 실패하거나(엄격 해석) 숫자를 사후에 고쳐 쓰게 된다(느슨한
    해석). 완료 조건은 고정 숫자가 아니라 '술어가 잡은 집합 = 경로 접두 집합이고 자기 문서·노션과 교집합 0' 같은 불변식이어야 한다.
  status: open
  disposition_reason: null
- issue_id: I-016
  category: scope-creep
  severity: low
  description: §0 이 선언한 일(사본 내리기 + principal 설정 한 줄)에 비해, 이 SPEC 은 문서 수명주기에 새 프리미티브
    두 개(`retire_reason` taxonomy 와 `moved_to` 포인터)와 `search_log` 스키마 변경을 함께 얹는다. 문서
    수명주기는 ADR-0006 이 소유하는 영역이고, 새 사유는 이번 컷오버 한 건이 아니라 앞으로의 모든 테넌트 이동에 쓰이는 일반 기제다.
    '개정이 아니라 사유를 더한다' 는 §3 의 주장은 그 확장을 ADR 처분 없이 SPEC 안에서 처리하겠다는 뜻이 되고, 되돌리기 비싼 스키마
    변경이라 게이트가 필요한 쪽에 가깝다.
  status: open
  disposition_reason: null
approved_by: null
approved_at: null
---

