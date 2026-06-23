# Design Spec — ken engine v2 / Slice B: path & install friction (root discovery)

- **Date:** 2026-06-24
- **Status:** Design (brainstorming output) — pending spec review + user approval
- **Builds on:** ken v0/v1 + ken-web v0.1 + S2 Postgres + Slice A (all merged, #29–#38). Second of three "engine v2 friction" slices (A done; C calendar-TTL deferred).
- **Decisions locked (from brainstorming):** **Root model = manifest-as-marker** (walk up for `ken.manifest.yaml`; root = its directory). **Artifact paths stored root-relative POSIX, resolved to absolute on load** (service layer unchanged). **Root mode is opt-in** — `registry`'s `root` defaults to `None` (= today's verbatim-path behavior); `FileStore` gains `relative_to_root=False`; **only the CLI turns it on**. This keeps ken-web's FileStore mode, the store contract, and existing registry tests behaving exactly as today. **PostgresStore untouched** (server controls its own cwd; no root concept). Migrate the existing committed manifest. Fix the stale README. Out of scope: calendar TTL (C), Postgres root handling, `.gitignore` for local state.

---

## 1. Goal

Let `ken` be run from **any directory** within a project, and make the checked-in manifest **clone-portable**. Today every command resolves artifact paths against the current working directory, so running from anywhere other than where you registered crashes.

## 2. The friction (verified in current code + committed data)

1. **Cross-cwd crash.** `registry.load_manifest` (`ken/src/ken/registry.py:30-48`) calls `current_hash(entry["path"])` for **every** entry, and `current_hash` (`registry.py:24-27`) does `Path(path).read_text()` — relative to cwd. So running *any* command (even `coverage`) from a directory where the stored relative paths don't resolve raises `FileNotFoundError` on the first entry.
2. **artifact_id keyed on the raw path string.** `_artifact_id(path) = sha256(path)[:12]` (`registry.py:19-21`). `register ./x`, `register x`, and `register /abs/x` produce three different ids for the same file → silent duplicates.
3. **State files are cwd-relative.** The CLI defaults are `ken.manifest.yaml`, `ken.questions.json`, `ken.attempts.jsonl` at cwd (`cli.py:27-29`), with no discovery — state is tied to wherever you happen to run.
4. **Existing data proves the bug.** The committed `ken/ken.manifest.yaml` registers 10 khala artifacts with **repo-root-relative** paths (`adr/ADR-0001-…md`, `nexus/nexus/search/hybrid.py`) — but the manifest sits in `ken/`. The paths only resolve when run from the **repo root**, not from `ken/`, and nothing records that. This is friction #1 already biting.
5. **Stale README.** `ken/README.md` documents a non-existent `ken probe ARTIFACT_ID` command and claims a vouch "has a TTL" — neither is true (the CLI is `register/due/save-questions/record-attempt/coverage/review`; TTL is unbuilt slice C). The README is the install/onboarding surface and has no Install section.

## 3. Root model: manifest-as-marker

A `ken` **project root** is the directory containing `ken.manifest.yaml`. Discovery walks up from cwd:

```python
def discover_root(start: Path) -> Path | None:
    """Nearest ancestor (incl. start) containing ken.manifest.yaml, else None."""
    for d in [start, *start.parents]:
        if (d / "ken.manifest.yaml").is_file():
            return d
    return None
```

- The three state files live **at root**: `root/ken.manifest.yaml`, `root/ken.questions.json`, `root/ken.attempts.jsonl`.
- **`register` runs discovery first.** It calls `discover_root(cwd)`: if a root is found, it **anchors to that root** (appends to the existing `root/ken.manifest.yaml`) even when run from a subdirectory; only if discovery returns `None` does it **bootstrap** a new `ken.manifest.yaml` at **cwd** (root = cwd). `register` is the *only* command that proceeds when discovery returns `None`.
- **Non-register commands with no root found** (`due`/`coverage`/`review`/`save-questions`/`record-attempt`): print a clear error (`no ken.manifest.yaml found in <cwd> or any parent; run 'ken register' first`) and exit 1, rather than silently operating on an empty cwd store.

This lives in the **CLI layer** (`ken/src/ken/paths.py`, a new ~15-line pure helper module + the CLI wiring). The flags `--manifest/--questions/--ledger` remain as explicit overrides; when a flag is given, it is used verbatim and discovery is skipped for that file. The CLI always constructs its `FileStore` with `relative_to_root=True`.

## 4. Paths: store root-relative, resolve to absolute on load

The read/write boundary (registry) gains an **optional** `root` (default `None` = today's verbatim behavior, so all existing callers are unaffected):

- **`register(path, *, manifest_path, root=None)`**:
  - `root is None` → **today's behavior**: store `path` verbatim, `artifact_id = _artifact_id(path)`, return `ArtifactRef(id, path, current_hash(path))`.
  - `root` set → resolve `path` to absolute; compute **root-relative POSIX** via `Path(abs).relative_to(root).as_posix()`. If `path` is **not** under `root`, raise `ValueError("artifact <path> is outside the ken root <root>")` (fail-loud). Store the relative POSIX string. `artifact_id = _artifact_id(relative_posix)` — so spelling variants (`./x`, `x`, abs) collapse to one id. Return `ArtifactRef(id, abs_path, current_hash(abs_path))`.
- **`load_manifest(manifest_path, *, root=None)`**:
  - `root is None` → today's behavior: `ArtifactRef(id, stored_path, current_hash(stored_path))` (verbatim, cwd-relative).
  - `root` set → for each entry resolve `abs = (root / entry["path"])`; `ArtifactRef(id, str(abs), current_hash(str(abs)))`. The live hash is computed against the **absolute** path, so it works from any cwd.

**Why this keeps the service layer untouched:** in root mode `ArtifactRef.path` is **absolute**, so `service.ensure_questions`/`grade_answer` (`Path(ref.path).read_text`, `service.py:58` and `:132`) and all derivations are unchanged.

`FileStore.__init__` gains `relative_to_root: bool = False`. When `True`, it derives `root = Path(self._manifest).resolve().parent` and passes it into the two registry calls; when `False` (default), it calls them with `root=None` (today's behavior). `root` is computed lazily inside `register`/`load_manifest`, so a degenerate `FileStore(manifest="x", …)` that never reaches the registry (e.g. the fail-loud attempt test) is unaffected. The constructor stays backward-compatible for ken-web and the contract test (both keep the default `False`).

**CLI surfaces the outside-root error cleanly.** `register`'s `ValueError` propagates `registry → service.register_artifact → cli.register`; `cli.register` wraps the call in `try/except ValueError` and re-emits `typer.echo(str(e), err=True); raise typer.Exit(1)` — matching the no-root command UX (a clean exit 1, never a traceback).

## 5. PostgresStore + ken-web: unchanged

`PostgresStore.register`/`load_manifest` (`stores/postgres_store.py:38-53`) keep storing/returning the path verbatim and deriving `_artifact_id(path)` from it. The web server controls its own working directory and has no filesystem "project root"; root discovery is a local-CLI concern.

**ken-web FileStore mode is unchanged** because root mode is opt-in. `ken-web/api/.../deps.py` constructs `FileStore(manifest=…)` with the **default** `relative_to_root=False`, so the web API keeps registering arbitrary `req.path` values verbatim (no outside-root constraint). This is the reason root mode is a flag rather than always-on: FileStore is shared between the CLI and ken-web, and only the CLI wants root semantics.

**Contract parity is preserved with the contract test unchanged.** `test_store_contract.py` constructs `FileStore(manifest=…, questions=…, ledger=…)` with the default `relative_to_root=False`, i.e. today's verbatim behavior — so `test_register_roundtrip_and_idempotent` (`man[0].path == str(art)`, `r1.id == r2.id`) passes exactly as before, and `test_append_attempt_fail_loud` (`FileStore(manifest="x", …)`) is unaffected (it never reaches the registry and root is computed lazily). Root mode is covered by **new registry/FileStore unit tests** (§10), not by the cross-backend contract (Postgres has no root, so root mode is intentionally outside the parity contract).

## 6. Migration of the committed manifest

- Move `ken/ken.manifest.yaml` → repo-root `ken.manifest.yaml` (git move). Its paths are already clean repo-root-relative POSIX (`adr/…`, `nexus/…`; no `./`, no backslashes), so with root = repo root they resolve correctly. `artifact_id`s are unchanged because the move is byte-identical YAML — nothing recomputes ids. No committed `questions`/`attempts` files exist, so nothing else migrates.
- **Forward-consistent (not a coincidence):** the committed ids are `sha256` of the (already repo-root-relative) stored strings, and the new root-mode `_artifact_id` keys on the repo-root-relative POSIX string. So re-registering any of these 10 files from anywhere under the repo root — by abs path, `./` path, or from a subdir — now normalizes to the *same* relative string → the **same** id. The migration is forward-consistent; ids will not silently drift and orphan coverage.
- Verify post-move: from the repo root, `ken coverage` resolves all 10 artifacts (live hash succeeds for each) — and from `ken/` (a subdir) it now *also* works via walk-up.

## 7. README fix (`ken/README.md`)

- **Add an Install section:** `uv tool install ./ken` or `pipx install ./ken` (installs the global `ken` console script, defined at `pyproject.toml [project.scripts] ken = "ken.cli:app"`); `pip install -e 'ken[dev]'` for development; `pip install -e 'ken[postgres]'` for the optional Postgres backend.
- **Correct the CLI section:** replace the stale `ken probe`/TTL prose with the real v1 commands (`register`, `due`, `save-questions`, `record-attempt`, `coverage`, `review`) and a one-line note: "run from anywhere in the project — root is the nearest `ken.manifest.yaml`."
- Remove the unimplemented "has a TTL" claim; describe current staleness accurately (content-hash change + spaced-repetition re-test). (Calendar TTL is slice C; do not document it as existing.)

## 8. Files touched

- **Create:** `ken/src/ken/paths.py` (`discover_root`, root-anchored default file paths helper).
- **Modify:** `ken/src/ken/registry.py` (`register`/`load_manifest` take optional `root=None`; `None` = today's behavior; set = relative-store + absolute-resolve + outside-root `ValueError`).
- **Modify:** `ken/src/ken/stores/file_store.py` (`relative_to_root=False` flag; when `True` derive `root` from manifest dir and pass to registry).
- **Modify:** `ken/src/ken/cli.py` (discover root; anchor default file paths; construct `FileStore(relative_to_root=True)`; catch outside-root `ValueError` in `register`; clear no-root error for non-register commands).
- **Modify:** `ken/README.md` (Install + corrected CLI sections).
- **Move:** `ken/ken.manifest.yaml` → `ken.manifest.yaml` (repo root).
- **Tests:**
  - `ken/tests/test_paths.py` (new) — `discover_root`.
  - `ken/tests/test_registry.py` — **the two existing tests keep their current calls** (`register(..., manifest_path=man)` / `load_manifest(man)`) and stay green because `root` defaults to `None`; **add** new cases for root mode (relative store, `./`-prefix id-collapse, absolute-resolve on load, outside-root `ValueError`).
  - `ken/tests/test_cli_v1.py` — register under root then run `coverage`/`due` from a **subdir** (`monkeypatch.chdir`) succeeds; non-register command with no manifest anywhere → exit 1 + actionable message; outside-root `register` → exit 1 + clean message (not traceback).
  - `test_store_contract.py` stays **green unchanged** (default `relative_to_root=False`).
- **Green gate includes the ken-web api suite** (`ken-web/api`), not just `ken`, to confirm the shared FileStore default behavior is unaffected. (CI already runs both jobs.)

## 9. Error handling / invariants

- **Outside-root register → `ValueError`, fail-loud** (no silent absolute fallback).
- **No-root non-register command → exit 1 with an actionable message** (not a stack trace, not a silent empty store).
- **Fail-loud writes / fail-closed grade / live hash** invariants are all preserved (no change to attempt/question write paths or judge).
- **Clone-portability:** the checked-in manifest stores only relative POSIX paths (no absolute, no backslashes) so it is identical across machines/OSes.

## 10. Testing (no API key — pure filesystem + FakeLLM where needed)

- `discover_root`: finds marker in cwd, in an ancestor, returns None when absent.
- `registry.register`: stores root-relative POSIX for an abs input and for a `./`-prefixed input (same id); raises on an outside-root path.
- `registry.load_manifest`: returns absolute `ArtifactRef.path`; live hash succeeds when invoked with cwd ≠ root.
- CLI: register an artifact under root, then invoke `coverage`/`due` with the runner from a **subdirectory** (e.g. via `monkeypatch.chdir`) and assert success + correct artifact resolution; invoke a non-register command with no manifest anywhere and assert exit 1 + the actionable message.
- Full suite + `ruff check` green; the store contract suite unchanged and green (FileStore param always; Postgres param gated on `KEN_TEST_DATABASE_URL`).

## 11. YAGNI / scope discipline

- No `ken init`, no `.ken/` directory, no env-var root (rejected in brainstorming for the minimal manifest-marker model).
- Root mode is a single opt-in flag (`relative_to_root` / registry `root=None` default), not a rewrite of the storage layer — the smallest change that scopes new behavior to the CLI without touching ken-web, PostgresStore, or the store contract.
- README changes are limited to install + correcting what's already wrong; no broad doc rewrite.
