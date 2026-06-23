# ken path & install friction (root discovery) — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `ken` run from any directory in a project (root = nearest `ken.manifest.yaml`) and make the checked-in manifest clone-portable, **without changing ken-web, PostgresStore, or the store contract.**

**Architecture:** Root mode is **opt-in**. `registry.register`/`load_manifest` gain `root=None` (default = today's verbatim behavior). `FileStore` gains `relative_to_root=False`. Only the CLI sets it `True`: it discovers the root, anchors the three state files to it, stores artifact paths root-relative POSIX, and resolves them back to absolute on load (so the service layer is untouched). Then migrate the committed manifest and fix the stale README.

**Tech Stack:** Python 3.11, Typer CLI, pytest, ruff, PyYAML. No API key (pure filesystem; `FakeLLM` where cognition is needed).

**Spec:** `docs/superpowers/specs/2026-06-24-ken-path-root-discovery-design.md`

---

## File Structure

- `ken/src/ken/paths.py` — **new**: `discover_root` + state-file name constants. Pure, no IO beyond `Path.is_file`.
- `ken/src/ken/registry.py` — `register`/`load_manifest` take optional `root`.
- `ken/src/ken/stores/file_store.py` — `relative_to_root` flag; lazily derive root from the manifest dir.
- `ken/src/ken/cli.py` — discover root, anchor defaults, `FileStore(relative_to_root=True)`, catch outside-root `ValueError`, clean no-root error.
- `ken/README.md` — Install section + corrected CLI section.
- `ken.manifest.yaml` — **moved** from `ken/ken.manifest.yaml` to repo root.

---

## Chunk 1: engine layer (paths + registry + FileStore)

### Task 1: `discover_root` (paths.py)

**Files:**
- Create: `ken/src/ken/paths.py`
- Test: `ken/tests/test_paths.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# ken/tests/test_paths.py
from ken.paths import discover_root, MANIFEST_NAME


def test_finds_marker_in_start(tmp_path):
    (tmp_path / MANIFEST_NAME).write_text("[]", encoding="utf-8")
    assert discover_root(tmp_path) == tmp_path.resolve()


def test_finds_marker_in_ancestor(tmp_path):
    (tmp_path / MANIFEST_NAME).write_text("[]", encoding="utf-8")
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    assert discover_root(sub) == tmp_path.resolve()


def test_returns_none_when_absent(tmp_path):
    assert discover_root(tmp_path) is None
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError: ken.paths`)

Run: `cd ken && python -m pytest tests/test_paths.py -v`

- [ ] **Step 3: Implement `paths.py`**

```python
"""Project-root discovery for the ken CLI.

A ken project root is the nearest ancestor directory (including the start dir)
that contains `ken.manifest.yaml`. The CLI anchors its three state files to the
discovered root so commands work from any subdirectory. This is a CLI concern —
the engine/registry stays root-agnostic unless explicitly given a root.
"""

from __future__ import annotations

from pathlib import Path

MANIFEST_NAME = "ken.manifest.yaml"
QUESTIONS_NAME = "ken.questions.json"
LEDGER_NAME = "ken.attempts.jsonl"


def discover_root(start: Path) -> Path | None:
    """Nearest ancestor (incl. start) containing ken.manifest.yaml, else None."""
    start = start.resolve()
    for d in [start, *start.parents]:
        if (d / MANIFEST_NAME).is_file():
            return d
    return None
```

- [ ] **Step 4: Run — expect PASS**

Run: `cd ken && python -m pytest tests/test_paths.py -v`

- [ ] **Step 5: Commit**

```bash
git add ken/src/ken/paths.py ken/tests/test_paths.py
git commit -m "feat(ken): paths.discover_root (walk up for ken.manifest.yaml)"
```

---

### Task 2: registry root mode (opt-in)

**Files:**
- Modify: `ken/src/ken/registry.py` (`register` ~line 57-73, `load_manifest` ~line 30-48)
- Test: `ken/tests/test_registry.py` (keep the 2 existing tests as-is; add root-mode tests)

- [ ] **Step 1: Add the failing root-mode tests** (append to `test_registry.py`)

```python
import pytest
from ken.registry import _artifact_id


def test_root_mode_stores_relative_and_resolves_absolute(tmp_path):
    art = tmp_path / "sub" / "a.md"
    art.parent.mkdir(parents=True)
    art.write_text("hello\n", encoding="utf-8")
    man = tmp_path / "ken.manifest.yaml"

    ref = register(str(art), manifest_path=man, root=tmp_path)
    assert ref.path == str(art)  # returned path is absolute (resolved)

    import yaml
    raw = yaml.safe_load(man.read_text(encoding="utf-8"))
    assert raw[0]["path"] == "sub/a.md"  # stored relative POSIX

    entries = load_manifest(man, root=tmp_path)
    assert entries[0].path == str(art) and entries[0].content_hash  # resolved + live hash


def test_root_mode_collapses_path_spelling_to_one_id(tmp_path, monkeypatch):
    art = tmp_path / "a.md"
    art.write_text("x\n", encoding="utf-8")
    man = tmp_path / "ken.manifest.yaml"
    monkeypatch.chdir(tmp_path)  # so Path("./a.md").resolve() == tmp_path/a.md

    r_abs = register(str(art), manifest_path=man, root=tmp_path)
    r_dot = register("./a.md", manifest_path=man, root=tmp_path)  # run-from-root spelling
    assert r_abs.artifact_id == r_dot.artifact_id == _artifact_id("a.md")
    assert len(load_manifest(man, root=tmp_path)) == 1  # one entry, not two


def test_root_mode_rejects_outside_root(tmp_path):
    outside = tmp_path / "out.md"
    outside.write_text("x\n", encoding="utf-8")
    root = tmp_path / "proj"
    root.mkdir()
    man = root / "ken.manifest.yaml"
    with pytest.raises(ValueError, match="outside the ken root"):
        register(str(outside), manifest_path=man, root=root)
```

(The `monkeypatch.chdir(tmp_path)` in that test is required so `Path("./a.md").resolve()` resolves under `root`; it is already in the snippet above.)

- [ ] **Step 2: Run — expect FAIL** (`register() got an unexpected keyword argument 'root'`)

Run: `cd ken && python -m pytest tests/test_registry.py -v`

- [ ] **Step 3: Implement root mode in `registry.py`**

Replace `register` with:

```python
def register(path: str, *, manifest_path, root=None) -> ArtifactRef:
    """Register an artifact (idempotent on its stored key). Returns its ArtifactRef.

    root=None (default): store `path` verbatim, id from it, read it as given
    (today's behavior). root set: store the root-relative POSIX path, id from
    that, and return/read the resolved absolute path. A path outside root raises
    ValueError (fail-loud).
    """
    if root is None:
        stored = path
        read_path = path
    else:
        abs_path = Path(path).resolve()
        try:
            stored = abs_path.relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            raise ValueError(f"artifact {path} is outside the ken root {root}") from None
        read_path = str(abs_path)

    man = Path(manifest_path)
    raw = _load_raw(man)
    aid = _artifact_id(stored)
    if not any(entry["path"] == stored for entry in raw):
        raw.append({"artifact_id": aid, "path": stored})
        man.parent.mkdir(parents=True, exist_ok=True)
        man.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    else:
        aid = next(entry["artifact_id"] for entry in raw if entry["path"] == stored)
    return ArtifactRef(artifact_id=aid, path=read_path, content_hash=current_hash(read_path))
```

Replace `load_manifest` with:

```python
def load_manifest(manifest_path, *, root=None) -> list[ArtifactRef]:
    """Load manifest entries; hash is computed live, never read from the manifest.

    root=None: entry paths are used verbatim (cwd-relative, today's behavior).
    root set: each stored relative path is resolved to absolute against root, so
    the live hash works from any cwd. Returns [] if the manifest does not exist.
    """
    path = Path(manifest_path)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    refs: list[ArtifactRef] = []
    for entry in data:
        read_path = entry["path"] if root is None else str(Path(root).resolve() / entry["path"])
        refs.append(
            ArtifactRef(
                artifact_id=entry["artifact_id"],
                path=read_path,
                content_hash=current_hash(read_path),
            )
        )
    return refs
```

- [ ] **Step 4: Run — expect PASS** (all of `test_registry.py`, incl. the 2 unchanged tests)

Run: `cd ken && python -m pytest tests/test_registry.py -v`

- [ ] **Step 5: Commit**

```bash
git add ken/src/ken/registry.py ken/tests/test_registry.py
git commit -m "feat(ken): registry optional root mode (relative store, absolute resolve)"
```

---

### Task 3: FileStore `relative_to_root` flag

**Files:**
- Modify: `ken/src/ken/stores/file_store.py`
- Test: `ken/tests/test_store_contract.py` (add ONE guard test; do not change existing)

- [ ] **Step 1: Add the failing guard test** (append to `test_store_contract.py`)

```python
def test_filestore_default_is_verbatim_outside_any_root(tmp_path):
    # Guards the opt-in default: ken-web registers arbitrary paths verbatim.
    from ken.stores.file_store import FileStore

    art = tmp_path / "artifacts" / "a.md"
    art.parent.mkdir(parents=True)
    art.write_text("x\n", encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    s = FileStore(
        manifest=str(data_dir / "m.yaml"),
        questions=str(data_dir / "q.json"),
        ledger=str(data_dir / "l.jsonl"),
    )  # default relative_to_root=False
    ref = s.register(str(art))  # art is NOT under data_dir -> must NOT raise
    assert ref.path == str(art) and s.load_manifest()[0].path == str(art)
```

- [ ] **Step 2: Run — expect PASS (regression guard)**

Run: `cd ken && python -m pytest tests/test_store_contract.py::test_filestore_default_is_verbatim_outside_any_root -v`
Expected: PASS already (current FileStore is verbatim). This is a **regression guard**, not a RED→GREEN driver — it locks the verbatim default so a future "make root the default" change is caught. Keep it.

- [ ] **Step 3: Add the flag to `file_store.py`**

```python
from pathlib import Path  # add at top
```

```python
class FileStore:
    def __init__(
        self,
        *,
        manifest: str,
        questions: str,
        ledger: str,
        make_parents: bool = True,
        relative_to_root: bool = False,
    ):
        self._manifest = manifest
        self._questions = questions
        self._ledger = ledger
        self._mp = make_parents
        self._relative_to_root = relative_to_root

    def _root(self):
        # Lazily derived ONLY in root mode. Computed here (not __init__) so a
        # degenerate FileStore(manifest="x", ...) that never reaches the registry
        # (e.g. the fail-loud attempt test) is unaffected.
        return Path(self._manifest).resolve().parent if self._relative_to_root else None

    def load_manifest(self) -> list[ArtifactRef]:
        return _load_manifest(self._manifest, root=self._root())

    def register(self, path: str) -> ArtifactRef:
        return _register(path, manifest_path=self._manifest, root=self._root())
```

Leave `load_questions`/`save_questions`/`append_attempt`/`load_attempts` unchanged.

- [ ] **Step 4: Run the whole ken suite — expect PASS** (contract incl. new guard; registry; everything)

Run: `cd ken && python -m pytest -q`

- [ ] **Step 5: Commit**

```bash
git add ken/src/ken/stores/file_store.py ken/tests/test_store_contract.py
git commit -m "feat(ken): FileStore relative_to_root flag (opt-in root mode)"
```

---

## Chunk 2: CLI wiring

### Task 4: root-aware CLI store construction + per-command rewiring

**Files:**
- Modify: `ken/src/ken/cli.py`
- Test: `ken/tests/test_cli_v1.py` (add subdir + error tests)

- [ ] **Step 1: Add failing CLI tests** (append to `test_cli_v1.py`)

```python
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
    assert "coverage:" in r.stdout  # resolved the root manifest via walk-up


def test_cli_no_root_errors_cleanly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no ken.manifest.yaml anywhere up
    r = runner.invoke(app, ["coverage", "--as", "kr"])
    assert r.exit_code == 1
    assert "no ken.manifest.yaml found" in r.stdout + (r.stderr or "")


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
    assert "outside the ken root" in (r.stdout + (r.stderr or ""))
    assert "Traceback" not in r.stdout  # clean message, not a stack trace
```

Note: this repo runs Click 8.3 / Typer 0.24, where `CliRunner` always captures stdout/stderr **separately** and `r.stderr` returns `""` (never raises) when empty. `typer.echo(..., err=True)` lands in `r.stderr`; plain output is in `r.stdout`. The `r.stdout + (r.stderr or "")` union in the asserts above is the correct, version-safe pattern — keep it. (Do **not** pass `mix_stderr=` — that kwarg was removed in Click 8.2 and would raise `TypeError`.) The `"Traceback" not in r.stdout` assert is belt-and-suspenders, not load-bearing; the real discriminator is `exit_code == 1` **and** the message present in `stdout+stderr` (an *uncaught* `ValueError` gives exit 1 but no message in either stream).

- [ ] **Step 2: Run — expect FAIL** (commands still default to cwd files; subdir coverage finds nothing / crashes; no clean errors)

Run: `cd ken && python -m pytest tests/test_cli_v1.py -k "subdir or no_root or outside_root" -v`

- [ ] **Step 3: Add the CLI store helpers + imports**

At the top of `cli.py`, add imports and remove the now-superseded DEFAULT_* file constants usage (keep `DEFAULT_N_QUESTIONS`):

```python
from pathlib import Path

from ken.paths import LEDGER_NAME, MANIFEST_NAME, QUESTIONS_NAME, discover_root
```

Add helpers (after `_now`):

```python
def _resolve_paths(manifest, questions, ledger, *, allow_bootstrap):
    """Resolve the three state-file paths, anchoring to the discovered root.

    An explicit --manifest is used verbatim (root = its dir). Otherwise walk up
    for ken.manifest.yaml. allow_bootstrap=True (register only): a missing root
    bootstraps at cwd. allow_bootstrap=False: a missing root is a clean exit 1.
    Explicit --questions/--ledger always override the root-anchored default.
    """
    if manifest is not None:
        root = Path(manifest).resolve().parent
    else:
        found = discover_root(Path.cwd())
        if found is None:
            if not allow_bootstrap:
                typer.echo(
                    f"no {MANIFEST_NAME} found in {Path.cwd()} or any parent; "
                    "run 'ken register' first",
                    err=True,
                )
                raise typer.Exit(code=1)
            root = Path.cwd()
        else:
            root = found
        manifest = str(root / MANIFEST_NAME)
    questions = questions or str(root / QUESTIONS_NAME)
    ledger = ledger or str(root / LEDGER_NAME)
    return manifest, questions, ledger


def _store(manifest, questions, ledger, *, allow_bootstrap):
    m, q, ldg = _resolve_paths(manifest, questions, ledger, allow_bootstrap=allow_bootstrap)
    return FileStore(manifest=m, questions=q, ledger=ldg, relative_to_root=True)
```

- [ ] **Step 4: Rewire each command**

For **every** command, change the three file options' defaults from the `DEFAULT_*` strings to `None`:

```python
manifest: str = typer.Option(None, "--manifest", help="Manifest path (default: discovered root)."),
questions: str = typer.Option(None, "--questions", help="Questions store (default: beside manifest)."),
ledger: str = typer.Option(None, "--ledger", help="Attempt ledger (default: beside manifest)."),
```

(`register` only has `--manifest`; give it `None` too and drop its inline `DEFAULT_QUESTIONS/DEFAULT_LEDGER` FileStore args.)

Replace each command's `store = FileStore(...)` line with:
- `register`: `store = _store(manifest, None, None, allow_bootstrap=True)` then wrap the register call:
  ```python
  try:
      ref = service.register_artifact(path, store=store)
  except ValueError as exc:
      typer.echo(str(exc), err=True)
      raise typer.Exit(code=1)
  ```
- `due`, `save-questions`, `record-attempt`, `coverage`, `review`: `store = _store(manifest, questions, ledger, allow_bootstrap=False)` (save-questions has no `--ledger`; pass `None`).

Remove the module-level `DEFAULT_MANIFEST`/`DEFAULT_QUESTIONS`/`DEFAULT_LEDGER` constants once nothing references them (keep `DEFAULT_N_QUESTIONS`). Run `ruff check` to confirm no dangling references.

- [ ] **Step 5: Run the targeted CLI tests — expect PASS**

Run: `cd ken && python -m pytest tests/test_cli_v1.py -v`
Expected: new tests pass AND all pre-existing `test_cli_v1.py` tests still pass. The existing tests pass explicit `--manifest/--questions/--ledger` (all under `tmp_path`), so `_resolve_paths` uses them verbatim with root = `tmp_path` — artifacts under root → root mode works; outputs unchanged.

- [ ] **Step 6: Commit**

```bash
git add ken/src/ken/cli.py ken/tests/test_cli_v1.py
git commit -m "feat(ken): CLI discovers project root; runs from any subdir; clean path errors"
```

---

## Chunk 3: migration, README, full green

### Task 5: migrate the committed manifest

**Files:**
- Move: `ken/ken.manifest.yaml` → `ken.manifest.yaml` (repo root)

- [ ] **Step 1: Git-move the manifest**

```bash
git mv ken/ken.manifest.yaml ken.manifest.yaml
```

- [ ] **Step 2: Verify it resolves from the repo root and from a subdir**

From the repo root (with `ken` installed as a console script — `cd ken && pip install -e .` if needed):
```bash
cd "$(git rev-parse --show-toplevel)" && ken coverage --as kr
```
Expected: `coverage: N/10 (...)` with no `FileNotFoundError` (all 10 artifact paths resolve against repo root). Discovery works from **any** subdirectory too — e.g. `cd nexus && ken coverage --as kr` walks up to the repo-root manifest and resolves the same 10 artifacts. (The only reason to prefer the installed console script over `python -m ken.cli` is packaging/cwd ergonomics; root discovery itself works from any subdir.)

(No `ken.questions.json`/`ken.attempts.jsonl` exist yet, so coverage shows all orphans — that's expected; the check is that it RESOLVES, not that anything is vouched.)

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore(ken): move manifest to repo root (root-relative paths now resolve)"
```

### Task 6: README install + CLI correction

**Files:**
- Modify: `ken/README.md`

- [ ] **Step 1: Rewrite the Install + CLI sections**

Add an **Install** section and replace the stale `## CLI` block. Use the real commands and remove the non-existent `ken probe` and the unimplemented "TTL" claim:

```markdown
## Install

```bash
uv tool install ./ken        # or: pipx install ./ken  — installs the global `ken` command
pip install -e 'ken[dev]'    # development (editable + pytest/ruff)
pip install -e 'ken[postgres]'  # optional Postgres backend
```

## CLI

Run `ken` from anywhere in your project — the root is the nearest `ken.manifest.yaml`
(walking up from the current directory).

```bash
ken register PATH                              # register an artifact; prints its artifact_id
ken due --as PERSON                            # list due questions / artifacts needing questions
ken save-questions ARTIFACT_ID --hash HASH     # store questions (one per stdin line)
ken record-attempt --as PERSON --question QID --artifact AID --passed|--failed
ken coverage --as PERSON                       # covered/total, orphan hotlist, weakness map
ken review ARTIFACT_ID --as PERSON             # headless self-drive (needs ANTHROPIC_API_KEY)
```

A vouch is bound to the artifact's `content_hash` and goes **stale** when the artifact
changes; questions resurface on a spaced-repetition ladder until re-passed.
```

(Adjust the surrounding prose in `README.md` lines 8-12 to drop the "has a TTL" claim; describe staleness as content-hash change + spaced repetition. Do not document calendar TTL — that is slice C, not built.)

- [ ] **Step 2: Commit**

```bash
git add ken/README.md
git commit -m "docs(ken): README install section + correct CLI/staleness (drop stale probe/TTL)"
```

### Task 7: full green gate + lint

- [ ] **Step 1: ken suite + lint**

Run: `cd ken && python -m pytest -q && ruff check src tests`
Expected: all pass; ruff clean (no unused `DEFAULT_*`, no unused imports).

- [ ] **Step 2: ken-web api suite (shared FileStore default guard)**

Run: `cd ken-web/api && python -m pytest -q`
Expected: all pass (ken-web uses `FileStore` default `relative_to_root=False`, unchanged). If `ken-web/api` needs `ken` installed, install it editable first per that project's CI.

- [ ] **Step 3: Confirm no stray references**

Run: `cd ken && grep -rn --include='*.py' --include='*.md' "DEFAULT_MANIFEST\|DEFAULT_QUESTIONS\|DEFAULT_LEDGER\|ken probe" src tests README.md`
Expected: no matches (constants removed; README corrected). `ruff check` (Step 1) already catches unused `DEFAULT_*`/imports independently.

---

## Done criteria

- `ken` runs from any subdirectory (root = nearest `ken.manifest.yaml`); cross-cwd `FileNotFoundError` is gone.
- Manifest stores root-relative POSIX paths; `load_manifest` returns absolute → service layer untouched.
- Outside-root register and no-root commands fail with clean exit-1 messages, not tracebacks.
- ken-web, PostgresStore, and the store contract are unchanged and green; the regression-guard test locks the verbatim default.
- Committed manifest moved to repo root and resolves; README has Install + accurate CLI.
- `cd ken && python -m pytest -q` and `cd ken-web/api && python -m pytest -q` green; `ruff check` clean.
