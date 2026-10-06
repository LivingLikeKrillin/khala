# 4개 협력 저장소 공통 용어 사전 및 소유권 정의

검색 및 응답 API(Nexus API)를 제공하는 `khala`, 로봇을 실행하며 승인 엔드포인트(`POST /approvals`), 익스포트 번들, 작업 결과 보고서를 제공하는 `picasso`, 진단 에피소드를 실행하며 `narrator`와 교환하는 진단 계약을 정의하는 `koshchei`, 그리고 이 셋을 모두 소비하는 `narrator`의 4개 저장소가 상호 협력한다. 2026-10-05 오너의 지시로 4개 저장소가 용어 검토를 진행하여 Gemini가 사전을 초안 작성했고, 2026-10-06 둘 이상의 저장소에서 사용하는 용어를 취합하여 Gemini가 각 항목의 공통 용어를 결정했다. 결정된 항목은 저장소 경계를 넘나드는 필드, 타입, enum, 컬럼 명칭인 계약 용어 A01-A34, 여러 저장소가 공유하는 개념인 B01-B29, 저장소마다 의미가 다른 어휘인 C01-C08의 세 그룹으로 나뉜다.

## 1. 역할 및 소유권 정의

| 소유 대상 | 소유자 | 비고 |
|---|---|---|
| 공통 용어 사전 및 변경 절차 | `khala` | 본 문서 및 변경 절차 관리 |
| 모든 결정 | 오너 | 모든 최종 결정권 보유 |
| Nexus API 계약 용어 | `khala` | 계약 생산자 |
| `picasso` 승인 엔드포인트(`POST /approvals`), 익스포트 번들, 작업 결과 보고서 계약 용어 | `picasso` | 계약 생산자 |
| 진단 계약 용어 | `koshchei` | 계약 생산자 |

계약 용어 명칭의 소유권은 해당 계약을 생산하는 저장소에 있다.

## 2. 중복 작업 방지

- 각 저장소는 공통 용어 결정을 독자적으로 재수행하지 않고 본 목록의 항목을 Gemini에게 다시 질의하지 않으며, 신규 공통 용어 제안과 사실관계 오류를 `khala`에 전달한다.
- 계약 용어의 이름 변경은 생산자만이 계획하며, 소비자는 해당 변경이 자신의 쪽에 미치는 영향 목록을 생산자에게 전달한다.
- 각 저장소는 결정된 B 및 C 그룹 용어를 자체 문서에 적용한다.
- 단일 저장소에서만 사용하는 용어는 해당 저장소의 자체 검토에 유지한다.

## 3. 변경 절차

1. 저장소가 `khala`에 제안이나 사실관계 오류를 전달한다.
2. `khala`는 사실관계와 잘못된 점만을 명시하여 Gemini에게 다시 질의한다.
3. `khala`는 Gemini의 답변을 오너에게 보고한다.
4. 오너가 결정을 내린다.
5. `khala`는 이 문서를 갱신하고 다른 세 저장소에 알린다.

## 4. 오너 판단 항목

2026-10-06 오너 결정에 따라 본 섹션의 오너 판단 항목은 Gemini의 결정을 그대로 채택한다.

- C01: `khala`의 `vouch`는 엔지니어 서약으로 변경되고 `picasso`는 보증을 유지하며, 서약은 기존에 4개 저장소 어디에서도 사용되지 않았고 현재 `khala`는 `vouch`를 71회, 보증을 23회 사용하고 있으나 결정대로 채택한다.
- B16: `khala` 자체 사전에는 해당 개념이 근거 패킷으로 기재되어 있었으나 공유 결정이 근거 묶음이므로 `khala` 자체 항목을 변경한다.
- B05: `picasso` 자체 사전은 표면을 유지하고 있었고(`picasso`에서 오너 판단 대기 중), `khala`는 서피스, `narrator`는 인터페이스를 사용했으나 공유 결정인 API 표면으로 세 저장소 모두 변경한다.
- 그룹 A 계약 명칭 변경: 4개 저장소의 생산자와 소비자를 함께 이전하는 별도 계획이 먼저 승인되어야 한다는 2026-10-06 소유자 결정에 따라 모두 보류되며, `narrator`는 자체 사전에서 여러 항목을 변경 없이 유지했으나 공유 결정에서 이들이 변경되었고 전체 목록은 표에 기재되어 있다.
- A18: `WITHHELD`는 `picasso`의 해결책 탐색 결과 값과 승인 응답의 거절 값이라는 두 가지 의미를 가지며, Gemini는 `WITHHELD_HUMAN_FIRST`를 `MANUAL_DIAGNOSIS_REQUIRED`로 변경하고 거절 값 `WITHHELD`는 유지했으나 해결책 탐색 결과 값에는 별도 이름을 부여하지 않았으므로 두 의미는 하나의 이름 아래 유지된다.
- A20: `koshchei`가 `episode_id` 컬럼을 가지고 있지 않음을 확인했으므로 새 이름은 충돌하지 않는다(2026-10-06).
- B11: `picasso` 세션의 2026-10-06 오너 결정에 따라 `picasso`는 등록된 로봇 1대(등록, 결속, 명령의 단위)와 일반적인 로봇 사이의 경계를 유지하기 위해 기체를 유지하고, 기체에서 로봇으로의 공유 결정은 `narrator`와 `koshchei`에만 적용되며, 동일한 결정에 의해 `picasso` 자체 용어인 적재, 관문, 소모, 소모 기록, 결속은 그대로 유지된다.

## 5. 공통 용어 의사결정 표

2026-10-06 오너 결정에 따라 4개 저장소의 생산자와 소비자가 함께 이동하는 별도 계획이 먼저 승인되어야 하므로 그룹 A의 계약 용어 이름 변경은 보류한다. 문서와 산문에는 그룹 B 및 C의 공유 결정 사항을 적용하며, 섹션 4의 오너 판단 항목은 Gemini의 결정을 원안대로 채택한다.

재질의 컬럼의 1, 2, 3 값은 Gemini에 제공된 사실관계가 부정확하거나 불완전하여 어떤 단어를 선택할지가 아니라 무엇이 잘못되었는지만을 명시해 다시 질의한 차수를 나타낸다. 1차 재질의는 최초 답변 이후 8개 항목을 대상으로 진행했으며, 그중 5개는 `khala` 자체의 요청에서 사실관계를 잘못 기재했기 때문이었다. 2차 재질의는 `picasso`가 보고한 5개 항목을 대상으로 진행했다. 3차 재질의는 `koshchei`와 `picasso`가 보고한 7개 항목을 대상으로 진행했다.

### 5.1 저장소 간 연계 계약 용어 (명칭 변경 보류)

그룹 A의 계약 용어 이름 변경은 4개 저장소의 생산자와 소비자가 함께 이동하는 별도 계획이 먼저 승인되어야 하므로 보류한다.

| 항목 ID | 연계 방향 | 현재 명칭 -> 공통 명칭 | 제안 사유 | 재질의 |
|---|---|---|---|---|
| A01 | khala -> narrator | `chunk_rid` → `chunk_id` | 문서 청크의 식별자는 업계 표준인 chunk_id를 사용하는 것이 자연스럽습니다. |  |
| A02 | narrator -> khala | `identifier_channel (request)` → `enable_identifier_channel`<br>`identifier_channel (response)` → `identifier_channel` | 요청 플래그와 응답 필드가 동일한 이름을 공유하므로 요청은 enable_identifier_channel로 변경하여 두 개념을 명확히 분리해야 합니다. |  |
| A03 | khala -> narrator | `identifier_channel_asked` → `identifier_channel_requested` | API 계약에서 요청 여부를 나타내는 불리언 필드는 구어체인 asked보다 업계 표준인 requested가 적합합니다. |  |
| A04 | narrator -> khala | `fusion_doc_agreement` → `fusion_doc_agreement` (유지) | 요청, 응답, 저장소 전반에서 동일한 기능 플래그 개념을 공유하므로 기존 이름인 fusion_doc_agreement를 유지하는 것이 최선입니다. |  |
| A05 | khala -> narrator | `answer_context_len` → `answer_context_length` | 축약어 len 대신 전체 단어인 answer_context_length를 사용하는 것이 표준 API 명명 관례에 부합합니다. |  |
| A06 | khala -> narrator | `provenance_mark` → `provenance_label` | 사람이 읽을 수 있는 표시 문자열에는 mark 대신 업계 표준인 provenance_label이 적합합니다. |  |
| A07 | koshchei/narrator -> picasso | `approverKind` → `approverType` | 승인 주체 유형 분류에는 다수 저장소가 제안하고 JSON 스키마 관례에 부합하는 approverType을 사용하는 것이 자연스럽습니다. |  |
| A08 | picasso -> narrator/koshchei | `refusal` → `rejection` | 승인(approval) 워크플로에서 거절 사유 객체는 표준 용어인 rejection을 사용하는 것이 바람직합니다. |  |
| A09 | picasso -> narrator/koshchei | `wallClockAt` → `wallClockTime` | 시뮬레이션 환경의 가상 시간과 대칭을 이루는 실제 시간 필드로 업계 표준인 wallClockTime이 적합합니다. |  |
| A10 | picasso -> narrator/koshchei | `virtualNow` → `virtualTime` | 영속화되는 로그 기록에서 상대적 표현인 Now 대신 wallClockTime과 대칭을 이루는 virtualTime이 적합합니다. |  |
| A11 | picasso -> narrator/koshchei | `activeUntilKind` → `activeUntilType` | 조건 유형 분류에는 Kind 대신 스키마 표준 접미사인 Type(activeUntilType)을 사용하는 것이 좋습니다. |  |
| A12 | koshchei -> picasso | `ApprovalHost` → `ApprovalEndpoint`<br>`ApprovalWindow` → `ApprovalClient`<br>`HttpApprovalWindow` → `HttpApprovalClient` | 서버 측 HTTP 엔드포인트와 호출용 클라이언트 인터페이스 및 구현체를 역할에 맞게 분리했습니다. | 3 |
| A13 | picasso -> koshchei | `instanceId` → `picassoInstanceId` | koshchei의 에피소드 instanceId와의 이름 충돌을 방지하기 위해 프로세스 인스턴스 ID를 picassoInstanceId로 명확히 구분해야 합니다. |  |
| A14 | picasso -> koshchei/narrator | `units` → `units` (유지)<br>`approvedUnits` → `approvedUnits` (유지)<br>`unitId` → `unitId` (유지) | unitId는 실행 단위 식별자로 완료 목록 매칭에 사용되며 units와 approvedUnits도 실행 단위를 가리키므로 기존 이름을 유지합니다. | 2 |
| A15 | picasso -> koshchei/narrator | `runId` → `exportRunId` | Temporal의 워크플로 runId와의 혼동을 피하기 위해 picasso의 내보내기 실행 ID는 exportRunId로 명시해야 합니다. |  |
| A16 | picasso -> koshchei/narrator | `bundle` → `bundle` (유지)<br>`export` → `bundle`<br>`LedgerExport` → `bundle`<br>`manifest` → `manifest` (유지) | 내보내기 디렉터리는 bundle로 통일하고 내부의 레코드 수 목록 파일은 manifest로 분리하여 명명합니다. | 1 |
| A17 | picasso -> koshchei | `evidence` → `jobResponse`<br>`Evidence` → `JobResponse`<br>`EvidenceArrived` → `JobResponseArrived`<br>`JobResponse` → `JobResponse` (유지) | 실행 작업 결과 보고서라는 의미를 정확히 전달하고 검색 증거(evidence) 개념과의 혼동을 피하기 위해 jobResponse로 통일합니다. |  |
| A18 | picasso -> koshchei | `WITHHELD_HUMAN_FIRST` → `MANUAL_DIAGNOSIS_REQUIRED`<br>`WITHHELD` → `WITHHELD` (유지) | 치료 탐색을 보류하고 사람 진단을 우선하는 사유는 MANUAL_DIAGNOSIS_REQUIRED로 지정하고 승인 응답의 거절 사유는 WITHHELD로 분리했습니다. | 3 |
| A19 | koshchei <-> narrator, koshchei -> picasso | `sawCandidatesVersion` → `observedCandidatesVersion`<br>`sawSkillTypes` → `observedSkillTypes` | 구어체 saw 대신 분산 제어 시스템에서 관측된 버전을 나타내는 표준 접두사 observed를 사용하는 것이 자연스럽습니다. |  |
| A20 | koshchei <-> narrator | `episode_instance_id` → `episode_id`<br>`episodeId` → `episodeId` (유지)<br>`instanceId` → `episodeId` | Postgres 컬럼은 snake_case 규칙에 따라 episode_id로 지정하고 JSON과 코드 필드는 camelCase인 episodeId로 정의했습니다. | 3 |
| A21 | koshchei <-> narrator | `ref` → `ref` (유지) | 객체 참조를 나타내는 데 소프트웨어 업계 전반에서 통용되는 간결하고 표준적인 ref를 유지하는 것이 최선입니다. |  |
| A22 | koshchei <-> narrator/picasso | `approverId` → `approverId` (유지)<br>`operatorId` → `operatorId` (유지)<br>`X-Koshchei-Operator` → `X-Koshchei-Operator` (유지) | 승인 주체는 사람과 에이전트를 모두 포함하므로 approverId를 사용하고 사람으로 한정되는 운영자는 operatorId와 관련 헤더를 유지합니다. | 2 |
| A23 | narrator -> koshchei | `DiagnosisOutcome` → `DiagnosisOutcome` (유지) | 진단 생성의 분류 결과(outcome)와 후속 판정(verdict) 단계의 책임을 분리하기 위해 DiagnosisOutcome을 유지하는 것이 좋습니다. |  |
| A24 | koshchei, narrator | `judge` → `classifyDiagnosis`<br>`judgeDiagnosis` → `validateDiagnosis` | 진단을 결과별로 분류하는 narrator 단계는 classifyDiagnosis로, 수신된 진단을 검증하는 koshchei 단계는 validateDiagnosis로 분리합니다. | 1 |
| A25 | koshchei -> narrator | `CHOOSE_SOURCE` → `CHOOSE_PICKUP_LOCATION` | 추상적인 SOURCE보다 대체 픽업 위치를 선택한다는 비즈니스 의미가 명확한 CHOOSE_PICKUP_LOCATION이 적합합니다. |  |
| A26 | koshchei -> narrator | `CandidateKind.ESCALATE` → `CandidateKind.ESCALATE_TO_OPERATOR`<br>`ESCALATE` → `ESCALATE_TO_OPERATOR`<br>`ESCALATE_ID` → `ESCALATE_TO_OPERATOR_ID` | 판정 결과 및 워크플로 단계와의 명칭 충돌을 피하고 운영자 이관 선택지임을 명확히 나타내기 위해 ESCALATE_TO_OPERATOR가 적합합니다. |  |
| A27 | koshchei -> narrator | `closedAs` → `closedAs` (유지)<br>`SUPERSEDED` → `PRECONDITION_FAILED` | 전제 조건이 거짓으로 판명된 종료 사유는 오해를 부르는 SUPERSEDED 대신 PRECONDITION_FAILED가 정확하며 필드명은 closedAs를 유지합니다. |  |
| A28 | narrator -> koshchei | `card` → `guidance` | UI 위젯 용어인 card 대신 작업자 지침이라는 도메인 의미를 나타내고 하위 타입 GuidanceLine과 일치하는 guidance가 적합합니다. |  |
| A29 | koshchei -> narrator | `outcome` → `outcome` (유지) | 작업 결과 보고서의 완료 상태를 나타내므로 camelCase 형식의 outcome을 표준 이름으로 유지합니다. | 1 |
| A30 | koshchei -> narrator | `unknown` → `unobservedCondition`<br>`unknowns` → `unobservedConditions`<br>`Unknown` → `UnobservedCondition`<br>`UnknownWhat` → `UnobservedConditionType` | 시스템이 관측할 수 없어 물리 동작이 차단된 상태임을 명확히 설명하는 UnobservedCondition이 적합합니다. |  |
| A31 | koshchei -> narrator | `projection` → `projection` (유지)<br>`projectCandidates` → `projectCandidates` (유지)<br>`projectionVersion` → `projectionVersion` (유지) | 에피소드 스냅샷으로부터의 순수 매핑 함수이자 버전 관리 대상이므로 함수형/CQRS 표준 용어인 projection을 유지하는 것이 최선입니다. |  |
| A32 | koshchei -> narrator | `ApprovalRecordResult` → `ApprovalResult`<br>`ApprovalResult` → `ApprovalResult` (유지)<br>`REVOKED` → `POLICY_INVALIDATED` | 동일한 승인 결과 개념을 단일 enum인 ApprovalResult로 통합하고 정책 변경에 따른 무효화를 POLICY_INVALIDATED로 명확히 표현합니다. |  |
| A33 | narrator -> koshchei | `clean` → `grounded`<br>`requireClean` → `requireGrounded` | 모든 문장에 근거 인용이 있고 검증되었음을 뜻하는 AI 도메인의 표준 용어인 grounded(requireGrounded)가 적합합니다. |  |
| A34 | picasso -> koshchei/narrator | `grade` → `evidenceLevel` | 피카소의 근거 세기 값에 현장 확인 항목을 포함하는 수신 측 필드이므로 단계적 수준을 나타내는 evidenceLevel로 명명했습니다. | 3 |

### 5.2 저장소 간 공통 개념 용어

| 항목 ID | 현재 한국어 용어 | 동일 개념 여부 판정 | 저장소별 표준 용어 | 제안 사유 | 재질의 |
|---|---|---|---|---|---|
| B01 | 사건 / 사건 번들 | 같은 개념 | picasso: 인시던트, koshchei: 인시던트, khala: 인시던트 | 세 저장소 모두 시스템 장애 및 실패 단위를 나타내는 incident를 의미하므로 표준 개발 용어인 인시던트로 통일한다. |  |
| B02 | 판(버전 표시) | 같은 개념 | picasso: 버전, narrator: 버전, koshchei: 버전, khala: 버전 | 모든 저장소에서 스키마, 계약, 코퍼스, 컴포넌트 등의 버전 번호를 가리키므로 버전으로 통일한다. |  |
| B03 | 판 칸 | 같은 개념 | khala: 버전 필드, narrator: 버전 필드, koshchei: 버전 필드 | 모든 저장소에서 응답에 포함되는 버전 관련 메타데이터 필드들을 의미하므로 동일하게 버전 필드로 통일합니다. | 1 |
| B04 | 층 | 같은 개념 | picasso: 계층, narrator: 계층, khala: 계층 | 세 저장소 모두 시스템 및 아키텍처의 layer를 가리키므로 표준 소프트웨어 공학 용어인 계층으로 통일한다. |  |
| B05 | 표면 | 같은 개념 | picasso: API 표면, narrator: API 표면, khala: API 표면 | 세 저장소 모두 외부에 공개되는 인터페이스 및 엔드포인트 집합인 API surface를 가리킨다. |  |
| B06 | 정본 | 같은 개념 | picasso: 정본, koshchei: 정본, khala: 정본 | 세 저장소 모두 기준이 되는 권위 있는 원본인 canonical source를 가리키므로 정본으로 통일한다. |  |
| B07 | 대장 | 다른 개념 | khala: 서신 결함 인덱스, narrator: 서신 결함 인덱스, picasso: 레지스터, koshchei: 피카소 레저 | 저장소별로 가리키는 대상이 서신 결함 인덱스 문서, 시스템 레지스터, 피카소 이력 레저로 서로 다르므로 용어를 분리합니다. | 1, 3 |
| B08 | 선언 · 자격 | 다른 개념 | picasso: 선언 및 자격, narrator: 자동 승인 자격, koshchei: 승인자 목록, khala: 명시적 선언 | picasso는 명시적 선언과 자동 승인 권한, narrator는 자동 승인 자격, koshchei는 승인자 ID 목록, khala는 컴포넌트 필수 실행 선언을 의미하여 서로 다르다. |  |
| B09 | 판정 | 같은 개념 | picasso: 판정, koshchei: 판정, khala: 판정 | 세 저장소 모두 규칙이나 기준에 따라 수락·거절이나 통과 여부를 결정하는 일인 verdict를 가리키므로 판정으로 통일한다. |  |
| B10 | 승인 창구 / 창구 | 같은 개념 | koshchei: 승인 엔드포인트, picasso: 승인 엔드포인트, narrator: 승인 엔드포인트 | 피카소의 승인 HTTP 엔드포인트를 호출하거나 제공하는 공통 대상을 가리키므로 승인 엔드포인트로 통일합니다. | 1, 3 |
| B11 | 기체 | 같은 개념 | picasso: 로봇, narrator: 로봇, koshchei: 로봇 | 세 저장소 모두 제어 및 진단 대상인 개별 로봇 개체를 가리키므로 로봇으로 통일한다. |  |
| B12 | 실물 | 다른 개념 | picasso: 실제 하드웨어, narrator: 실제 서비스, koshchei: 실환경 실행 | picasso는 실제 하드웨어 장비, narrator는 모의 객체가 아닌 실제 서비스, koshchei는 실제 환경에서의 실행 경로를 의미하므로 구분한다. |  |
| B13 | 신원 | 같은 개념 | picasso: 식별 정보, narrator: 식별 정보, khala: 식별 정보 | 세 저장소 모두 호출 주체, 계약, 문서 등을 식별하는 identity를 가리키므로 식별 정보로 통일한다. |  |
| B14 | 주 변수 · 부 변수 | 다른 개념 | 주 변수: 1차 결과 변수, 부 변수: 2차 결과 변수 | 처치 판정의 기준이 되는 1차 결과 변수와 보조적으로 보고되는 2차 결과 변수를 명확히 분리하여 정의합니다. | 1 |
| B15 | 식별자 채널 | 같은 개념 | narrator: 식별자 채널, khala: 식별자 채널 | 두 저장소 모두 쿼리 내 식별자를 전용으로 검색하는 선택적 검색 경로를 가리킨다. |  |
| B16 | 근거 묶음 · 꾸러미 · 묶음 | 같은 개념 | narrator: 근거 묶음, koshchei: 근거 묶음, khala: 근거 묶음 | 세 저장소 모두 답변 생성을 뒷받침하기 위해 검색된 근거 스니펫 묶음을 가리킨다. |  |
| B17 | 검색 글 · 질문 자리 · 자료 칸 | 같은 개념 | khala: 검색 텍스트, 쿼리, 답변 컨텍스트, narrator: 검색 텍스트, 쿼리, 답변 컨텍스트 | 두 저장소 모두 khala 답변 API의 세 요청 필드를 가리키므로 표준 개발 용어로 통일한다. |  |
| B18 | 후보 밖 | 같은 개념 | narrator: 후보 외 선택, koshchei: 후보 외 선택 | 두 저장소 모두 시스템이 제시된 후보 목록에 없는 대안을 선택하거나 권고한 상황을 가리킨다. |  |
| B19 | 탐색 줄 | 같은 개념 | narrator: 조치 탐색 기록, koshchei: 조치 탐색 기록 | 두 저장소 모두 picasso의 번들 내 조치 탐색 결과를 기록한 항목을 가리킨다. |  |
| B20 | 열쇠 | 다른 개념 | picasso:lookup: 조회 키, picasso:idempotency: 멱등성 키, narrator: 요청 해시 | picasso의 레코드 조회 키와 멱등성 키 및 narrator의 요청 그룹화 해시는 서로 다른 목적의 값이므로 분리합니다. | 2 |
| B21 | 결과 통보 | 같은 개념 | picasso: 작업 응답, koshchei: 작업 응답 | 두 저장소 모두 picasso의 작업 실행 결과를 상위로 알리는 메시지인 JobResponse를 가리킨다. |  |
| B22 | 주문 | 같은 개념 | picasso: 작업 지시, koshchei: 작업 지시 | 두 저장소 모두 상위 시스템이 로봇에 내리는 작업 요청인 JobOrder를 가리키므로 작업 지시로 통일한다. |  |
| B23 | 인계 | 다른 개념 | picasso:handoff: 핸드오프, picasso:handover: 공정 간 인계, koshchei: 운영자 인계 | 아티팩트 전달인 핸드오프와 물리적 공정 간 인계 및 koshchei의 운영자 인계는 서로 다른 대상과 목적을 가지므로 분리합니다. | 2 |
| B24 | 접수 | 다른 개념 | picasso: 작업 수락, koshchei: 증상 수신 | picasso는 로봇이나 미들웨어가 작업 요청을 수락한 상태를, koshchei는 감시기가 결함 증상을 수신한 동작을 의미하므로 구분한다. |  |
| B25 | 미결 · 열림 · 열린 항목 | 같은 개념 | picasso: 오픈 항목, khala: 오픈 항목 | 두 저장소 모두 사양서나 문서에서 아직 종결되지 않고 후속 조치를 기다리는 open items를 가리킨다. |  |
| B26 | 갈래 | 같은 개념 | picasso: 하위 범주, narrator: 하위 범주, khala: 하위 범주 | 세 저장소 모두 대분류 내의 세부 분류 케이스나 분기를 가리키므로 하위 범주로 통일한다. |  |
| B27 | 가드 | 다른 개념 | narrator: 가드레일 지표, khala: 가드 검사 | narrator는 모델 채택의 제약 조건이 되는 지표를, khala는 오류를 기계적으로 차단하는 검사 장치를 의미하므로 구분한다. |  |
| B28 | 낱말 | 다른 개념 | picasso: 용어, narrator: 단어 | picasso는 용어집에 정의된 표준 용어를 의미하고, narrator는 자연어 처리 및 검색 대상인 개별 단어를 의미하므로 구분한다. |  |
| B29 | 축 | 같은 개념 | picasso: 차원, narrator: 차원, khala: 차원 | 세 저장소 모두 시스템 분류나 측정 조건의 독립적인 기준을 나타내는 차원을 가리킨다. |  |

### 5.3 저장소별 다의어 용어

| 항목 ID | 현재 용어 | 저장소 및 의미별 표준 용어 | 제안 사유 | 재질의 |
|---|---|---|---|---|
| C01 | 보증 | khala: 엔지니어 서약, picasso: 보증 | khala의 보증은 엔지니어 서약이고 picasso의 보증은 일반적인 시스템 보증을 뜻하므로 분리합니다. | 2 |
| C02 | 카드 | khala: 코드 카드, narrator: 답변 카드, koshchei: 오퍼레이터 카드 | 각 저장소의 카드가 코드 심볼 요약, 정형화된 답변 출력, 운영 조치 정보를 담는 용도로 서로 다르므로 분리합니다. | 3 |
| C03 | 판독 | khala: 기계 판독, narrator: 인간 평가 | khala는 이미지를 텍스트로 변환하는 기계 판독을, narrator는 사람이 직접 답변을 읽고 채점하는 수동 평가를 의미한다. |  |
| C04 | 조각 | khala: 청크, narrator: 코드 모듈 | khala는 색인 및 검색 단위인 문서 청크를, narrator는 시스템을 구성하는 코드 모듈을 의미한다. |  |
| C05 | 강등 | khala: 검색 경로 저하, picasso: 자동 승인 자격 박탈 | khala는 검색 경로 실패로 인한 서비스 부분 저하 상태를, picasso는 승인자의 자동 승인 권한 박탈을 의미한다. |  |
| C06 | 근거 | khala: 검색 근거, koshchei: 실행 증빙 | khala는 답변 생성을 뒷받침하는 검색 근거를, koshchei는 작업 완료를 증명하는 실행 결과 보고를 의미한다. |  |
| C07 | verdict | narrator: 진단 판정 로직, koshchei: 검증 판정 결과 | narrator는 진단을 네 가지 결과로 분류하는 내부 판정 로직을, koshchei는 진단 검증 및 에피소드 진행 판정 결과를 의미한다. |  |
| C08 | 판 | version: 버전, run: 실행 | 판의 두 가지 의미를 스키마나 규약의 버전과 측정이나 실험의 1회 실행으로 분리하여 정의합니다. | 1 |
