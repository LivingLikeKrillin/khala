from typer.testing import CliRunner

from ken.cli import app
from ken.llm import FakeLLM


def test_register_probe_vouch_coverage(tmp_path, monkeypatch):
    man = tmp_path / "m.yaml"
    led = tmp_path / "ledger.jsonl"
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes the orders topic.\n", encoding="utf-8")
    runner = CliRunner()

    r = runner.invoke(app, ["register", str(art), "--manifest", str(man)])
    assert r.exit_code == 0
    aid = r.stdout.strip().split()[-1]  # cli prints the artifact_id

    # ONE _make_llm() result is shared across both LLM calls in a single `probe`,
    # so FakeLLM.responses must be [questions, verdict_json] IN CALL ORDER.
    monkeypatch.setattr(
        "ken.cli._make_llm",
        lambda: FakeLLM(responses=["Q1?\nQ2?", '{"passed": true, "score": 0.9, "rationale": "ok"}']),
    )
    r = runner.invoke(
        app,
        ["probe", aid, "--as", "kr", "--manifest", str(man), "--ledger", str(led)],
        input="answer1\nanswer2\n",  # one line per question, via stdin
    )
    assert r.exit_code == 0

    r = runner.invoke(app, ["coverage", "--manifest", str(man), "--ledger", str(led)])
    assert "1/1" in r.stdout
