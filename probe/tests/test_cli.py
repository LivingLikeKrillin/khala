"""Probe CLI — SPEC-probe-cli §7.

두 명령을 cosmic-ray 없이·라이브 Critic 없이 단위 테스트한다: 변이 실행 단계(mutate)와 변경 모듈
나열(list_modules)과 suite 수집(collect)을 주입하고, Critic 판정은 테스트가 쓰는 파일로 대체한다.
CliRunner 로 실제 명령 표면을 두드린다.

여기서 고정하는 불변식:
  · survey 는 fresh survivor마다 슬롯이 채워진 Critic 프롬프트를
    아티팩트로 낸다({module} 잔존 금지).
  · survey 는 원장을 쓰지 않는다(측정은 영속 상태에 read-only).
    runner 실패는 빈 survey 로 위장 안 함.
  · absorb 는 verdict 도메인 밖 값·survey에 없는 key 를 시끄럽게 거부하고 원장을 손대지 않는다.
  · 부분 verdicts(빠진 fresh)는 삼키지 않고 경고로 알린다.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from typer.testing import CliRunner

from khala.probe.cli import build_cli
from khala.probe.ledger import absorb, dump_ledger, load_ledger
from khala.probe.models import Survivor, Verdict

runner = CliRunner()
TODAY = datetime.date(2026, 7, 11)

_S1 = Survivor(module="pkg/a.py", lineno=10, operator="core/ReplaceТrue",
               mutation_diff="- return True\n+ return False")
_S2 = Survivor(module="pkg/b.py", lineno=20, operator="core/RemoveLoop",
               mutation_diff="- for x in xs\n+ for x in []")

_PROMPT = "module {module} line {lineno} op {operator} diff {mutation_diff} suite {suite_summary}"


def _cli(*, survivors=None, modules=("pkg/a.py",), collect_ok=True):
    """survivors 를 그대로 돌려주는 가짜 mutate 와, 고정 모듈 목록을 붙인 CLI."""
    survivors = list(survivors if survivors is not None else [_S1, _S2])

    def mutate(module_path, workdir):
        return survivors

    def list_modules(base):
        return list(modules)

    def collect(workdir):
        if not collect_ok:
            raise RuntimeError("collect boom")
        return "69 tests collected in 0.4s"

    return build_cli(
        mutate=mutate,
        list_modules=list_modules,
        collect=collect,
        prompt_template=_PROMPT,
        today_fn=lambda: TODAY,
    )


# ── §5.1 survey ───────────────────────────────────────────────────────────────

def test_survey_writes_artifact_with_filled_prompts(tmp_path: Path):
    out = tmp_path / "probe-survey.json"
    res = runner.invoke(_cli(), ["survey", "--out", str(out),
                                 "--ledger", str(tmp_path / "probe-ledger.yaml")])
    assert res.exit_code == 0, res.output
    art = json.loads(out.read_text(encoding="utf-8"))
    assert {s["module"] for s in art["survivors"]} == {"pkg/a.py", "pkg/b.py"}
    assert len(art["fresh"]) == 2
    prompts = art["prompts"]
    assert len(prompts) == 2
    for p in prompts:
        assert "{module}" not in p["prompt"] and "{suite_summary}" not in p["prompt"]
        assert "69 tests collected" in p["prompt"]      # suite_summary substituted


def test_survey_zero_modules_exits_clean(tmp_path: Path):
    out = tmp_path / "s.json"
    res = runner.invoke(_cli(modules=()), ["survey", "--out", str(out)])
    assert res.exit_code == 0
    assert "변경된 소스 모듈 없음" in res.output
    assert not out.exists()


def test_survey_zero_survivors_reports_no_gap(tmp_path: Path):
    out = tmp_path / "s.json"
    res = runner.invoke(_cli(survivors=[]), ["survey", "--out", str(out)])
    assert res.exit_code == 0
    assert "갭 없음" in res.output


def test_survey_all_already_judged_needs_no_critic(tmp_path: Path):
    ledger_path = tmp_path / "probe-ledger.yaml"
    seeded = absorb(load_ledger(""),
                    [Verdict(_S1.key, "real-gap", "r"), Verdict(_S2.key, "equivalent", "r")], TODAY)
    ledger_path.write_text(dump_ledger(seeded), encoding="utf-8")
    out = tmp_path / "s.json"
    res = runner.invoke(_cli(), ["survey", "--out", str(out), "--ledger", str(ledger_path)])
    assert res.exit_code == 0
    assert "새로 판정할 survivor 없음" in res.output
    art = json.loads(out.read_text(encoding="utf-8"))
    assert art["fresh"] == []
    assert art["prompts"] == []


def test_survey_does_not_write_the_ledger(tmp_path: Path):
    ledger_path = tmp_path / "probe-ledger.yaml"
    ledger_path.write_text("waivers: []\n", encoding="utf-8")
    before = ledger_path.read_bytes()
    runner.invoke(_cli(), ["survey", "--out", str(tmp_path / "s.json"),
                           "--ledger", str(ledger_path)])
    assert ledger_path.read_bytes() == before      # 측정은 영속 상태 read-only


def test_survey_collect_failure_falls_back(tmp_path: Path):
    out = tmp_path / "s.json"
    res = runner.invoke(_cli(collect_ok=False), ["survey", "--out", str(out)])
    assert res.exit_code == 0
    art = json.loads(out.read_text(encoding="utf-8"))
    assert art["suite_summary"] == "스위트 요약 수집 실패"   # survey 는 그래도 나온다


def test_survey_runner_failure_is_not_an_empty_survey(tmp_path: Path):
    def boom(module_path, workdir):
        raise RuntimeError("cosmic-ray exec 실패")

    app = build_cli(mutate=boom, list_modules=lambda base: ["pkg/a.py"],
                    collect=lambda w: "x", prompt_template=_PROMPT, today_fn=lambda: TODAY)
    out = tmp_path / "s.json"
    res = runner.invoke(app, ["survey", "--out", str(out)])
    assert res.exit_code != 0            # fail-open 금지
    assert not out.exists()


# ── §5.3 absorb ───────────────────────────────────────────────────────────────

def _survey_file(tmp_path: Path, survivors, fresh) -> Path:
    p = tmp_path / "probe-survey.json"
    p.write_text(json.dumps({
        "survivors": [{"module": s.module, "lineno": s.lineno, "operator": s.operator,
                       "mutation_diff": s.mutation_diff} for s in survivors],
        "fresh": [{"module": s.module, "lineno": s.lineno, "operator": s.operator,
                   "mutation_diff": s.mutation_diff} for s in fresh],
        "suite_summary": "69 tests collected", "prompts": [],
    }, ensure_ascii=False), encoding="utf-8")
    return p


def _verdicts_file(tmp_path: Path, rows) -> Path:
    p = tmp_path / "verdicts.json"
    p.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return p


def test_absorb_folds_verdicts_and_headlines_biting(tmp_path: Path):
    survey = _survey_file(tmp_path, [_S1, _S2], [_S1, _S2])
    verdicts = _verdicts_file(tmp_path, [
        {"survivor_key": _S1.key, "verdict": "real-gap", "rationale": "행위 갭"},
        {"survivor_key": _S2.key, "verdict": "equivalent", "rationale": "동치"},
    ])
    ledger_path = tmp_path / "probe-ledger.yaml"
    res = runner.invoke(_cli(), ["absorb", "--verdicts", str(verdicts),
                                 "--survey", str(survey), "--ledger", str(ledger_path)])
    assert res.exit_code == 0, res.output
    assert "unwaived real-gap: 1" in res.output      # real-gap 1, equivalent 강등
    assert ledger_path.exists()
    reloaded = load_ledger(ledger_path.read_text(encoding="utf-8"))
    assert reloaded.waivers[_S1.key]["verdict"] == "real-gap"
    assert reloaded.waivers[_S2.key]["verdict"] == "equivalent"   # 누락 안 됨


def test_absorb_rejects_key_not_in_survey(tmp_path: Path):
    survey = _survey_file(tmp_path, [_S1], [_S1])
    verdicts = _verdicts_file(tmp_path, [
        {"survivor_key": "ghost/x.py:1:Op", "verdict": "real-gap", "rationale": "r"},
    ])
    ledger_path = tmp_path / "probe-ledger.yaml"
    ledger_path.write_text("waivers: []\n", encoding="utf-8")
    before = ledger_path.read_bytes()
    res = runner.invoke(_cli(), ["absorb", "--verdicts", str(verdicts),
                                 "--survey", str(survey), "--ledger", str(ledger_path)])
    assert res.exit_code != 0
    assert "ghost/x.py:1:Op" in res.output
    assert ledger_path.read_bytes() == before        # 원장 불변


def test_absorb_rejects_verdict_value_outside_domain(tmp_path: Path):
    survey = _survey_file(tmp_path, [_S1], [_S1])
    verdicts = _verdicts_file(tmp_path, [
        {"survivor_key": _S1.key, "verdict": "probably-fine", "rationale": "r"},
    ])
    ledger_path = tmp_path / "probe-ledger.yaml"
    ledger_path.write_text("waivers: []\n", encoding="utf-8")
    before = ledger_path.read_bytes()
    res = runner.invoke(_cli(), ["absorb", "--verdicts", str(verdicts),
                                 "--survey", str(survey), "--ledger", str(ledger_path)])
    assert res.exit_code != 0
    assert "probably-fine" in res.output
    assert ledger_path.read_bytes() == before


def test_absorb_warns_about_unjudged_fresh(tmp_path: Path):
    survey = _survey_file(tmp_path, [_S1, _S2], [_S1, _S2])
    verdicts = _verdicts_file(tmp_path, [
        {"survivor_key": _S1.key, "verdict": "real-gap", "rationale": "r"},   # _S2 빠짐
    ])
    ledger_path = tmp_path / "probe-ledger.yaml"
    res = runner.invoke(_cli(), ["absorb", "--verdicts", str(verdicts),
                                 "--survey", str(survey), "--ledger", str(ledger_path)])
    assert res.exit_code == 0
    assert _S2.key in res.output                     # 빠진 fresh 를 이름으로 알림
    reloaded = load_ledger(ledger_path.read_text(encoding="utf-8"))
    assert _S1.key in reloaded.waivers               # 있는 건 흡수


def test_absorb_malformed_verdicts_leaves_ledger_untouched(tmp_path: Path):
    survey = _survey_file(tmp_path, [_S1], [_S1])
    bad = tmp_path / "verdicts.json"
    bad.write_text("{ not json", encoding="utf-8")
    ledger_path = tmp_path / "probe-ledger.yaml"
    ledger_path.write_text("waivers: []\n", encoding="utf-8")
    before = ledger_path.read_bytes()
    res = runner.invoke(_cli(), ["absorb", "--verdicts", str(bad),
                                 "--survey", str(survey), "--ledger", str(ledger_path)])
    assert res.exit_code != 0
    assert ledger_path.read_bytes() == before


# ── §5.4 packaging ────────────────────────────────────────────────────────────

def test_help_lists_both_commands():
    res = runner.invoke(_cli(), ["--help"])
    assert res.exit_code == 0
    assert "survey" in res.output and "absorb" in res.output
