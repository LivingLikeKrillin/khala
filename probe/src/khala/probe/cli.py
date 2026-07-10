"""Probe CLI — 결정론 척추를 두 명령으로, 판단은 있어야 할 곳(CLI 밖)에 남긴다.

SPEC-probe-cli. 여태 Probe 를 쓰려면 SKILL.md 의 파이썬 블록 6개를 손으로 붙여넣어야 했다 —
"도구가 아니다"(감사). 이 CLI 가 결정론 부분(변이 실행·survivor·원장·리포트)을 명령으로 감싼다.

    probe survey [--base HEAD~1] [--module PATH ...]   # 변이 척추 → survivor + fresh Critic 프롬프트
    (에이전트/사람이 프롬프트로 Test Quality Critic 을 dispatch → verdicts.json)   ← CLI 밖, 설계상
    probe absorb --verdicts verdicts.json --survey probe-survey.json   # 판정 흡수 → 원장 + 리포트

핵심(SPEC §2): 러너(결정론, LLM 없음)와 Critic(판단)을 섞지 않는다. CLI 는 LLM 을 부르지 않는다 —
판정은 파일 경계 너머 에이전트가 한다. mutate/list_modules/collect 는 주입 가능(테스트용).
"""

from __future__ import annotations

import datetime
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import typer

from khala.probe.ledger import absorb, dump_ledger, load_ledger, new_survivors
from khala.probe.models import Survivor, Verdict
from khala.probe.report import build_report
from khala.probe.run import run_mutation
from khala.probe.scope import changed_source_modules

# Windows 콘솔(cp949)은 한글 출력에서 죽는다. UTF-8 로 재구성 (nexus/cli.py·arbiter/cli.py 와 동일).
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 — 재구성 불가 환경이면 그냥 둔다
        pass

_VERDICT_DOMAIN = {"real-gap", "equivalent", "low-value"}
_PROMPT_PATH = Path(__file__).resolve().parents[3] / "references" / "critic-prompt.md"
_SLOTS = ("module", "lineno", "operator", "mutation_diff", "suite_summary")


def _default_mutate(module_path: str, workdir: Path) -> list[Survivor]:
    return run_mutation(module_path, workdir=workdir)


def _default_list_modules(base: str) -> list[str]:
    return changed_source_modules(base=base)


def _default_collect(workdir: Path) -> str:
    """pytest --collect-only 원시 출력. 실패는 예외 전파(호출부가 coarse 요약/폴백 처리)."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=workdir, capture_output=True, text=True, check=True,
    ).stdout


def _coarse_summary(raw: str) -> str:
    """버전 무관 best-effort 요약: 'collected/수집' 줄을 우선, 없으면 마지막 줄."""
    for line in raw.splitlines():
        if "collected" in line or "수집" in line:
            return line.strip()
    tail = [ln for ln in raw.strip().splitlines() if ln.strip()]
    return tail[-1].strip() if tail else "스위트 요약 없음"


def _suite_summary(workdir: Path, collect) -> str:
    try:
        raw = collect(workdir)
    except Exception:  # noqa: BLE001 — 수집 실패는 Critic 문맥을 거칠게 할 뿐, 실행을 깨지 않는다
        return "스위트 요약 수집 실패"
    return _coarse_summary(raw)


def _fill_prompt(template: str, s: Survivor, suite_summary: str) -> str:
    """슬롯을 replace 로 치환한다 — mutation_diff 안의 중괄호가 format 을 깨지 않도록."""
    values = {"module": s.module, "lineno": str(s.lineno), "operator": s.operator,
              "mutation_diff": s.mutation_diff, "suite_summary": suite_summary}
    out = template
    for slot in _SLOTS:
        out = out.replace("{" + slot + "}", values[slot])
    return out


def _survivor_key(d: dict) -> str:
    """survey JSON 의 survivor dict → 안정 키. 하네스 Survivor.key 와 정확히 같은 규칙."""
    return f"{d['module']}:{d['lineno']}:{d['operator']}"


def build_cli(
    *,
    mutate=_default_mutate,
    list_modules=_default_list_modules,
    collect=_default_collect,
    prompt_template: str | None = None,
    today_fn=datetime.date.today,
) -> typer.Typer:
    """결정론 함수들을 명령으로 노출한다. 주입점은 테스트용(프로덕션은 기본값=실제 러너)."""
    app = typer.Typer(help="Probe — 변이 구동 테스트 품질 하네스 CLI", no_args_is_help=True)

    def _prompt() -> str:
        return prompt_template if prompt_template is not None else _PROMPT_PATH.read_text(
            encoding="utf-8")

    @app.command()
    def survey(
        base: str = typer.Option("HEAD~1", "--base", help="diff 기준 (변경 모듈 식별)"),
        module: list[str] = typer.Option([], "--module", help="분석 모듈 명시 (없으면 diff)"),
        workdir: str = typer.Option(".", "--workdir", help="분석 대상 소비자 repo"),
        out: str = typer.Option("probe-survey.json", "--out"),
        ledger: str = typer.Option("probe-ledger.yaml", "--ledger"),
    ) -> None:
        """변이 척추(결정론): 변경 모듈 → survivor → fresh 마다 채워진 Critic 프롬프트. LLM 없음."""
        modules = list(module) or list_modules(base)
        if not modules:
            typer.echo("변경된 소스 모듈 없음")
            return
        survivors: list[Survivor] = []
        for m in modules:
            survivors.extend(mutate(m, Path(workdir)))   # 실패는 예외 전파 — 빈 survey 위장 금지
        if not survivors:
            typer.echo("갭 없음: 변경 모듈의 행위가 현재 스위트로 고정됨")
            return

        ledger_path = Path(ledger)
        led = load_ledger(ledger_path.read_text(encoding="utf-8") if ledger_path.exists() else "")
        fresh = new_survivors(survivors, led)   # 원장은 읽기만 — survey 는 영속 상태를 안 쓴다
        suite_summary = _suite_summary(Path(workdir), collect)
        tmpl = _prompt()
        prompts = [{"survivor_key": s.key, "prompt": _fill_prompt(tmpl, s, suite_summary)}
                   for s in fresh]

        Path(out).write_text(json.dumps({
            "survivors": [asdict(s) for s in survivors],
            "fresh": [asdict(s) for s in fresh],
            "suite_summary": suite_summary,
            "prompts": prompts,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        today = today_fn()
        typer.echo(build_report(survivors, led, today))
        if not fresh:
            typer.echo("새로 판정할 survivor 없음")
        else:
            typer.echo(f"{len(fresh)} fresh survivors need judgment — "
                       f"{out} 의 프롬프트로 Critic 을 dispatch 하세요.")

    @app.command(name="absorb")
    def absorb_cmd(
        verdicts: str = typer.Option(..., "--verdicts", help="Critic 판정 JSON (리스트)"),
        survey: str | None = typer.Option(None, "--survey", help="probe survey 아티팩트"),
        ledger: str = typer.Option("probe-ledger.yaml", "--ledger"),
    ) -> None:
        """Critic 판정을 원장에 흡수 → 영속 → 리포트. 도메인 밖 값·survey 에 없는 key 는 시끄럽게 거부."""
        ledger_path = Path(ledger)
        led = load_ledger(ledger_path.read_text(encoding="utf-8") if ledger_path.exists() else "")

        try:
            raw = json.loads(Path(verdicts).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            typer.echo(f"verdicts 파일을 읽을 수 없습니다: {e}", err=True)
            raise typer.Exit(1) from None
        if not isinstance(raw, list):
            typer.echo("verdicts 는 리스트여야 합니다.", err=True)
            raise typer.Exit(1)

        survivor_keys: set[str] | None = None
        fresh_keys: set[str] | None = None
        survey_data = None
        if survey is not None:
            try:
                survey_data = json.loads(Path(survey).read_text(encoding="utf-8"))
                survivor_keys = {_survivor_key(d) for d in survey_data["survivors"]}
                fresh_keys = {_survivor_key(d) for d in survey_data["fresh"]}
            except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
                typer.echo(f"survey 파일이 손상되었습니다: {e}", err=True)
                raise typer.Exit(1) from None

        # 원장을 손대기 전에 전부 검증한다 — 거부는 원장을 불변으로 둔다.
        objs: list[Verdict] = []
        for row in raw:
            vv = row.get("verdict")
            if vv not in _VERDICT_DOMAIN:
                typer.echo(f"알 수 없는 verdict 값: {vv!r} (key={row.get('survivor_key')})", err=True)
                raise typer.Exit(1)
            key = row.get("survivor_key")
            if survivor_keys is not None and key not in survivor_keys:
                typer.echo(f"survey 에 없는 survivor_key: {key}", err=True)
                raise typer.Exit(1)
            objs.append(Verdict(survivor_key=key, verdict=vv,
                                rationale=row.get("rationale", ""),
                                suggested_test_intent=row.get("suggested_test_intent")))

        # 부분 verdicts(빠진 fresh)는 삼키지 않고 알린다.
        if fresh_keys is not None:
            unjudged = fresh_keys - {v.survivor_key for v in objs}
            if unjudged:
                typer.echo("경고: 판정되지 않은 fresh survivor: " + ", ".join(sorted(unjudged)))

        today = today_fn()
        led = absorb(led, objs, today)
        ledger_path.write_text(dump_ledger(led), encoding="utf-8")

        if survey_data is not None:
            survivors = [Survivor(**d) for d in survey_data["survivors"]]
            typer.echo(build_report(survivors, led, today))
        else:
            typer.echo("survivor 문맥 생략됨(--survey 없음) — 원장만 갱신.")

    return app


def main() -> None:
    build_cli()()


if __name__ == "__main__":
    main()
