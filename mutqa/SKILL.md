---
name: mutqa
description: Use when you want to find weak spots in a Python test suite that advisory review misses — runs cosmic-ray mutation testing on changed modules, triages surviving mutants with a Test Quality Critic subagent (judging from deterministic evidence), and emits an advisory report of real behavioral-test gaps. First consumer = specledger. Requires cosmic-ray installed (Windows-native OK; mutmut is not).
---

# mutqa — 뮤테이션-구동 테스트 품질 하네스 (M2: 원장)

기존 어드바이저리 리뷰(TDD 스킬, LLM 테스트 리뷰어)가 놓치는 **행위검증 공백**을, 변이가 살아남는지로
**결정론적으로** 드러낸다. M2는 영속 **원장**(`mutqa-ledger.yaml`)으로 판정을 쌓아 **재실행 시 새
survivor만 재심의**한다(동치 노이즈 재심의 제거). 아직 게이트 없이 리포트만 낸다(강제 bite는 M3).

**핵심 원칙:** 결정론 영역(러너, LLM 없음)과 판단 영역(Critic)을 섞지 않는다. 러너가 산출한
survivor 목록이 유일한 계약. Critic은 "이 변이에도 스위트가 green이었다"는 *측정된 사실*에만 근거해
triage한다 — 이게 순수 LLM 리뷰 대비 차별점.

## 사전 조건

- `cosmic-ray`가 설치돼 있어야 한다(`pip install cosmic-ray`). Windows 네이티브 지원.
- 대상은 git repo이고 테스트 스위트가 green인 상태여야 한다(변이 전 baseline이 통과해야 의미 있음).

## 절차

작업 디렉토리 = 분석 대상 소비자 repo(예: specledger). mutqa 패키지가 import 가능해야 한다
(`pythonpath`에 mutqa의 `src` 추가하거나 설치).

### 1. 변경 모듈 식별 + 변이 실행 → survivor 산출 (결정론, LLM 없음)

```python
from pathlib import Path
import json, dataclasses
from mutqa.scope import changed_source_modules
from mutqa.run import run_mutation

modules = changed_source_modules(base="HEAD~1")   # diff 대상; 전체 분석이면 명시적으로 모듈 지정
survivors = []
for m in modules:
    survivors.extend(run_mutation(module_path=m, workdir=Path(".")))

Path("survivors.json").write_text(
    json.dumps([dataclasses.asdict(s) for s in survivors], ensure_ascii=False, indent=2)
)
```
- `survivors.json`은 **사람이 보는 산출물 아티팩트**다. 후속 단계는 메모리의 `survivors` 객체를 그대로
  쓴다(`asdict`는 `key` 프로퍼티를 직렬화하지 않음). 만약 별도 세션에서 `survivors.json`을 재로드하면
  `.key`가 없으니 **`f"{module}:{lineno}:{operator}"`로 재구성**하라(module은 이미 `/`로 정규화돼 있다 — OS 무관).
- `run_mutation`은 cosmic-ray `init`/`exec`/`dump`를 돌리고 살아남은 변이만 돌려준다. **실패는 예외로
  전파**된다(게이트 fail-open 금지) — 에러가 나면 멈추고 원인을 보고하라, 빈 결과로 위장하지 마라.
- survivor가 0건이면: 변경 모듈의 행위가 현재 스위트로 충분히 고정돼 있다는 뜻 → 리포트에 "갭 없음" 보고하고 종료.

### 2. 원장 로드 + 새 survivor 추림 (M2 — 재심의 최소화)

```python
import datetime
from pathlib import Path
from mutqa.ledger import load_ledger, new_survivors

ledger_path = Path("mutqa-ledger.yaml")
ledger = load_ledger(ledger_path.read_text(encoding="utf-8") if ledger_path.exists() else "")
fresh = new_survivors(survivors, ledger)   # 원장에 없는 것만 = Critic 재심의 대상
```
- **이미 판정된 survivor(`fresh`에 없음)는 Critic을 다시 부르지 않는다** — 동치 노이즈를 매 실행
  재심의하던 비용이 사라진다. 원장의 verdict를 그대로 재사용한다.
- `today`(아래에서 쓸 기준일)는 호출 시점의 날짜로 한 번 정해 둔다(`datetime.date.today()`).
- `fresh`가 0건이면 새로 판정할 게 없다 → 곧장 리포트(6단계)로. survivor 자체가 0건이면 "갭 없음" 종료.

### 3. suite 요약 수집 (Critic 입력용)

```bash
python -m pytest --collect-only -q
```
테스트 **개수**를 세어 `suite_summary` 문자열로 만든다(예: "69개 전부 통과" — 변이 실행 시 스위트가
green이었으므로). 이 거친 요약을 Critic에 전달한다(per-survivor coverage 매핑은 향후 작업).

### 4. **새** survivor마다 Test Quality Critic dispatch (판단 영역)

`fresh`의 각 survivor에 대해 `references/critic-prompt.md`의 슬롯(`{module}`, `{lineno}`, `{operator}`,
`{mutation_diff}`, `{suite_summary}`)을 채워 **서브에이전트로 dispatch**한다. survivor들은 서로
독립이므로 병렬로 띄워도 된다. Critic은 `{verdict, rationale, suggested_test_intent}` JSON을 돌려준다.

수집한 verdict를 `Verdict(survivor_key=<survivor.key>, ...)` 리스트로 만든다.
(`survivor.key` = `module:lineno:operator`.)

### 5. verdict를 원장에 흡수 + 영속 (M2)

```python
from mutqa.ledger import absorb, dump_ledger

ledger = absorb(ledger, fresh_verdicts, today)        # 새 판정을 원장에 기록(불변)
ledger_path.write_text(dump_ledger(ledger), encoding="utf-8")   # mutqa-ledger.yaml 커밋 대상
```
- **이 파일은 커밋된다** — 판정 기록이 소스와 함께 버전관리된다. equivalent/low-value는 영구 waive,
  real-gap은 surface 유지(사람이 `waived_until`을 손으로 달면 만료까지만 침묵).
- `absorb`는 사람이 손으로 단 `waived_until`을 덮지 않는다(기존 항목 보존).

### 6. 어드바이저리 리포트 조립 + 제시

```python
from mutqa.report import build_report
print(build_report(survivors, ledger, today))
```
- **headline = 무는(unwaived) real-gap 수** = `biting(survivors, ledger, today)` 길이. 변이 점수가 아니다.
- real-gap이 최상단, equivalent/low-value/유예된 real-gap은 강등되지만 누락되지 않는다(`[real-gap (waived)]` 표시).

### 7. real-gap 후속 제안

무는 real-gap마다 Critic의 `suggested_test_intent`를 사용자에게 제시하고 **행위검증 테스트 추가를
권유**한다. M2도 아직 어드바이저리라 강제하지 않는다 — 결정은 사용자 몫. (강제 게이트 = M3.)

## 품질 회귀

Critic 프롬프트를 수정하면 `references/critic-eval.md`의 골든 케이스(EVAL-1=real-gap,
EVAL-3=low-value)로 회귀 검사하라 — 결정론 증거를 보고 옳게 triage하는지가 이 하네스의 가치 그 자체다.

## 범위 밖 (M2 현재)

**게이트(pre-commit 강제)** = M3 — `biting(survivors, ledger, today)`가 그 입력이다(무는 real-gap이 있으면
커밋 실패). diff 라인 단위 정밀 coverage 매핑, survivor의 behavioral clustering(동일 갭을 증거하는 변이 묶기)도
향후 작업. 계획서: `docs/superpowers/plans/2026-06-06-mutqa-m1-runner-advisory.md`(M1; M2/M3은 spec §5–6).
