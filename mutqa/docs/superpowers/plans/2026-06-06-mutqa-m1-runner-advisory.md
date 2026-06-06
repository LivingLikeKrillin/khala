# mutqa M1 — 러너 + 어드바이저리 리포트 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** cosmic-ray 뮤테이션 survivor를 결정론적으로 추출하고, Critic 서브에이전트가 triage한 어드바이저리 마크다운 리포트를 내는 러너+스킬을 만든다. (게이트·영속 원장 없음 = M2/M3.)

**Architecture:** 결정론 러너(파이썬, LLM 없음) = `scope`(diff→대상 모듈) → `run`(cosmic-ray config+오케스트레이션) → `extract`(dump JSON→survivor). 에이전트 스킬 = survivor마다 Critic dispatch → `report`가 마크다운 조립. 결정론/에이전트 경계 = `survivors.json` 계약. 첫 소비자이자 테스트 오라클 = specledger.

**Tech Stack:** Python 3.11+, pytest, cosmic-ray(뮤테이션 엔진, Windows 네이티브 지원), TOML(cosmic-ray config), Claude skill(SKILL.md) + 서브에이전트.

**Spec:** `docs/superpowers/specs/2026-06-06-mutation-test-quality-harness-design.md`

---

## 파일 구조 (M1)

```
[claude] skills/mutqa/
  pyproject.toml                      # 패키지 메타 + pytest/ruff 설정 (Task 1)
  src/mutqa/
    __init__.py
    extract.py                        # cosmic-ray dump → survivor 정규화 (Task 2)
    scope.py                          # git diff → 변경 소스 모듈 목록 (Task 3)
    run.py                            # cosmic-ray config 생성 + 오케스트레이션 (Task 4,5)
    report.py                         # survivor+verdict → 어드바이저리 마크다운 (Task 6)
    models.py                         # Survivor/Verdict 데이터클래스 (Task 2에서 시작)
  tests/
    conftest.py
    fixtures/
      cr_dump_sample.jsonl            # cosmic-ray dump 프로즌 픽스처 (Task 2)
    test_extract.py
    test_scope.py
    test_run_config.py
    test_report.py
  SKILL.md                            # 스킬 오케스트레이션 프로즈 (Task 8)
  references/
    critic-prompt.md                  # Critic 서브에이전트 프롬프트 템플릿 (Task 7)
    critic-eval.md                    # 골든 이밸 케이스(specledger ground-truth) (Task 7)
```

각 유닛 책임(내부 안 봐도 이해 가능):
- `extract.py`: cosmic-ray dump(JSONL) → `list[Survivor]`. **순수 함수, LLM/네트워크/디스크 부작용 없음.**
- `scope.py`: git diff 범위 → cosmic-ray가 변이할 모듈 경로 목록.
- `run.py`: 모듈 목록 → cosmic-ray TOML config(순수) + `init`/`exec`/`dump` subprocess 오케스트레이션(부작용).
- `report.py`: `(survivors, verdicts)` → 사람이 읽는 마크다운. 순수.
- `models.py`: 경계 계약 타입(`Survivor`, `Verdict`).

---

## Chunk 1: 결정론 러너 (TDD)

### Task 1: 프로젝트 스캐폴드

**Files:**
- Create: `pyproject.toml`
- Create: `src/mutqa/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: pyproject.toml 작성**

```toml
[project]
name = "mutqa"
version = "0.1.0"
description = "Mutation-driven test quality harness"
requires-python = ">=3.11"
dependencies = ["cosmic-ray>=8.3"]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.5"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
```

- [ ] **Step 2: 빈 패키지/conftest 생성**

`src/mutqa/__init__.py` = 빈 파일. `tests/conftest.py`:

```python
from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
```

- [ ] **Step 3: 설치·수집 확인**

Run: `python -m pip install -e ".[dev]"` 후 `python -m pytest -q`
Expected: `no tests ran` (수집 0, 에러 없음)

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/mutqa/__init__.py tests/conftest.py
git commit -m "chore: scaffold mutqa package"
```

---

### Task 2: `extract.py` — cosmic-ray dump → survivor

cosmic-ray `dump` 출력은 JSONL이며 각 줄 = `[work_item, work_result]` 배열.
- `work_item` = `{"job_id","module_path","operator_name","occurrence","start_pos":[line,col],"end_pos":[line,col]}`
- `work_result` = `{"worker_outcome","test_outcome","output","diff","job_id"}` **또는 `null`**(미실행).
- **survivor 정의:** `work_result` 비-null AND `worker_outcome == "normal"` AND `test_outcome == "survived"`(소문자).

**Files:**
- Create: `src/mutqa/models.py`
- Create: `src/mutqa/extract.py`
- Create: `tests/fixtures/cr_dump_sample.jsonl`
- Create: `tests/test_extract.py`

- [ ] **Step 1: 프로즌 픽스처 작성** (실제 cosmic-ray dump 스키마 충실 — survivor 1, killed 1, 미실행 1)

`tests/fixtures/cr_dump_sample.jsonl` (각 줄이 완전한 JSON 배열, 줄바꿈 구분):

```
[{"job_id":"a1","module_path":"src/specledger/review.py","operator_name":"core/ReplaceComparisonOperator_Lt_LtE","occurrence":0,"start_pos":[88,4],"end_pos":[88,20]},{"job_id":"a1","worker_outcome":"normal","test_outcome":"survived","output":"69 passed","diff":"--- mutation diff\n+++ b\n@@ -88 +88 @@\n-        for d in dispositions:\n+        for d in []:"}]
[{"job_id":"b2","module_path":"src/specledger/review.py","operator_name":"core/NumberReplacer","occurrence":0,"start_pos":[42,8],"end_pos":[42,9]},{"job_id":"b2","worker_outcome":"normal","test_outcome":"killed","output":"1 failed","diff":"--- m\n+++ b\n@@ -42 +42 @@\n-    x = 1\n+    x = 2"}]
[{"job_id":"c3","module_path":"src/specledger/review.py","operator_name":"core/ReplaceTrueWithFalse","occurrence":0,"start_pos":[15,11],"end_pos":[15,15]},null]
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_extract.py`:

```python
from mutqa.extract import extract_survivors
from mutqa.models import Survivor


def test_extract_keeps_only_survivors(fixtures_dir):
    survivors = extract_survivors((fixtures_dir / "cr_dump_sample.jsonl").read_text())
    assert len(survivors) == 1  # killed 제외, 미실행(null) 제외


def test_survivor_fields_normalized(fixtures_dir):
    [s] = extract_survivors((fixtures_dir / "cr_dump_sample.jsonl").read_text())
    assert isinstance(s, Survivor)
    assert s.module == "src/specledger/review.py"
    assert s.lineno == 88                       # start_pos[0]
    assert s.operator == "core/ReplaceComparisonOperator_Lt_LtE"
    assert "for d in []:" in s.mutation_diff


def test_blank_lines_ignored(fixtures_dir):
    text = (fixtures_dir / "cr_dump_sample.jsonl").read_text() + "\n\n"
    assert len(extract_survivors(text)) == 1
```

- [ ] **Step 3: 실패 확인**

Run: `python -m pytest tests/test_extract.py -v`
Expected: FAIL — `ModuleNotFoundError: mutqa.extract` / `mutqa.models`

- [ ] **Step 4: models.py + extract.py 최소 구현**

`src/mutqa/models.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Survivor:
    # NOTE(M1): spec §4의 `surviving_tests`는 여기 없음 — M1은 suite 요약(테스트 개수)을
    # Critic에 out-of-band로 전달(SKILL.md Step 2). per-survivor coverage 매핑은 M2.
    module: str
    lineno: int
    operator: str
    mutation_diff: str

    @property
    def key(self) -> str:
        """안정 키: module:lineno:operator (원장 매칭용, M2에서 사용)."""
        return f"{self.module}:{self.lineno}:{self.operator}"


@dataclass(frozen=True)
class Verdict:
    survivor_key: str
    verdict: str            # "real-gap" | "equivalent" | "low-value"
    rationale: str
    suggested_test_intent: str | None = None
```

`src/mutqa/extract.py`:

```python
import json

from mutqa.models import Survivor


def extract_survivors(dump_text: str) -> list[Survivor]:
    """cosmic-ray `dump` 출력(JSONL)에서 살아남은 변이만 추출.

    각 줄 = [work_item, work_result]. survivor = work_result 비-null이며
    worker_outcome == "normal" AND test_outcome == "survived".
    """
    survivors: list[Survivor] = []
    for line in dump_text.splitlines():
        line = line.strip()
        if not line:
            continue
        work_item, result = json.loads(line)
        if result is None:
            continue
        if result.get("worker_outcome") != "normal":
            continue
        if result.get("test_outcome") != "survived":
            continue
        survivors.append(
            Survivor(
                module=work_item["module_path"],
                lineno=work_item["start_pos"][0],
                operator=work_item["operator_name"],
                mutation_diff=result.get("diff", ""),
            )
        )
    return survivors
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/test_extract.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add src/mutqa/models.py src/mutqa/extract.py tests/test_extract.py tests/fixtures/cr_dump_sample.jsonl
git commit -m "feat: extract survivors from cosmic-ray dump"
```

---

### Task 3: `scope.py` — git diff → 변경 소스 모듈

소비자 repo에서 변경된 `.py` 소스 파일(테스트 제외)을 골라 cosmic-ray 변이 대상으로 산출.

**Files:**
- Create: `src/mutqa/scope.py`
- Create: `tests/test_scope.py`

- [ ] **Step 1: 실패하는 테스트 작성** (subprocess는 주입 가능한 콜러블로 — 결정론 유지)

`tests/test_scope.py`:

```python
from mutqa.scope import changed_source_modules


def test_filters_to_python_sources():
    diff_output = "src/pkg/a.py\nsrc/pkg/b.py\nREADME.md\n"
    mods = changed_source_modules(base="HEAD~1", run=lambda cmd: diff_output)
    assert mods == ["src/pkg/a.py", "src/pkg/b.py"]


def test_excludes_tests_and_dunder():
    diff_output = "src/pkg/a.py\ntests/test_a.py\nsrc/pkg/__init__.py\n"
    mods = changed_source_modules(base="HEAD~1", run=lambda cmd: diff_output)
    assert mods == ["src/pkg/a.py"]


def test_empty_diff_returns_empty():
    mods = changed_source_modules(base="HEAD~1", run=lambda cmd: "")
    assert mods == []
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_scope.py -v`
Expected: FAIL — `ModuleNotFoundError: mutqa.scope`

- [ ] **Step 3: 최소 구현**

`src/mutqa/scope.py`:

```python
import subprocess
from collections.abc import Callable


def _git(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def changed_source_modules(
    base: str = "HEAD",
    run: Callable[[list[str]], str] = _git,
) -> list[str]:
    """base 대비 변경된 파이썬 소스 모듈 경로(테스트/__init__ 제외)."""
    raw = run(["git", "diff", "--name-only", base])
    out: list[str] = []
    for path in raw.splitlines():
        path = path.strip().replace("\\", "/")
        if not path.endswith(".py"):
            continue
        if path.startswith("tests/") or "/tests/" in path:
            continue
        if path.endswith("__init__.py"):
            continue
        out.append(path)
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_scope.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mutqa/scope.py tests/test_scope.py
git commit -m "feat: scope changed source modules from git diff"
```

---

### Task 4: `run.py` — cosmic-ray config 생성 (순수)

모듈 목록 + 테스트 명령 → cosmic-ray TOML config 문자열. (subprocess 오케스트레이션은 Task 5.)

**Files:**
- Create: `src/mutqa/run.py`
- Create: `tests/test_run_config.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_run_config.py`:

```python
import tomllib

from mutqa.run import build_config


def test_config_targets_given_module():
    cfg = build_config(module_path="src/specledger/review.py")
    parsed = tomllib.loads(cfg)
    assert parsed["cosmic-ray"]["module-path"] == "src/specledger/review.py"


def test_config_default_test_command():
    cfg = build_config(module_path="src/pkg/a.py")
    parsed = tomllib.loads(cfg)
    assert parsed["cosmic-ray"]["test-command"] == "python -m pytest -q -x"


def test_config_custom_test_command():
    cfg = build_config(module_path="src/pkg/a.py", test_command="pytest -q")
    assert tomllib.loads(cfg)["cosmic-ray"]["test-command"] == "pytest -q"
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_run_config.py -v`
Expected: FAIL — `ModuleNotFoundError: mutqa.run`

- [ ] **Step 3: 최소 구현**

`src/mutqa/run.py`:

```python
DEFAULT_TEST_COMMAND = "python -m pytest -q -x"


def build_config(module_path: str, test_command: str = DEFAULT_TEST_COMMAND) -> str:
    """단일 모듈 대상 cosmic-ray config(TOML 문자열) 생성.

    cosmic-ray는 module-path를 단일 경로로 받으므로 모듈별 1 config.
    """
    return (
        "[cosmic-ray]\n"
        f'module-path = "{module_path}"\n'
        "timeout = 30.0\n"
        "excluded-modules = []\n"
        f'test-command = "{test_command}"\n'
        "\n"
        "[cosmic-ray.distributor]\n"
        'name = "cosmic_ray.distribution.local.LocalDistributor"\n'
    )
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_run_config.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mutqa/run.py tests/test_run_config.py
git commit -m "feat: generate cosmic-ray config per module"
```

---

### Task 5: `run.py` — 오케스트레이션 (통합, cosmic-ray 게이트)

config 작성 → `cosmic-ray init` → `cosmic-ray exec` → `cosmic-ray dump` → survivor 추출까지 잇는다. cosmic-ray 실행에 의존하므로 통합 테스트로 분리하고, cosmic-ray 미설치 시 skip.

**Files:**
- Modify: `src/mutqa/run.py`
- Create: `tests/test_run_integration.py`

- [ ] **Step 1: 실패하는 통합 테스트 작성** (실제 cosmic-ray가 작은 임시 모듈에 돌아감)

`tests/test_run_integration.py`:

```python
import shutil
import textwrap

import pytest

from mutqa.run import run_mutation

pytestmark = pytest.mark.skipif(
    shutil.which("cosmic-ray") is None, reason="cosmic-ray 미설치"
)


def test_run_surfaces_known_survivor(tmp_path):
    """행위검증 없는 모듈 → 변이가 살아남아야 한다."""
    (tmp_path / "m.py").write_text("def f(x):\n    return x > 0\n")
    # 반환값을 검증하지 않는 테스트 = 약한 테스트 → 변이 생존 유발
    (tmp_path / "test_m.py").write_text(
        textwrap.dedent(
            """
            from m import f
            def test_f_runs():
                f(1)   # 단언 없음 — 의도적 약한 테스트
            """
        )
    )
    survivors = run_mutation(module_path="m.py", workdir=tmp_path)
    assert len(survivors) >= 1
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_run_integration.py -v`
Expected: FAIL — `ImportError: cannot import name 'run_mutation'` (cosmic-ray 설치 시) 또는 SKIP

- [ ] **Step 3: 오케스트레이션 구현** (`src/mutqa/run.py`에 추가)

```python
import subprocess
from pathlib import Path

from mutqa.extract import extract_survivors
from mutqa.models import Survivor


def run_mutation(module_path: str, workdir: Path, test_command: str = DEFAULT_TEST_COMMAND) -> list[Survivor]:
    """단일 모듈에 cosmic-ray 전체 사이클 실행 → survivor 목록.

    실패(init/exec 비정상 종료)는 예외로 전파 — 게이트 fail-open 금지(spec §8).
    """
    workdir = Path(workdir)
    cfg_path = workdir / "mutqa.cfg.toml"
    session = workdir / "mutqa.sqlite"
    cfg_path.write_text(build_config(module_path, test_command))

    def cr(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["cosmic-ray", *args], cwd=workdir, capture_output=True, text=True, check=True
        )

    cr("init", str(cfg_path), str(session))
    cr("exec", str(cfg_path), str(session))
    dump = subprocess.run(
        ["cosmic-ray", "dump", str(session)],
        cwd=workdir, capture_output=True, text=True, check=True,
    )
    return extract_survivors(dump.stdout)
```

- [ ] **Step 4: 통과/skip 확인**

Run: `python -m pytest tests/test_run_integration.py -v`
Expected: PASS (cosmic-ray 설치 시) 또는 SKIP. 단위 테스트는 여전히 전부 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mutqa/run.py tests/test_run_integration.py
git commit -m "feat: orchestrate cosmic-ray init/exec/dump into survivors"
```

---

## Chunk 2: Critic + 리포트 + 스킬 + dogfood

### Task 6: `report.py` — 어드바이저리 마크다운 조립 (순수)

`(survivors, verdicts)` → 사람이 읽는 마크다운. real-gap 우선 정렬, equivalent/low-value는 접어서 표시. M1 메트릭 = **unwaived real-gap 수**(변이 점수 아님, spec §8).

**Files:**
- Create: `src/mutqa/report.py`
- Create: `tests/test_report.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_report.py`:

```python
from mutqa.models import Survivor, Verdict
from mutqa.report import build_report


def _surv(line, op="op"):
    return Survivor(module="src/pkg/a.py", lineno=line, operator=op, mutation_diff=f"diff@{line}")


def test_report_counts_real_gaps_in_headline():
    survivors = [_surv(10), _surv(20)]
    verdicts = [
        Verdict(survivors[0].key, "real-gap", "행위검증 없음"),
        Verdict(survivors[1].key, "equivalent", "관측 차이 없음"),
    ]
    md = build_report(survivors, verdicts)
    assert "real-gap: 1" in md
    assert "src/pkg/a.py:10" in md
    assert "행위검증 없음" in md


def test_equivalent_is_demoted_not_dropped():
    survivors = [_surv(10)]
    verdicts = [Verdict(survivors[0].key, "equivalent", "동치")]
    md = build_report(survivors, verdicts)
    assert "real-gap: 0" in md
    assert "동치" in md  # 접혀도 내용은 남는다


def test_missing_verdict_treated_as_unknown():
    survivors = [_surv(10)]
    md = build_report(survivors, verdicts=[])
    assert "unknown" in md.lower()  # verdict 없는 survivor도 누락되지 않음
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: mutqa.report`

- [ ] **Step 3: 최소 구현**

`src/mutqa/report.py`:

```python
from mutqa.models import Survivor, Verdict

_ORDER = {"real-gap": 0, "unknown": 1, "low-value": 2, "equivalent": 3}


def build_report(survivors: list[Survivor], verdicts: list[Verdict]) -> str:
    by_key = {v.survivor_key: v for v in verdicts}
    rows = []
    for s in survivors:
        v = by_key.get(s.key)
        rows.append((s, v.verdict if v else "unknown", v.rationale if v else "(triage 안 됨)"))
    rows.sort(key=lambda r: _ORDER.get(r[1], 1))

    real_gaps = sum(1 for _, verdict, _ in rows if verdict == "real-gap")
    lines = [
        "# mutqa 어드바이저리 리포트",
        "",
        f"**unwaived real-gap: {real_gaps}** · survivor 총 {len(survivors)}",
        "",
    ]
    for s, verdict, rationale in rows:
        lines.append(f"- `{s.module}:{s.lineno}` [{verdict}] {s.operator}")
        lines.append(f"    - {rationale}")
    return "\n".join(lines)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_report.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mutqa/report.py tests/test_report.py
git commit -m "feat: assemble advisory markdown report"
```

---

### Task 7: Critic 프롬프트 + 골든 이밸 케이스 (authored)

Critic은 결정론 증거(변이 diff + 통과한 전체 스위트)만 보고 triage. specledger ground-truth로 회귀 검사.

**Files:**
- Create: `references/critic-prompt.md`
- Create: `references/critic-eval.md`

- [ ] **Step 1: Critic 프롬프트 템플릿 작성**

`references/critic-prompt.md` — 다음을 담는다:
- 역할: "너는 뮤테이션 survivor를 triage하는 Test Quality Critic이다."
- 입력 슬롯: `{module}`, `{lineno}`, `{operator}`, `{mutation_diff}`, `{suite_summary}`(예: "69개 테스트 전부 통과").
- 판정 규칙(spec §4): **불확실하면 real-gap으로 기운다**(놓친 갭 > 노이즈 비용). `equivalent`는 *관측 가능한 행위 차이가 없음*을 논증할 수 있을 때만. `low-value`는 로깅/방어코드 등 행위 계약과 무관할 때.
- 출력(스키마 강제): `{"verdict": "real-gap|equivalent|low-value", "rationale": "...", "suggested_test_intent": "..."|null}`.
- 핵심 지침: "변이가 핵심 행위를 무력화했는데 스위트가 green이면 그 행위에 행위검증이 없다는 결정론적 증거다 → real-gap."

- [ ] **Step 2: 골든 이밸 케이스 작성**

`references/critic-eval.md` — specledger ground-truth 케이스(각: 입력 + 기대 verdict + 근거):
- **EVAL-1 (must=real-gap):** `review.py` disposition 기록 루프 무력화(`for d in dispositions:` → `for d in []:`), suite 69 green. → 핵심 부수효과(disposition 기록)에 행위검증 0개. Critic은 반드시 `real-gap`.
- **EVAL-2 (must=equivalent):** PoC에서 나온 동치 변이 1건(실제 dogfood Task 9에서 채집해 채워넣음 — 그 전까지 placeholder 아님, "Task 9에서 실제 케이스로 확정" 명시). 임시로 합성 동치 예: 도달 불가 분기의 상수 변경.
- **EVAL-3 (must=low-value):** 디버그 로그 문자열 변경처럼 행위 계약 무관 변이.
- 합격 기준: Critic이 EVAL-1을 real-gap, EVAL-3을 low-value로 분류. EVAL-2는 Task 9에서 실데이터로 확정 후 equivalent 회귀로 고정.

> 주: M1에서 Critic 이밸은 **수동 실행**(실제 LLM 호출). 자동 이밸 러너는 M2+ YAGNI.

- [ ] **Step 3: Commit**

```bash
git add references/critic-prompt.md references/critic-eval.md
git commit -m "docs: critic prompt and golden eval cases"
```

---

### Task 8: `SKILL.md` — 스킬 오케스트레이션 프로즈 (authored)

스킬이 러너→Critic→리포트를 잇는 사용자 대면 절차.

**Files:**
- Create: `SKILL.md`

- [ ] **Step 1: SKILL.md 작성** (frontmatter + 절차)

frontmatter:
```yaml
---
name: mutqa
description: Use when you want to find weak spots in a Python test suite that advisory review misses — runs mutation testing on changed modules, triages surviving mutants with a Critic subagent, and emits an advisory report of real behavioral-test gaps. First consumer = specledger.
---
```
본문 절차:
1. `scope.changed_source_modules` + `run_mutation`으로 변경 모듈 변이 실행 → survivor 목록을 `dataclasses.asdict`로 직렬화해 `survivors.json` 저장(전용 직렬화 함수 없음 — 인라인 asdict).
2. 전체 스위트 요약 수집(`pytest --collect-only -q`로 테스트 개수 = `suite_summary`).
3. survivor마다 `references/critic-prompt.md`를 채워 **Critic 서브에이전트 dispatch**(병렬 가능, 건별 독립). verdict 수집 → `verdicts.json`.
4. `mutqa.report.build_report`로 마크다운 리포트 출력. **headline = unwaived real-gap 수.**
5. real-gap마다 `suggested_test_intent`를 사용자에게 제시 — 행위검증 테스트 추가를 권유(M1은 강제 없음, 어드바이저리).

- [ ] **Step 2: Commit**

```bash
git add SKILL.md
git commit -m "feat: mutqa skill orchestration prose"
```

---

### Task 9: E2E dogfood — specledger에서 17 survivor surface (수용 기준)

M1 완료 신호. specledger에 하네스를 통째로 돌려 PoC가 발견한 survivor가 재현되고 Critic이 disposition-loop를 real-gap으로 잡는지 확인.

**Files:**
- Create: `tests/fixtures/cr_dump_specledger.jsonl` (실제 캡처)
- Modify: `references/critic-eval.md` (EVAL-2를 실데이터로 확정)

- [ ] **Step 1: specledger에서 실제 변이 실행 + dump 캡처**

specledger repo에서 (**config는 M1 코드로 생성** — 하네스 코드경로를 실제로 검증):
```bash
cd "C:/Users/Eisen/Desktop/Labs/[claude] mcp-tools/specledger"
python -c "from mutqa.run import build_config; open('mutqa.cfg.toml','w').write(build_config('src/specledger/review.py'))"
cosmic-ray init mutqa.cfg.toml mutqa.sqlite
cosmic-ray exec mutqa.cfg.toml mutqa.sqlite
cosmic-ray dump mutqa.sqlite > review_dump.jsonl
```

- [ ] **Step 2: 캡처한 dump로 extract 검증** — PoC 기준 survivor가 재현되는지

`review_dump.jsonl`을 `tests/fixtures/cr_dump_specledger.jsonl`로 저장 후:
```bash
python -c "from mutqa.extract import extract_survivors; import pathlib; s=extract_survivors(pathlib.Path('tests/fixtures/cr_dump_specledger.jsonl').read_text()); print(len(s)); [print(x.key) for x in s]"
```
Expected: survivor 수가 PoC 보고(≈17)와 같은 자릿수, disposition-loop 변이가 목록에 존재.

- [ ] **Step 3: 스키마 충실성 검증** — Task 2 합성 픽스처가 실 스키마와 일치하는지

실 dump 한 줄과 `cr_dump_sample.jsonl`의 키 집합 비교. 불일치 시 합성 픽스처 수정 후 Task 2 테스트 재실행(green 유지).

- [ ] **Step 4: Critic 수동 이밸 (EVAL-1)** — disposition-loop survivor를 Critic에 넣어 `real-gap` 확인

`references/critic-prompt.md`를 disposition-loop survivor로 채워 Critic 서브에이전트 dispatch. Expected: `verdict == "real-gap"`. EVAL-2(동치)는 실제 survivor 중 하나를 골라 equivalent로 확정해 `critic-eval.md`에 고정. **폴백: specledger 실행에서 깨끗한 동치 survivor를 못 찾으면 Task 7의 합성 EVAL-2 케이스를 그대로 유지하고 그 사실을 명시**(Task 9가 외부 경험 조건에 막히지 않게).

- [ ] **Step 5: 전체 어드바이저리 리포트 생성 + 육안 확인**

스킬 전 절차 실행 → 마크다운 리포트가 disposition-loop를 real-gap 최상단에 띄우는지 확인.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/cr_dump_specledger.jsonl references/critic-eval.md
git commit -m "test: dogfood mutqa on specledger, confirm survivors surface"
```

---

## M1 완료 정의 (Definition of Done)

- [ ] 단위 테스트 전부 green (`extract`, `scope`, `run_config`, `report`), cosmic-ray 통합 테스트 green-or-skip.
- [ ] specledger dogfood에서 PoC survivor(특히 disposition-loop) 재현 + Critic이 real-gap으로 triage.
- [ ] 어드바이저리 마크다운 리포트가 unwaived real-gap 수를 headline으로 출력.
- [ ] **비목표 확인:** 게이트/영속 원장/diff-scoping 정밀 coverage = M2/M3, M1에 없음.

## M1 → M2 인계 메모

- `Survivor.key`(`module:lineno:operator`)는 이미 원장 매칭용으로 존재 → M2 `ledger.py`가 소비.
- `surviving_tests` 정밀화(coverage 기반 per-line 매핑)는 M2. M1은 suite 요약(개수)만 Critic에 전달.
- 라인 이동 키 깨짐 완화(정규화 해시 보조 키)는 M2.
