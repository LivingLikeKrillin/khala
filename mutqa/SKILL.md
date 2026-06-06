---
name: mutqa
description: Use when you want to find weak spots in a Python test suite that advisory review misses — runs cosmic-ray mutation testing on changed modules, triages surviving mutants with a Test Quality Critic subagent (judging from deterministic evidence), and emits an advisory report of real behavioral-test gaps. First consumer = specledger. Requires cosmic-ray installed (Windows-native OK; mutmut is not).
---

# mutqa — 뮤테이션-구동 테스트 품질 하네스 (M1: 어드바이저리)

기존 어드바이저리 리뷰(TDD 스킬, LLM 테스트 리뷰어)가 놓치는 **행위검증 공백**을, 변이가 살아남는지로
**결정론적으로** 드러낸다. M1은 게이트 없이 리포트만 낸다(강제는 M2/M3).

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
- `run_mutation`은 cosmic-ray `init`/`exec`/`dump`를 돌리고 살아남은 변이만 돌려준다. **실패는 예외로
  전파**된다(게이트 fail-open 금지) — 에러가 나면 멈추고 원인을 보고하라, 빈 결과로 위장하지 마라.
- survivor가 0건이면: 변경 모듈의 행위가 현재 스위트로 충분히 고정돼 있다는 뜻 → 리포트에 "갭 없음" 보고하고 종료.

### 2. suite 요약 수집 (Critic 입력용)

```bash
python -m pytest --collect-only -q
```
테스트 **개수**를 세어 `suite_summary` 문자열로 만든다(예: "69개 전부 통과" — 변이 실행 시 스위트가
green이었으므로). M1은 이 거친 요약만 Critic에 전달한다(per-survivor coverage 매핑은 M2).

### 3. survivor마다 Test Quality Critic dispatch (판단 영역)

각 survivor에 대해 `references/critic-prompt.md`의 슬롯(`{module}`, `{lineno}`, `{operator}`,
`{mutation_diff}`, `{suite_summary}`)을 채워 **서브에이전트로 dispatch**한다. survivor들은 서로
독립이므로 병렬로 띄워도 된다. Critic은 `{verdict, rationale, suggested_test_intent}` JSON을 돌려준다.

수집한 verdict를 `Verdict(survivor_key=<survivor.key>, ...)`로 만들어 `verdicts.json`에 저장한다.
(`survivor.key` = `module:lineno:operator`.)

### 4. 어드바이저리 리포트 조립 + 제시

```python
from mutqa.report import build_report
print(build_report(survivors, verdicts))
```
- 리포트 **headline = unwaived real-gap 수**. 변이 점수가 아니다 — equivalent 노이즈에 휘둘리지 않기 위함.
- real-gap이 최상단, equivalent/low-value는 강등되지만 누락되지 않는다.

### 5. real-gap 후속 제안

real-gap마다 Critic의 `suggested_test_intent`를 사용자에게 제시하고 **행위검증 테스트 추가를 권유**한다.
M1은 어드바이저리라 강제하지 않는다 — 결정은 사용자 몫. (강제 게이트 = M3.)

## 품질 회귀

Critic 프롬프트를 수정하면 `references/critic-eval.md`의 골든 케이스(EVAL-1=real-gap,
EVAL-3=low-value)로 회귀 검사하라 — 결정론 증거를 보고 옳게 triage하는지가 이 하네스의 가치 그 자체다.

## 범위 밖 (M1)

게이트(pre-commit 강제), baseline/waiver 원장(동치 영속 흡수), diff 라인 단위 정밀 coverage 매핑 —
전부 M2/M3. 계획서: `docs/superpowers/plans/2026-06-06-mutqa-m1-runner-advisory.md`.
