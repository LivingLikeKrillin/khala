# 뮤테이션-구동 테스트 품질 하네스 — 설계

- **날짜:** 2026-06-06
- **상태:** 설계 승인됨 (브레인스토밍 완료, spec 리뷰 대기)
- **로드맵:** 에이전트 하네스 (#13) — "AI 생성 테스트 코드 품질" 슬라이스
- **첫 소비자 / 테스트 오라클:** specledger (dogfood)

## 1. 문제와 검증된 가설

**질문(사전등록):** 기존 도구(superpowers TDD+anti-patterns, `python:test-reviewer`,
`tech-lead:code-review`)보다 테스트 품질을 의미있게 더 높일 수 있나? 없으면 접는다.

**PoC 결과(2026-06-06):** 개념 커버리지는 포화 — 기존 도구는 전부 *어드바이저리*.
진짜 빈칸은 **결정론적 강제(deterministic forcing)**. specledger `review.py`에 cosmic-ray
뮤테이션 테스팅을 돌려 변이 63개 중 17개(27%) 생존 확인. 결정적 발견:
`approve()`의 **disposition 기록 루프를 통째로 무력화(`for i in []`)해도 69 테스트 전부 green** —
핵심 행위에 행위검증이 0개. 이걸 사람+LLM 2단계 리뷰까지 거치고도 놓쳤다. 뮤테이션이
결정론적으로 잡았다. (단 equivalent mutant 노이즈도 발생 → Critic의 역할이 survivor triage임이 드러남.)

**결론:** 도구의 가치는 "더 똑똑한 조언"이 아니라 **"결정론적 증거 + 그 증거에 근거한 강제"**.

## 2. 가치 가설 (사전등록 · 변경 금지)

> "결정론적 강제(뮤테이션 survivor 게이트)가 어드바이저리 리뷰보다 진짜 테스트 갭을 잡는다."

**합격 신호:** specledger dogfood에서 하네스가 disposition-loop류 real-gap을 surface하고,
게이트가 그것을 막고, 행위검증 테스트를 추가해야만 통과한다. 알려진 17 survivor가 수용 회귀 세트.
**기각 신호:** 게이트가 잡는 게 거의 equivalent 노이즈뿐(real-gap을 못 더함)이거나, 노이즈가
많아 매번 묵살하게 됨 → 어드바이저리 대비 우위 없음 → 접는다.

## 3. 핵심 설계 원칙 — 하나의 깨끗한 seam

한쪽은 100% 결정론(재현 가능, LLM 없음), 다른 쪽은 에이전트 판단. **둘을 섞지 않는다** —
섞이면 "왜 이 게이트가 걸렸나"를 신뢰할 수 없다.

```
┌─ 결정론 영역 (러너, 파이썬, LLM 없음) ──────────┐
│  diff 감지 → cosmic-ray config 생성 →            │
│  변이 실행(변경 모듈만) → survivor 추출 →         │
│  baseline 원장과 대조 → "새 survivor" 목록(JSON)  │
└──────────────────────┬───────────────────────────┘
                       │  survivors.json   ← 두 영역의 유일한 계약
                       ▼
┌─ 에이전트 영역 (스킬 + Critic 서브에이전트) ──────┐
│  새 survivor마다: Critic이 결정론 증거(변이 diff + │
│  통과한 테스트들)를 보고 triage:                   │
│     real-gap / equivalent / low-value + 근거       │
│  → equivalent/low-value는 사유와 함께 원장에 기록  │
│  → real-gap만 게이트로                             │
└──────────────────────┬───────────────────────────┘
                       │  verdicts.json
                       ▼
        게이트(pre-commit hook): unwaived real-gap 있으면 실패
```

**경계가 주는 보장:**
- 러너 출력(`survivors.json`)이 유일한 계약. 러너는 단독으로 테스트·재현 가능(LLM 무관).
- Critic은 **결정론 증거에만** 근거 → 순수 LLM `python:test-reviewer` 대비 차별점이 *구조로* 보장됨.
- baseline 원장이 결정론 영역에 있는 이유: "이 변이는 이미 판정됨"은 **사실 기록**이지 판단이 아님.
  Critic은 *새* survivor에만 호출 → equivalent 노이즈를 매번 재심의하지 않음.

## 4. 컴포넌트

### 러너 `mutqa` (작은 파이썬 패키지)
- `scope.py` — git diff로 변경된 소스 모듈 식별 → cosmic-ray 대상 산출. (전체 스윕은 옵션 플래그.)
- `run.py` — cosmic-ray config 생성(`test-command="python -m pytest -q -x"`) → `init`→`exec` 오케스트레이션 → dump.
- `extract.py` — dump JSON 파싱 → survivor 정규화(소문자 `survived`).
  각 survivor = `{module, lineno, operator, mutation_diff, surviving_tests}`.
  - **`surviving_tests` 출처:** cosmic-ray의 변이별 dump는 "어떤 테스트가 통과했나"를 직접 주지
    않으므로(통과/실패 집계만), M1 러너는 그 변이를 적용한 채 `pytest --collect-only`로 대상
    모듈을 커버하는 테스트를 수집해 Critic 입력으로 첨부한다(= "이 변이에도 green인 테스트들").
    정밀 매핑(변이 라인을 실제로 실행한 테스트만)은 coverage 기반으로 M2에서 좁힌다.
- `ledger.py` — baseline/waiver 원장 읽기·쓰기·대조. "새 survivor" = 원장에 없는 것만.

### Critic 서브에이전트 (스킬이 dispatch)
- **입력:** 새 survivor 1건의 결정론 증거 = 변이 diff + 그 변이에도 통과한 테스트 목록.
- **출력(스키마 강제):** `{verdict: real-gap|equivalent|low-value, rationale, suggested_test_intent?}`.
- **핵심 규칙:** 불확실하면 real-gap으로 기운다(놓친 갭 > 노이즈 비용). 단 equivalent는
  명확한 근거가 있을 때만(관측 가능한 행위 차이가 없음을 논증).

### 스킬 (`[claude] skills/mutqa/`)
- 오케스트레이션 프로즈: 러너 호출 → 새 survivor마다 Critic dispatch → verdict를 원장에 반영
  → real-gap 요약 + 게이트 상태 제시.
- **파일 흐름:** 러너가 휘발성 `survivors.json`(새 survivor) 산출 → 스킬이 Critic을 돌려
  `verdicts.json`(triage 결과) 산출 → 스킬이 이를 영속 `mutqa-ledger.yaml`에 흡수(§5).
  즉 `*.json`은 한 실행의 작업 산출물, `mutqa-ledger.yaml`은 커밋되는 판정 기록.
- **Critic dispatch 비용:** survivor는 건별 독립 dispatch(병렬 가능). 첫 dogfood 기준 ≈17건 ×
  1콜이 비용 상한 가정. equivalent가 원장에 흡수되면 재실행 시 새 survivor만 남아 콜 수가 급감.

### 게이트 (소비자 repo의 `hooks/`)
- pre-commit: unwaived real-gap survivor 존재 시 실패 + 어떤 행위에 테스트가 없는지 출력.
- specledger의 기존 `hooks/pretooluse_gate.py` 패턴을 따름.
- **러너 실패 시 fail-open 금지** — 명확히 에러로(침묵하면 안전한 척하게 됨).

## 5. 데이터 계약 — baseline 원장 포맷

소스와 함께 커밋되는 영속 상태. 결정론/에이전트 양쪽을 잇는다.

```yaml
# mutqa-ledger.yaml
waivers:
  - key: "review.py:142:replace_or_with_and"   # module:lineno:operator (안정 키)
    verdict: equivalent
    rationale: "두 분기 결과 동일 — 관측 가능한 차이 없음"
    recorded: 2026-06-06
  - key: "review.py:88:remove_disposition_loop"
    verdict: real-gap
    waived_until: 2026-06-20          # real-gap이지만 의식적으로 미룸 (만료 필수)
    rationale: "다음 스프린트에 행위검증 추가 예정"
```

- **안정 키 = `module:lineno:operator`.** cosmic-ray 식별자 중 가장 안정적(라인 이동엔 약함 → §7).
- equivalent / low-value는 영구 waive.
- **real-gap waive는 만료 필수(`waived_until`)** — 무기한 묵살 방지. 게이트가 만료된 real-gap을 다시 살린다.

## 6. Milestone 순서 (어드바이저리 → 강제)

각 milestone이 독립적으로 가치를 준다.

1. **M1 — 러너 + 어드바이저리 리포트.** 러너를 TDD로 구축(survivor 추출까지).
   스킬이 Critic triage해서 마크다운 리포트 출력. 게이트·원장 없음.
   **specledger에 돌려 17 survivor를 실제로 surface = 첫 dogfood.** (M1만으로도 PoC보다 나은
   반복 가능 도구.)
2. **M2 — 원장 + triage 영속화.** baseline/waiver 원장 추가. Critic verdict가 원장에 쌓임.
   재실행 시 새 survivor만 재심의(equivalent 재심의 제거).
3. **M3 — pre-commit 게이트.** unwaived real-gap에 bite. **여기서 "결정론적 강제"라는 검증된
   종착지 도달.** 가치 가설을 E2E로 검증.

## 7. 테스트 전략

seam 덕분에 두 영역을 완전히 다르게 테스트한다.

### ① 러너 (결정론 영역) — 평범한 TDD, LLM 0회
입력 고정 → 출력 고정. red-first로 짠다.
- cosmic-ray dump JSON을 **프로즌 픽스처**로 박아두고 → survivor 추출이 정확한 목록을 내는지.
- baseline 원장 대조 로직(새 survivor만 골라내기, waiver 매칭, real-gap 만료 처리).
- diff-scoping(변경 모듈만 config에 포함).

### ② Critic (에이전트 영역) — 골든 이밸 세트
**specledger가 이미 ground-truth를 준다:**
- `approve()` disposition 루프 무력화 변이 → 69 green인데 살아남음 = 명백한 **real-gap**.
  Critic은 반드시 real-gap으로 분류해야 한다.
- PoC에서 나온 equivalent mutant 사례 → Critic은 반드시 equivalent로 분류해야 한다.
이 둘(+α)을 작은 이밸 세트로 고정 → Critic 프롬프트 변경 시 회귀 검사. 실제 LLM 호출이지만
케이스가 소수라 싸다. "결정론 증거를 보고 옳게 triage하나"를 직접 측정.

### ③ 하네스 전체(E2E) = dogfood 수용 기준
specledger에 통째로 돌려서: disposition-loop 갭을 surface → 게이트가 막음 → 테스트를 추가하면
통과. 이 한 사이클이 가치 가설의 살아있는 증거. specledger의 알려진 17 survivor = 수용 회귀 스위트.

> specledger는 첫 소비자이자 이 하네스의 **테스트 오라클**. 합성 데이터가 불필요한 게 큰 이점.

## 8. Gotcha / 에러 처리

- **라인 이동으로 원장 키 깨짐:** 코드가 바뀌면 `lineno`가 흔들려 waive가 헛돈다.
  완화책(M2): 변이 주변 소스의 **정규화 해시**를 보조 키로(라인 대신 코드 내용 기준).
  M1에선 라인 키로 두고 한계를 명시.
- **cosmic-ray 느림:** diff-scoping이 1차 방어. 그래도 느리면 변경 라인 근처만 변이(M2+).
- **equivalent mutant 불가피:** 0으로 못 만든다 → Critic triage + 원장 흡수가 설계상 답.
  메트릭은 "변이 점수"가 아니라 **"unwaived real-gap 수"**(노이즈에 안 휘둘림).
- **Windows 네이티브:** `mutmut` 미지원 → **cosmic-ray** 사용
  (`pip install cosmic-ray`, config `module-path`/`test-command`, `init`→`exec`→`cr-rate`/`cr-report`;
  dump JSON outcome은 소문자 `killed`/`survived`).
- **러너 실패:** 게이트 fail-open 금지 — 명확히 에러.

## 9. 비목표 (YAGNI)

- CI 배치 서비스 / 변이 점수 추세 추적 (접근법 C) — 가치 검증 후로 보류.
- 스토리→불변식 자동도출류 — 범위 밖.
- 전체 변이 스윕 기본화 — diff-scoped가 기본, 전체는 옵션.
- **뮤테이션 엔진 추상화** — cosmic-ray에 의도적 강결합(§8). 다중 엔진 플러그인 레이어는
  명시적 YAGNI. 필요해지면 그때 추출.
