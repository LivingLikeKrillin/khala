# Dogfood 결과 — specledger (2026-06-06)

mutqa M1을 첫 소비자이자 테스트 오라클인 specledger에 통째로 돌린 수용 기록.

## 실행

- 대상: `specledger/src/specledger/review.py` (69 테스트 baseline green)
- config: `mutqa.run.build_config("src/specledger/review.py")`로 생성(하네스 코드경로 실증)
- 사이클: `cosmic-ray init/exec/dump` (8.4.6) → `mutqa.extract.extract_survivors`

## 결과 — 수용 기준 충족

- **변이 63개 중 survivor 17개** — PoC 보고("17개(27%) 생존")와 **정확히 일치**.
- **disposition 기록 루프 무력화 survivor 재현**: line 38 `core/ZeroIterationForLoop`
  (`for i in sc.issues:` → `for i in []:`). 이슈 상태 갱신 루프를 통째로 무력화했는데
  **69 테스트 전부 green** — PoC의 결정적 발견 그대로.
- **스키마 충실성**: 실 dump의 키 집합이 단위테스트 합성 픽스처(`cr_dump_sample.jsonl`)와
  모든 레벨(work_item/mutations[0]/result)에서 일치 확인.

## Critic triage (실 survivor 2건)

| survivor | verdict | 근거 |
|---|---|---|
| line 38 `ZeroIterationForLoop` (disposition 루프 무력화) | **real-gap** ✓ | 상태 갱신 부수효과를 제거했는데 green → 행위검증 0. test intent: "approve() 후 각 이슈 status/disposition_reason이 입력을 반영하는지 검증" |
| line 47 `Is_Eq` (`art.type is ADR` → `==`) | **equivalent** ✓ | enum 멤버는 싱글톤 → is/== 항상 일치, 관측 차이 0 |

→ 골든 이밸 EVAL-1(real-gap)/EVAL-2(equivalent 실데이터 확정)/EVAL-3(low-value, 합성) 통과.

## 어드바이저리 리포트 (headline)

```
# mutqa 어드바이저리 리포트
**unwaived real-gap: 1** · survivor 총 17
- `src\specledger\review.py:38` [real-gap] core/ZeroIterationForLoop   ← 최상단
    - approve()의 이슈 상태 갱신 루프를 통째로 무력화했는데 69 테스트 green
- ... [unknown] x15 (운영 시 전량 triage) ...
- `src\specledger\review.py:47` [equivalent] core/ReplaceComparisonOperator_Is_Eq  ← 강등(누락 X)
```

disposition-loop real-gap이 최상단, equivalent는 강등되나 누락 없음, 미triage는 unknown으로 표시.
(이 데모는 17건 중 2건만 Critic triage — 나머지 15건 전량 triage는 운영 단계. line 41/20의 조건
변이 다수는 "어떤 이슈가 갱신되는지" 미검증인 추가 real-gap 후보.)

## 결론

가치 가설("결정론적 강제가 어드바이저리 리뷰보다 진짜 갭을 잡는다")의 **기술적 전제가 실데이터로
입증됨**: 뮤테이션이 사람+LLM 2단계 리뷰가 놓친 행위검증 공백을 결정론적으로 surface하고, Critic이
결정론 증거로 real-gap과 equivalent 노이즈를 정확히 구분. 남은 검증(채택·강제의 실효)은 M3 게이트 + 실사용.

실 dump 보존: `tests/fixtures/cr_dump_specledger.jsonl` (M2 원장/coverage 작업의 실데이터 기준).
