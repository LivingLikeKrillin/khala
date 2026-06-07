# 운영 1회전 — specledger 17 survivor 전량 triage + 행동 (2026-06-07)

M1 dogfood(2026-06-06)은 17 survivor 중 2건만 triage했다. 이 라운드의 목적은 **채택 리스크를 가장 싸게
검증**하는 것 — "사람이 mutqa 리포트를 받으면 실제로 행동하는가?"를, M2 원장/M3 게이트를 짓기 *전에*
한 번 손으로 돌려 떠본다. (재개 결정 = current-focus 메모의 A안.)

## 절차

- 입력: 보존된 frozen dump `tests/fixtures/cr_dump_specledger.jsonl` (cosmic-ray 재실행 없이 결정론 재현).
- `extract_survivors` → survivor 17건 추출(PoC/M1과 동일 집합 재확인).
- **17건 전량을 독립 Critic 서브에이전트로 병렬 dispatch** (SKILL.md Step 3). 각 Critic은 자기 변이의
  결정론 증거(변이 diff + "69 테스트 전부 green")만 보고 판정 — 합성 편향 차단이 설계 핵심.
- `build_report`로 공식 어드바이저리 리포트 생성.

## triage 결과 — real-gap 14 · equivalent 3

survivor 14건은 **구별되는 행위 갭 2개**로 접힌다 (리포트가 surface한 실제 actionable 작업):

| 갭 | surfaced by (survivor) | 진단 |
|---|---|---|
| **A. 이슈 종료상태/영속 미검증** | line 38 `for[]`, line 41 `!= < <= > >= is is-not not== or`, line 20 `<= >= is-not` (13건) | approve() 후 (a) open 이슈가 disposition+reason으로 갱신되는지, (b) 이미 닫힌 이슈가 보존되는지 — 아무 테스트도 단언 안 함 |
| **B. has_accept 무결성 게이트** | line 33 `is` (1건) | "accepted인데 본문 미수정 → ReviewError" 경로가 True+불변해시 조합으로 실행/식별자-비교 검증된 적 없음 |

equivalent 3건 (Critic이 결정론 증거로 정확히 강등 — 노이즈, M2 원장이 흡수):
- line 33 `<=`: `disp`가 사전 `_VALID` 가드로 {accepted,rejected,deferred} 3값 제약 → `<=`가 `==`와 동일.
- line 47 `is→==`: `art.type`은 항상 enum 싱글톤 → is/== 일치.
- line 47 `is→<=`: 현 2멤버 도메인(ADR="adr"/SPEC="spec")에서 `<= ADR`이 `is ADR`과 동일.
  **단 Critic이 fragility 명시**: 값이 "adr"보다 작게 정렬되는 ArtifactType이 추가되면 깨짐 — 순수
  survivor-count가 놓치는 뉘앙스.

## 행동 — 리포트가 테스트 2개를 specledger에 밀어넣음

리포트 진단을 기존 테스트로 확인: `tests/test_review.py`의 8개 전부 **Artifact의 meta**(status/
approved_by/content_hash)만 단언하고, approve()가 쓰는 **Sidecar 이슈 레코드**(`i.status`,
`i.disposition_reason`)를 단언하는 테스트가 0개 — 갭 A 그대로.

추가한 행위검증 테스트 2개:
- `test_approve_persists_disposition_onto_open_issue` — approve 후 sidecar를 되읽어 open 이슈가
  `rejected`+reason으로 갱신됐는지 단언.
- `test_approve_leaves_already_closed_issue_untouched` — 직전 라운드의 닫힌 이슈(deferred/rejected,
  이번 by_id에 없음)가 open_issues로 유입되지도 덮어써지지도 않는지 단언.

specledger 스위트: **69 → 71 green.**

## 뮤턴트 사망 검증 (surface→test→kill 루프 폐쇄)

대표 뮤턴트를 임시 적용해 신규 테스트가 fail(=kill)하는지 확인 (전부 KILLED, 파일 복원됨):

| 뮤턴트 | 죽인 테스트 |
|---|---|
| line 38 `for i in []` (**골든** — disposition 루프 통째 무력화) | persists_disposition |
| line 41 `Eq_Gt` (open 이슈 절대 미갱신) | persists_disposition |
| line 20 `Eq_LtE` (닫힌 deferred 이슈 과포함) | leaves_already_closed |
| line 20 `Eq_GtE` (닫힌 rejected 이슈 과포함) | leaves_already_closed |

골든 real-gap이 이제 결정론적으로 죽는다 = 가치 가설의 살아있는 증거 1사이클.

## 결론 — "사람이 행동하는가?": YES, 결정적으로. + 보너스 설계 신호

1. ✅ **리포트는 actionable.** 진단이 기존 테스트 독해로 즉시 확증됐고 명백한 수정으로 이어짐.
2. ✅ **Critic triage 정확.** equivalent 3건 정확 강등(헛수고 방지), idx13 fragility 주석 = survivor-count가
   못 주는 가치.
3. ⚠️ **헤드라인 "14 real-gap"은 작업량을 과장한다.** 14 survivor = 행위 갭 2개 + 미루는 미묘한 불변식 1개.
   → **새 설계 신호(plan 미예상):** 사람-대면 리포트는 survivor를 *증거하는 갭 기준으로 클러스터링*해야 한다.
   M2 원장은 survivor 키로 묶지만, 리포트 레이어엔 "behavioral clustering"이 따로 필요.
4. ⚠️ **꼬리:** 신규 2테스트가 대부분을 죽이지만 line41 "by_id에 재등장한 닫힌 이슈 덮어쓰기"(idx4/7 `<=`/`>=`)는
   미사망 — 현실적으로 사람이 미루는 3번째 불변식. 운영의 자연스러운 잔여.

## 다음

- (M2 흡수) equivalent 3건 → 원장 영구 waive. 재실행 시 새 survivor만 재심의.
- (리포트 개선) behavioral clustering — survivor를 진단 갭 단위로 묶어 headline을 "갭 N개"로.
- (specledger) 갭 B 테스트(has_accept 게이트) + 갭 A 꼬리(재제출 닫힌 이슈 보존) 추가는 선택.
