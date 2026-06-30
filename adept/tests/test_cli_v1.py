from typer.testing import CliRunner

from khala.adept.cli import app
from khala.adept.llm import FakeLLM
from khala.adept.questions import load_questions, make_question_id

runner = CliRunner()


def _register(man, art_path):
    r = runner.invoke(app, ["register", str(art_path), "--manifest", str(man)])
    assert r.exit_code == 0, r.stdout
    return r.stdout.strip().split()[-1]


def _current_hash(art_path):
    from khala.adept.registry import current_hash

    return current_hash(str(art_path))


def test_due_flags_needs_questions(tmp_path):
    man = tmp_path / "m.yaml"
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes the orders topic.\n", encoding="utf-8")
    aid = _register(man, art)

    r = runner.invoke(
        app,
        ["due", "--as", "kr", "--manifest", str(man),
         "--questions", str(tmp_path / "q.json"), "--ledger", str(tmp_path / "l.jsonl")],
    )
    assert r.exit_code == 0
    assert f"needs-questions {aid}" in r.stdout


def test_save_questions_rejects_wrong_hash(tmp_path):
    man = tmp_path / "m.yaml"
    art = tmp_path / "a.md"
    art.write_text("content\n", encoding="utf-8")
    aid = _register(man, art)
    store = tmp_path / "q.json"

    r = runner.invoke(
        app,
        ["save-questions", aid, "--hash", "sha256:WRONG",
         "--manifest", str(man), "--questions", str(store)],
        input="Q1?\nQ2?\n",
    )
    assert r.exit_code != 0
    h, qs = load_questions(aid, store_path=store)
    assert qs == []  # nothing stored on rejection


def test_save_questions_stores_on_correct_hash(tmp_path):
    man = tmp_path / "m.yaml"
    art = tmp_path / "a.md"
    art.write_text("content\n", encoding="utf-8")
    aid = _register(man, art)
    store = tmp_path / "q.json"
    h = _current_hash(art)

    r = runner.invoke(
        app,
        ["save-questions", aid, "--hash", h,
         "--manifest", str(man), "--questions", str(store)],
        input="Q1?\nQ2?\n",
    )
    assert r.exit_code == 0, r.stdout
    sh, qs = load_questions(aid, store_path=store)
    assert sh == h and [q.text for q in qs] == ["Q1?", "Q2?"]


def test_due_lists_saved_but_unanswered_questions(tmp_path):
    man = tmp_path / "m.yaml"
    art = tmp_path / "a.md"
    art.write_text("content\n", encoding="utf-8")
    aid = _register(man, art)
    store = tmp_path / "q.json"
    h = _current_hash(art)

    runner.invoke(
        app,
        ["save-questions", aid, "--hash", h, "--manifest", str(man), "--questions", str(store)],
        input="Q1?\n",
    )
    r = runner.invoke(
        app,
        ["due", "--as", "kr", "--manifest", str(man),
         "--questions", str(store), "--ledger", str(tmp_path / "l.jsonl")],
    )
    assert r.exit_code == 0
    qid = make_question_id(aid, h, 0)
    assert qid in r.stdout
    assert "needs-questions" not in r.stdout  # questions exist; just unanswered


def test_record_attempt_then_coverage_moves(tmp_path):
    man = tmp_path / "m.yaml"
    art = tmp_path / "a.md"
    art.write_text("content\n", encoding="utf-8")
    aid = _register(man, art)
    store = tmp_path / "q.json"
    ledger = tmp_path / "l.jsonl"
    h = _current_hash(art)

    runner.invoke(
        app,
        ["save-questions", aid, "--hash", h, "--manifest", str(man), "--questions", str(store)],
        input="Q1?\n",
    )
    qid = make_question_id(aid, h, 0)

    # before: not covered
    r = runner.invoke(
        app,
        ["coverage", "--as", "kr", "--manifest", str(man),
         "--questions", str(store), "--ledger", str(ledger)],
    )
    assert "0/1" in r.stdout

    r = runner.invoke(
        app,
        ["record-attempt", "--as", "kr", "--question", qid, "--artifact", aid,
         "--passed", "--manifest", str(man), "--questions", str(store), "--ledger", str(ledger)],
    )
    assert r.exit_code == 0, r.stdout

    r = runner.invoke(
        app,
        ["coverage", "--as", "kr", "--manifest", str(man),
         "--questions", str(store), "--ledger", str(ledger)],
    )
    assert "1/1" in r.stdout


def test_coverage_shows_weakness(tmp_path):
    man = tmp_path / "m.yaml"
    art = tmp_path / "a.md"
    art.write_text("content\n", encoding="utf-8")
    aid = _register(man, art)
    store = tmp_path / "q.json"
    ledger = tmp_path / "l.jsonl"
    h = _current_hash(art)

    runner.invoke(
        app,
        ["save-questions", aid, "--hash", h, "--manifest", str(man), "--questions", str(store)],
        input="Q1?\n",
    )
    qid = make_question_id(aid, h, 0)
    runner.invoke(
        app,
        ["record-attempt", "--as", "kr", "--question", qid, "--artifact", aid,
         "--failed", "--manifest", str(man), "--questions", str(store), "--ledger", str(ledger)],
    )
    r = runner.invoke(
        app,
        ["coverage", "--as", "kr", "--manifest", str(man),
         "--questions", str(store), "--ledger", str(ledger)],
    )
    assert "weakness" in r.stdout.lower()
    assert qid in r.stdout


def test_review_headless_records_per_question(tmp_path, monkeypatch):
    man = tmp_path / "m.yaml"
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes the orders topic.\n", encoding="utf-8")
    aid = _register(man, art)
    store = tmp_path / "q.json"
    ledger = tmp_path / "l.jsonl"
    h = _current_hash(art)

    # Call order: probe(1) -> grade Q1 pass(1) -> grade Q2 fail(1) -> remediate Q2(1)
    monkeypatch.setattr(
        "khala.adept.cli._make_llm",
        lambda: FakeLLM(responses=[
            "Q1?\nQ2?",
            '{"passed": true,  "score": 0.9, "rationale": "ok"}',
            '{"passed": false, "score": 0.1, "rationale": "no"}',
            "study the orders topic section",
        ]),
    )
    r = runner.invoke(
        app,
        ["review", aid, "--as", "kr", "--manifest", str(man),
         "--questions", str(store), "--ledger", str(ledger)],
        input="answer1\nanswer2\n",
    )
    assert r.exit_code == 0, r.stdout
    assert "study the orders topic section" in r.stdout  # remediation surfaced for the failed Q

    q1_id = make_question_id(aid, h, 0)
    q2_id = make_question_id(aid, h, 1)

    r = runner.invoke(
        app,
        ["coverage", "--as", "kr", "--manifest", str(man),
         "--questions", str(store), "--ledger", str(ledger)],
    )
    # one artifact, Q2 last-failed -> orphan -> 0/1 (per-artifact coverage)
    assert "0/1" in r.stdout
    # the discriminator: per-question recording means ONLY Q2 is in the weakness map
    assert q2_id in r.stdout
    assert q1_id not in r.stdout


def test_cli_runs_from_subdir(tmp_path, monkeypatch):
    # register at root, then run coverage from a nested cwd -> must resolve, not crash
    root = tmp_path
    art = root / "doc.md"
    art.write_text("Payments publish orders.\n", encoding="utf-8")
    monkeypatch.chdir(root)
    r = runner.invoke(app, ["register", str(art)])
    assert r.exit_code == 0, r.stdout

    sub = root / "a" / "b"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    r = runner.invoke(app, ["coverage", "--as", "kr"])
    assert r.exit_code == 0, r.stdout
    assert "0/1" in r.stdout  # walk-up found the root manifest + its 1 artifact (not 0/0)


def test_cli_no_root_errors_cleanly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no adept.manifest.yaml anywhere up
    r = runner.invoke(app, ["coverage", "--as", "kr"])
    assert r.exit_code == 1
    assert "no adept.manifest.yaml found" in (r.stdout + (r.stderr or ""))


def test_cli_register_outside_root_errors_cleanly(tmp_path, monkeypatch):
    # bootstrap a root, then try to register a file outside it
    root = tmp_path / "proj"
    root.mkdir()
    monkeypatch.chdir(root)
    here = root / "in.md"
    here.write_text("x\n", encoding="utf-8")
    runner.invoke(app, ["register", str(here)])  # bootstraps root manifest

    outside = tmp_path / "out.md"
    outside.write_text("x\n", encoding="utf-8")
    r = runner.invoke(app, ["register", str(outside)])
    assert r.exit_code == 1
    assert "outside the adept root" in (r.stdout + (r.stderr or ""))
    assert "Traceback" not in r.stdout  # clean message, not a stack trace
