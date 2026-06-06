# Test Quality Critic — 골든 이밸 케이스

Critic 프롬프트(`critic-prompt.md`)를 바꿀 때마다 **회귀 검사**로 돌리는 고정 케이스.
각 케이스는 입력(변이 증거) + 기대 verdict + 근거로 구성. ground-truth는 specledger PoC에서 옴.

> **실행 방식 (M1):** 수동. 각 케이스의 입력으로 Critic 서브에이전트를 dispatch하고, 반환 verdict가
> 기대와 일치하는지 사람이 확인한다. 자동 이밸 러너는 M2+ (YAGNI).
> **합격 기준 (M1):** EVAL-1 = real-gap, EVAL-3 = low-value 를 반드시 맞춘다. EVAL-2는 Task 9
> dogfood에서 실제 동치 survivor로 확정(아래 폴백 참조).

---

## EVAL-1 — 반드시 `real-gap` (핵심 ground-truth)

specledger `review.py`의 `approve()` 내 disposition 기록 루프 무력화. PoC에서 이 변이는 **69 테스트
전부 green인데도 살아남았다** — 핵심 부수효과(disposition 기록)에 행위검증이 0개라는 결정론적 증거.

- **module:** `src/specledger/review.py`
- **operator:** 루프 무력화 (예: `ReplaceCollectionWithEmpty` 류)
- **mutation diff:**
```
@@ approve() @@
-        for d in dispositions:
-            ledger.record(d)
+        for d in []:
+            ledger.record(d)
```
- **suite outcome:** 69개 전부 통과
- **기대 verdict:** `real-gap`
- **기대 근거 요지:** 변이가 disposition 기록이라는 관측 가능한 부수효과를 통째로 제거했는데 스위트가
  green → 그 부수효과를 검증하는 행위검증이 없다.
- **기대 suggested_test_intent:** "approve()가 각 disposition을 ledger에 기록하는지(기록 호출/결과 상태) 검증."

## EVAL-2 — 반드시 `equivalent` (M1 합성, Task 9에서 실데이터로 확정)

**현재(M1): 합성 케이스.** 도달 불가능한 분기 안의 상수 변경처럼 관측 차이가 없는 변이.

- **module:** `(합성)`
- **mutation diff:**
```
@@ @@
 if False:            # 도달 불가능
-    limit = 100
+    limit = 101
 return compute()     # limit를 쓰지 않음
```
- **suite outcome:** 전부 통과
- **기대 verdict:** `equivalent`
- **기대 근거 요지:** 변경된 분기는 도달 불가능하고 `limit`는 이후 사용되지 않음 → 관측 가능한 행위 차이 0.
- **suggested_test_intent:** `null`

> **▶ Task 9 폴백 규칙:** specledger 실제 실행에서 *깨끗한 동치 survivor*(명확히 관측 차이 없음을
> 논증 가능한 것)를 1건 찾으면 그것으로 이 EVAL-2를 교체해 실데이터 회귀로 고정한다. 못 찾으면
> **위 합성 케이스를 그대로 유지**하고 "합성"임을 명시한다(Task 9가 외부 경험 조건에 막히지 않게).

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
