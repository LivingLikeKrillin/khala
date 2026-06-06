# Test Quality Critic — 골든 이밸 케이스

Critic 프롬프트(`critic-prompt.md`)를 바꿀 때마다 **회귀 검사**로 돌리는 고정 케이스.
각 케이스는 입력(변이 증거) + 기대 verdict + 근거로 구성. ground-truth는 specledger PoC에서 옴.

> **실행 방식 (M1):** 수동. 각 케이스의 입력으로 Critic 서브에이전트를 dispatch하고, 반환 verdict가
> 기대와 일치하는지 사람이 확인한다. 자동 이밸 러너는 M2+ (YAGNI).
> **합격 기준 (M1):** EVAL-1 = real-gap, EVAL-3 = low-value 를 반드시 맞춘다. EVAL-2는 Task 9
> dogfood에서 실제 동치 survivor로 확정(아래 폴백 참조).

---

## EVAL-1 — 반드시 `real-gap` (핵심 ground-truth, 실데이터)

specledger `review.py:38` `approve()` 내 **이슈 상태 갱신 루프 무력화**. PoC + 2026-06-06 dogfood에서
이 변이는 **69 테스트 전부 green인데도 살아남았다** — 상태 갱신 부수효과에 행위검증이 0개라는 결정론적 증거.
dogfood에서 Critic이 실제로 `real-gap` 판정함.

- **module:** `src/specledger/review.py`
- **line:** 38
- **operator:** `core/ZeroIterationForLoop`
- **mutation diff:**
```
@@ approve() @@
-    for i in sc.issues:
+    for i in []:
         if i.status == "open" and i.issue_id in by_id:
             i.status = by_id[i.issue_id]["disposition"]
             i.disposition_reason = by_id[i.issue_id].get("reason")
```
- **suite outcome:** 69개 전부 통과
- **기대 verdict:** `real-gap`
- **기대 근거 요지:** 변이가 이슈 status/disposition_reason 갱신이라는 관측 가능한 상태변화를 통째로
  제거했는데 스위트가 green → 그 부수효과를 검증하는 행위검증이 없다.
- **기대 suggested_test_intent:** "approve() 후 각 이슈의 status/disposition_reason이 입력 disposition을 반영하는지 검증."

## EVAL-2 — 반드시 `equivalent` (실데이터 확정, 2026-06-06 dogfood)

**실 cosmic-ray survivor.** specledger `review.py` line 47의 enum 비교 연산자 변이.
Task 9 dogfood에서 깨끗한 동치 survivor로 채집·확정(폴백 발동 안 함). Critic이 실제로 `equivalent` 판정함.

- **module:** `src/specledger/review.py`
- **line:** 47
- **operator:** `core/ReplaceComparisonOperator_Is_Eq`
- **mutation diff:**
```
-    final = Status.ACCEPTED if art.type is ArtifactType.ADR else Status.APPROVED
+    final = Status.ACCEPTED if art.type == ArtifactType.ADR else Status.APPROVED
```
- **suite outcome:** 69개 전부 통과
- **기대 verdict:** `equivalent`
- **기대 근거 요지:** `ArtifactType`은 enum이고 멤버는 싱글톤이라 `is`와 `==`가 항상 일치 →
  관측 가능한 행위 차이 0. (테스트의 잘못이 아님 — 잡을 차이 자체가 없음.)
- **suggested_test_intent:** `null`

## EVAL-3 — 반드시 `low-value`

행위 계약과 무관한 표면(디버그 로그 문자열) 변경.

- **module:** `(예시)`
- **mutation diff:**
```
@@ @@
-    logger.debug("processing item %s", item_id)
+    logger.debug("XXprocessing item %s", item_id)
```
- **suite outcome:** 전부 통과
- **기대 verdict:** `low-value`
- **기대 근거 요지:** 변이는 디버그 로그 문자열만 바꿨다 — 사용자 대면 계약·반환·상태와 무관.
  테스트로 강제할 가치가 낮다.
- **suggested_test_intent:** `null`
