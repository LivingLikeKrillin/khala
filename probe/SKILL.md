---
name: probe
description: Use when you want to find weak spots in a Python test suite that advisory review misses — runs cosmic-ray mutation testing on changed modules, triages surviving mutants with a Test Quality Critic subagent (judging from deterministic evidence), and emits an advisory report of real behavioral-test gaps. First consumer = Arbiter. Requires cosmic-ray installed (Windows-native OK; mutmut is not).
---

# Probe — 뮤테이션-구동 테스트 품질 하네스 (M2: 원장)

기존 어드바이저리 리뷰(TDD 스킬, LLM 테스트 리뷰어)가 놓치는 **행위검증 공백**을, 변이가 살아남는지로
**결정론적으로** 드러낸다. M2는 영속 **원장**(`probe-ledger.yaml`)으로 판정을 쌓아 **재실행 시 새
survivor만 재심의**한다(동치 노이즈 재심의 제거). 아직 게이트 없이 리포트만 낸다(강제 bite는 M3).

**핵심 원칙:** 결정론 영역(러너, LLM 없음)과 판단 영역(Critic)을 섞지 않는다. 러너가 산출한
survivor 목록이 유일한 계약. Critic은 "이 변이에도 스위트가 green이었다"는 *측정된 사실*에만 근거해
triage한다 — 이게 순수 LLM 리뷰 대비 차별점.

## 사전 조건

- `cosmic-ray`가 설치돼 있어야 한다(`pip install cosmic-ray`). Windows 네이티브 지원.
- 대상은 git repo이고 테스트 스위트가 green인 상태여야 한다(변이 전 baseline이 통과해야 의미 있음).

## 절차

작업 디렉토리 = 분석 대상 소비자 repo(예: Arbiter). `probe` CLI 가 설치돼 있거나(`pip install -e
probe/`) `khala.probe` 가 `pythonpath` 에 있어야 한다(`python -m khala.probe.cli`).

세 단계다: **`probe survey`**(결정론) → **Critic dispatch**(판단, CLI 밖) → **`probe absorb`**(흡수).
파이썬 블록을 손으로 붙여넣지 않는다 — 러너·원장·리포트는 CLI 안에 있고, CLI 가 할 수 없는 유일한
단계(Critic dispatch)만 손으로 한다. 그게 결정론/판단 분리를 명령 표면으로 표현한 것이다.

### 1. `probe survey` — 변이 척추 (결정론, LLM 없음)

```bash
probe survey --base HEAD~1 --out probe-survey.json --ledger probe-ledger.yaml
# 전체 분석이면: probe survey --module pkg/a.py --module pkg/b.py ...
```
변경 모듈을 식별하고, 각 모듈에 cosmic-ray 를 돌려 survivor 를 산출하고, 원장을 읽어 **새 survivor
(fresh)** 만 추리고, suite 요약을 수집한다. `probe-survey.json` 에 survivors·fresh·suite_summary,
그리고 **fresh 마다 슬롯이 채워진 Critic 프롬프트**를 담아 낸다.

- 변경 모듈 0건 → "변경된 소스 모듈 없음", 종료. survivor 0건 → "갭 없음", 종료. fresh 0건(전부 이미
  판정됨) → 리포트만 내고 "새로 판정할 survivor 없음" — Critic 단계 불필요.
- **실패는 빈 survey 로 위장하지 않는다**: cosmic-ray 가 죽으면 CLI 도 비정상 종료하고 원인을 낸다
  (게이트 fail-open 금지).
- survey 는 **원장을 읽기만** 한다 — 측정은 영속 상태를 바꾸지 않는다.

### 2. Test Quality Critic dispatch (판단 영역 — CLI 밖, 설계상)

`probe-survey.json` 의 `prompts[]` 각 프롬프트(이미 슬롯이 채워져 있다)를 **서브에이전트로 dispatch**
한다. survivor 는 서로 독립이라 병렬로 띄워도 된다. Critic 은 `{verdict, rationale,
suggested_test_intent}` JSON 을 돌려준다(`verdict` ∈ `real-gap|equivalent|low-value`).

수집한 판정을 `verdicts.json` 리스트로 모은다 — 각 항목은 `{survivor_key, verdict, rationale,
suggested_test_intent}`. `survivor_key` 는 프롬프트 옆 `prompts[].survivor_key` 를 그대로 쓴다.

> 이 단계만 손으로 하는 이유: CLI 는 Claude 서브에이전트를 dispatch 할 수 없고, 해서도 안 된다 —
> LLM 을 러너에 넣는 순간 Probe 가 막으려는 그 융합이 된다.

### 3. `probe absorb` — 판정 흡수 → 영속 → 리포트

```bash
probe absorb --verdicts verdicts.json --survey probe-survey.json --ledger probe-ledger.yaml
```
판정을 원장에 기록하고(불변, 사람이 손으로 단 `waived_until` 보존), `probe-ledger.yaml` 을 **커밋
대상**으로 쓰고, 리포트를 낸다 — **headline = 무는(unwaived) real-gap 수**(변이 점수 아님), real-gap
최상단, equivalent/low-value/유예된 real-gap 은 강등되지만 누락 안 됨.

- 도메인 밖 `verdict` 값이나 survey 에 없는 `survivor_key` 는 **시끄럽게 거부**하고 원장을 손대지
  않는다. 부분 verdicts(빠진 fresh)는 삼키지 않고 경고로 이름을 알린다.
- 무는 real-gap 마다 Critic 의 `suggested_test_intent` 를 사용자에게 제시하고 **행위검증 테스트 추가를
  권유**한다. M2 는 아직 어드바이저리 — 강제하지 않는다(강제 게이트 = M3).

## 품질 회귀

Critic 프롬프트를 수정하면 `references/critic-eval.md`의 골든 케이스(EVAL-1=real-gap,
EVAL-3=low-value)로 회귀 검사하라 — 결정론 증거를 보고 옳게 triage하는지가 이 하네스의 가치 그 자체다.

## 범위 밖 (M2 현재)

**게이트(pre-commit 강제)** = M3 — `biting(survivors, ledger, today)`가 그 입력이다(무는 real-gap이 있으면
커밋 실패). diff 라인 단위 정밀 coverage 매핑, survivor의 behavioral clustering(동일 갭을 증거하는 변이 묶기)도
향후 작업(M1 완료; M2/M3 후속).
