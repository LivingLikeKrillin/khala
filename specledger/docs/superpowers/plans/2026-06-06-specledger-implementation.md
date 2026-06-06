# Specledger Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build specledger — a Python MCP server + Claude Code PreToolUse hook that records AI-generated ADRs/design-specs in a consistent format, enforces accountable review (AI critique → human issue-disposition → sign-off) before code is written, and optionally publishes approved docs to Khala.

**Architecture:** A pure, fully unit-testable **core library** (`src/specledger/`) holds all logic: id/hash primitives, a frontmatter+sidecar data layer, ledger operations, the review gate, and the enforcement gate. A thin **MCP adapter** (`server.py`) exposes the core as MCP tools. A standalone **PreToolUse hook** (`hooks/pretooluse_gate.py`) calls the gate to block unapproved code edits. Files are the single source of truth; `.specledger/` holds per-consumer-project runtime state.

**Tech Stack:** Python 3.11+, `mcp` (FastMCP server), `anthropic` (independent critique LLM, mocked in tests), `pyyaml` (frontmatter/config), `pytest`, `ruff`. Spec: `docs/superpowers/specs/2026-06-06-specledger-adr-sdd-governance-mcp-design.md`.

**Conventions for every task:** Follow @superpowers:test-driven-development (red → green → refactor). One behavior per test. Commit after each green test. Run `ruff check .` before each commit.

---

## File Structure

```
specledger/
  pyproject.toml                         # packaging, deps, pytest/ruff config
  README.md                              # what it is, install, hook registration
  src/specledger/
    __init__.py
    errors.py            # typed exceptions (IdCollision, ImmutableArtifact, GateDenied, ...)
    ids.py               # next_adr_id(), slugify(), make_spec_id() with collision suffix
    hashing.py           # content_hash(body) — body-only, normalized
    frontmatter.py       # split(text)->(meta,body), render(meta,body)->text
    artifacts.py         # Artifact model: load/save, type/status enums, body+meta
    sidecar.py           # Sidecar + Issue models: read/write .reviews/<id>.md
    config.py            # SpecledgerConfig: load .specledger/config.yaml + defaults
    ledger.py            # record(), status(), supersede(), index() over a docs root
    critique.py          # Critic protocol, AnthropicCritic, RUBRIC, critique()
    review.py            # approve(): disposition validation + edit-proof + atomic stamp
    gate.py              # active marker, begin/end_implementation, check_gate()
    publish.py           # Khala publish (optional, no-op without config)
    server.py            # FastMCP wiring: exposes all tools
  hooks/
    pretooluse_gate.py   # PreToolUse entrypoint: stdin JSON -> allow/deny via gate
  tests/
    test_ids.py  test_hashing.py  test_frontmatter.py  test_artifacts.py
    test_sidecar.py  test_config.py  test_ledger.py  test_critique.py
    test_review.py  test_gate.py  test_hook.py  test_publish.py
    test_integration.py
    conftest.py          # fixtures: tmp docs root, sample artifacts, FakeCritic
```

**Responsibility split rationale:** primitives (`ids`, `hashing`) are dependency-free and reused everywhere. The data layer (`frontmatter`, `artifacts`, `sidecar`) owns persistence and never makes decisions. `ledger`/`review`/`gate` hold the state machine and policy. `critique`/`publish` wrap external services behind protocols so tests never hit the network. `server.py` and the hook are thin adapters with no business logic.

---

## Chunk 1: Scaffold + primitives (ids, hashing)

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/specledger/__init__.py` (empty)
- Create: `src/specledger/errors.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "specledger"
version = "0.1.0"
description = "ADR/SDD recording & accountable-review governance MCP"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.2.0",
    "anthropic>=0.40.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.6"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/specledger"]

[tool.pytest.ini_options]
pythonpath = ["src", "tests"]   # "tests" lets shared doubles live in tests/helpers.py
testpaths = ["tests"]

[tool.ruff]
line-length = 100
src = ["src", "tests"]
```

- [ ] **Step 2: Create `errors.py`**

```python
class SpecledgerError(Exception):
    """Base for all specledger errors."""


class IdCollisionError(SpecledgerError):
    """Raised when an id would be reused."""


class ImmutableArtifactError(SpecledgerError):
    """Raised when mutating an accepted ADR."""


class ArtifactNotFoundError(SpecledgerError):
    """Raised when an id does not resolve to a file."""


class ReviewError(SpecledgerError):
    """Raised when approve() validation fails."""


class CritiqueError(SpecledgerError):
    """Raised when critique cannot run (fail-closed)."""


class GateDeniedError(SpecledgerError):
    """Raised by the hook path when an edit is blocked."""
```

- [ ] **Step 3: Create empty `__init__.py` and minimal `conftest.py`**

```python
# tests/conftest.py
import pytest


@pytest.fixture
def docs_root(tmp_path):
    """A temporary docs root with specs/ and adr/ subdirs."""
    (tmp_path / "specs").mkdir()
    (tmp_path / "adr").mkdir()
    (tmp_path / ".reviews").mkdir()
    return tmp_path
```

- [ ] **Step 4: Verify install + empty test run**

Run: `pip install -e ".[dev]"` then `pytest -q`
Expected: "no tests ran" (exit 0, collection succeeds).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/specledger/__init__.py src/specledger/errors.py tests/conftest.py
git commit -m "chore: scaffold specledger package"
```

### Task 2: `ids.py` — id generation

**Files:**
- Create: `src/specledger/ids.py`
- Test: `tests/test_ids.py`

Spec ref: §5 "id 생성 규칙". ADR = `ADR-NNNN` zero-pad monotonic; Spec = `SPEC-<slug>` from title (lowercase → spaces to `-` → strip to `[a-z0-9가-힣-]` → collapse `-` → trim → cap 56 chars) with `-2/-3` collision suffix.

- [ ] **Step 1: Write failing tests for `slugify`**

```python
# tests/test_ids.py
from specledger.ids import slugify, make_spec_id, next_adr_id


def test_slugify_lowercases_and_hyphenates():
    assert slugify("Virtual DJ Playlist") == "virtual-dj-playlist"


def test_slugify_strips_punctuation_and_collapses_hyphens():
    assert slugify("Auth!! (v2) -- final") == "auth-v2-final"


def test_slugify_keeps_korean():
    assert slugify("리뷰 게이트 설계") == "리뷰-게이트-설계"


def test_slugify_caps_at_56_chars():
    assert len(slugify("x" * 100)) == 56
```

- [ ] **Step 2: Run → FAIL** (`ImportError: cannot import name 'slugify'`)

Run: `pytest tests/test_ids.py -q`

- [ ] **Step 3: Implement `slugify`**

```python
# src/specledger/ids.py
import re
from pathlib import Path

_SLUG_STRIP = re.compile(r"[^a-z0-9가-힣-]")
_SLUG_COLLAPSE = re.compile(r"-+")
_SLUG_CAP = 56  # leaves room for "-NN" collision suffix within a 60-char budget


def slugify(title: str) -> str:
    s = title.lower()
    s = s.replace(" ", "-")
    s = _SLUG_STRIP.sub("", s)
    s = _SLUG_COLLAPSE.sub("-", s).strip("-")
    return s[:_SLUG_CAP].strip("-")
```

- [ ] **Step 4: Run → PASS**

Run: `pytest tests/test_ids.py -q`

- [ ] **Step 5: Write failing tests for `make_spec_id` collision + `next_adr_id`**

```python
def test_make_spec_id_basic(tmp_path):
    assert make_spec_id(tmp_path, "Virtual DJ Playlist") == "SPEC-virtual-dj-playlist"


def test_make_spec_id_collision_suffix(tmp_path):
    (tmp_path / "SPEC-auth.md").write_text("x", encoding="utf-8")
    assert make_spec_id(tmp_path, "auth") == "SPEC-auth-2"
    (tmp_path / "SPEC-auth-2.md").write_text("x", encoding="utf-8")
    assert make_spec_id(tmp_path, "auth") == "SPEC-auth-3"


def test_make_spec_id_explicit_slug(tmp_path):
    assert make_spec_id(tmp_path, "ignored title", slug="custom") == "SPEC-custom"


def test_next_adr_id_first(tmp_path):
    assert next_adr_id(tmp_path) == "ADR-0001"


def test_next_adr_id_increments(tmp_path):
    (tmp_path / "ADR-0001-foo.md").write_text("x", encoding="utf-8")
    (tmp_path / "ADR-0007-bar.md").write_text("x", encoding="utf-8")
    assert next_adr_id(tmp_path) == "ADR-0008"
```

- [ ] **Step 6: Run → FAIL**, then implement

```python
def make_spec_id(specs_dir: Path, title: str, slug: str | None = None) -> str:
    base = slug if slug else slugify(title)
    candidate = f"SPEC-{base}"
    n = 2
    while (specs_dir / f"{candidate}.md").exists():
        candidate = f"SPEC-{base}-{n}"
        n += 1
    return candidate


_ADR_NUM = re.compile(r"^ADR-(\d{4})")


def next_adr_id(adr_dir: Path) -> str:
    highest = 0
    for p in adr_dir.glob("ADR-*.md"):
        m = _ADR_NUM.match(p.name)
        if m:
            highest = max(highest, int(m.group(1)))
    return f"ADR-{highest + 1:04d}"
```

- [ ] **Step 7: Run → PASS** (`pytest tests/test_ids.py -q`), then `ruff check .`

- [ ] **Step 8: Commit**

```bash
git add src/specledger/ids.py tests/test_ids.py
git commit -m "feat: id generation (ADR monotonic, SPEC slug + collision)"
```

### Task 3: `hashing.py` — content hash

**Files:**
- Create: `src/specledger/hashing.py`
- Test: `tests/test_hashing.py`

Spec ref: §4 "content_hash 정의" — body only; normalize to LF, strip per-line trailing whitespace, strip leading/trailing blank lines, then sha256.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_hashing.py
from specledger.hashing import content_hash


def test_hash_is_sha256_prefixed():
    h = content_hash("hello")
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64


def test_hash_ignores_line_ending_style():
    assert content_hash("a\r\nb") == content_hash("a\nb")


def test_hash_ignores_trailing_whitespace_per_line():
    assert content_hash("a   \nb\t\n") == content_hash("a\nb\n")


def test_hash_ignores_surrounding_blank_lines():
    assert content_hash("\n\nbody\n\n") == content_hash("body")


def test_hash_differs_on_real_change():
    assert content_hash("decision A") != content_hash("decision B")
```

- [ ] **Step 2: Run → FAIL**, then implement

```python
# src/specledger/hashing.py
import hashlib


def _normalize(body: str) -> str:
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.split("\n")]
    return "\n".join(lines).strip("\n")


def content_hash(body: str) -> str:
    digest = hashlib.sha256(_normalize(body).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
```

- [ ] **Step 3: Run → PASS** (`pytest tests/test_hashing.py -q`), `ruff check .`

- [ ] **Step 4: Commit**

```bash
git add src/specledger/hashing.py tests/test_hashing.py
git commit -m "feat: deterministic body-only content_hash"
```

---

## Chunk 2: Data layer (frontmatter, artifacts, sidecar)

### Task 4: `frontmatter.py` — split/render

**Files:**
- Create: `src/specledger/frontmatter.py`
- Test: `tests/test_frontmatter.py`

Contract: `split(text) -> (meta: dict, body: str)`; `render(meta, body) -> str`. Body is everything after the closing `---`. `render` round-trips so that `split(render(m, b)) == (m, b_normalized)`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_frontmatter.py
from specledger.frontmatter import split, render


def test_split_extracts_meta_and_body():
    text = "---\nid: ADR-0001\nstatus: proposed\n---\n# Body\ntext\n"
    meta, body = split(text)
    assert meta["id"] == "ADR-0001"
    assert meta["status"] == "proposed"
    assert body == "# Body\ntext\n"


def test_split_no_frontmatter_returns_empty_meta():
    meta, body = split("no frontmatter here")
    assert meta == {}
    assert body == "no frontmatter here"


def test_render_roundtrips():
    meta = {"id": "SPEC-x", "status": "draft"}
    body = "# Title\n\ncontent\n"
    meta2, body2 = split(render(meta, body))
    assert meta2 == meta
    assert body2.strip() == body.strip()


def test_render_preserves_key_order():
    meta = {"id": "ADR-0001", "title": "t", "status": "accepted"}
    out = render(meta, "b")
    assert out.index("id:") < out.index("title:") < out.index("status:")
```

- [ ] **Step 2: Run → FAIL**, then implement

```python
# src/specledger/frontmatter.py
import yaml

_DELIM = "---"


def split(text: str) -> tuple[dict, str]:
    if not text.startswith(_DELIM):
        return {}, text
    parts = text.split("\n")
    # find closing delimiter after line 0
    for i in range(1, len(parts)):
        if parts[i].strip() == _DELIM:
            raw = "\n".join(parts[1:i])
            body = "\n".join(parts[i + 1:])
            meta = yaml.safe_load(raw) or {}
            return meta, body
    return {}, text


def render(meta: dict, body: str) -> str:
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"{_DELIM}\n{front}\n{_DELIM}\n{body if body.endswith(chr(10)) else body + chr(10)}"
```

- [ ] **Step 3: Run → PASS**, `ruff check .`

- [ ] **Step 4: Commit**

```bash
git add src/specledger/frontmatter.py tests/test_frontmatter.py
git commit -m "feat: frontmatter split/render with key-order preservation"
```

### Task 5: `artifacts.py` — Artifact model

**Files:**
- Create: `src/specledger/artifacts.py`
- Test: `tests/test_artifacts.py`

Contract: `Artifact` wraps a file. `Artifact.load(path)` reads meta+body. `.save()` writes back via frontmatter.render. `.recompute_hash()` returns content_hash(body). Enums for type (`adr`/`spec`) and status. Pure model — no policy decisions about transitions (those live in ledger/review).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_artifacts.py
from specledger.artifacts import Artifact, ArtifactType, Status


def test_load_reads_meta_and_body(docs_root):
    p = docs_root / "specs" / "SPEC-x.md"
    p.write_text("---\nid: SPEC-x\ntype: spec\nstatus: draft\n---\nbody\n", encoding="utf-8")
    a = Artifact.load(p)
    assert a.id == "SPEC-x"
    assert a.type == ArtifactType.SPEC
    assert a.status == Status.DRAFT
    assert a.body.strip() == "body"


def test_save_roundtrips(docs_root):
    p = docs_root / "specs" / "SPEC-y.md"
    p.write_text("---\nid: SPEC-y\ntype: spec\nstatus: draft\n---\nbody\n", encoding="utf-8")
    a = Artifact.load(p)
    a.meta["status"] = "in_review"
    a.save()
    assert Artifact.load(p).status == Status.IN_REVIEW


def test_recompute_hash_matches_hashing_module(docs_root):
    from specledger.hashing import content_hash
    p = docs_root / "specs" / "SPEC-z.md"
    p.write_text("---\nid: SPEC-z\ntype: spec\nstatus: draft\n---\nthe body\n", encoding="utf-8")
    a = Artifact.load(p)
    assert a.recompute_hash() == content_hash("the body\n")
```

- [ ] **Step 2: Run → FAIL**, then implement

```python
# src/specledger/artifacts.py
from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path

from . import frontmatter
from .hashing import content_hash


class ArtifactType(enum.StrEnum):
    ADR = "adr"
    SPEC = "spec"


class Status(enum.StrEnum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"
    DEPRECATED = "deprecated"
    STALE = "stale"


@dataclass
class Artifact:
    path: Path
    meta: dict
    body: str

    @classmethod
    def load(cls, path: Path) -> "Artifact":
        meta, body = frontmatter.split(Path(path).read_text(encoding="utf-8"))
        return cls(path=Path(path), meta=meta, body=body)

    @property
    def id(self) -> str:
        return self.meta["id"]

    @property
    def type(self) -> ArtifactType:
        return ArtifactType(self.meta["type"])

    @property
    def status(self) -> Status:
        return Status(self.meta["status"])

    def recompute_hash(self) -> str:
        return content_hash(self.body)

    def save(self) -> None:
        self.path.write_text(frontmatter.render(self.meta, self.body), encoding="utf-8")
```

- [ ] **Step 3: Run → PASS**, `ruff check .`

- [ ] **Step 4: Commit**

```bash
git add src/specledger/artifacts.py tests/test_artifacts.py
git commit -m "feat: Artifact model (load/save/recompute_hash)"
```

### Task 6: `sidecar.py` — review sidecar

**Files:**
- Create: `src/specledger/sidecar.py`
- Test: `tests/test_sidecar.py`

Spec ref: §4 sidecar schema. `Issue(issue_id, category, severity, description, status, disposition_reason)`. `Sidecar(target, critiqued_hash, critiqued_at, issues, approved_by, approved_at)`. `read(path)` / `write(path)`. The sidecar file is YAML-frontmatter + a human-readable body.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_sidecar.py
from specledger.sidecar import Sidecar, Issue


def test_write_then_read_roundtrips(docs_root):
    p = docs_root / ".reviews" / "SPEC-x.md"
    sc = Sidecar(
        target="SPEC-x",
        critiqued_hash="sha256:abc",
        critiqued_at="2026-06-06T13:00Z",
        issues=[Issue("I-001", "missing-invariant", "high", "no invariant stated", "open", None)],
        narrative="prose here",
    )
    sc.write(p)
    back = Sidecar.read(p)
    assert back.target == "SPEC-x"
    assert back.critiqued_hash == "sha256:abc"
    assert back.issues[0].issue_id == "I-001"
    assert back.issues[0].status == "open"
    assert back.narrative.strip() == "prose here"


def test_open_issue_count(docs_root):
    sc = Sidecar(
        target="SPEC-x", critiqued_hash="sha256:abc", critiqued_at="t",
        issues=[
            Issue("I-001", "x", "high", "d", "open", None),
            Issue("I-002", "y", "low", "d", "accepted", None),
        ],
        narrative="",
    )
    assert sc.open_issue_count() == 1
```

- [ ] **Step 2: Run → FAIL**, then implement

```python
# src/specledger/sidecar.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import frontmatter


@dataclass
class Issue:
    issue_id: str
    category: str
    severity: str
    description: str
    status: str  # open | accepted | rejected | deferred
    disposition_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "issue_id": self.issue_id,
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "status": self.status,
            "disposition_reason": self.disposition_reason,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Issue":
        return cls(
            issue_id=d["issue_id"], category=d["category"], severity=d["severity"],
            description=d["description"], status=d["status"],
            disposition_reason=d.get("disposition_reason"),
        )


@dataclass
class Sidecar:
    target: str
    critiqued_hash: str
    critiqued_at: str
    issues: list[Issue] = field(default_factory=list)
    approved_by: str | None = None
    approved_at: str | None = None
    narrative: str = ""

    def open_issue_count(self) -> int:
        return sum(1 for i in self.issues if i.status == "open")

    def write(self, path: Path) -> None:
        meta = {
            "target": self.target,
            "critiqued_hash": self.critiqued_hash,
            "critiqued_at": self.critiqued_at,
            "issues": [i.to_dict() for i in self.issues],
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
        }
        Path(path).write_text(frontmatter.render(meta, self.narrative), encoding="utf-8")

    @classmethod
    def read(cls, path: Path) -> "Sidecar":
        meta, body = frontmatter.split(Path(path).read_text(encoding="utf-8"))
        return cls(
            target=meta["target"], critiqued_hash=meta["critiqued_hash"],
            critiqued_at=meta["critiqued_at"],
            issues=[Issue.from_dict(d) for d in (meta.get("issues") or [])],
            approved_by=meta.get("approved_by"), approved_at=meta.get("approved_at"),
            narrative=body,
        )
```

- [ ] **Step 3: Run → PASS**, `ruff check .`

- [ ] **Step 4: Commit**

```bash
git add src/specledger/sidecar.py tests/test_sidecar.py
git commit -m "feat: review sidecar model (issues + dispositions)"
```

---

## Chunk 3: Ledger operations (record, status, supersede, index)

The `Ledger` class binds a docs root (with `specs/`, `adr/`, `.reviews/`) and provides the recording/state operations. Time is injected (`now: Callable[[], str]`) so tests are deterministic — never call the wall clock directly.

### Task 7: `Ledger.record`

**Files:**
- Create: `src/specledger/ledger.py`
- Test: `tests/test_ledger.py`

Spec ref: §5 `record`. `record(type, title, slug=None) -> id`. ADR → status=proposed in `adr/`; spec → status=draft in `specs/`. Writes frontmatter with id, type, title, status, date.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ledger.py
from specledger.ledger import Ledger
from specledger.artifacts import Artifact, Status


def make_ledger(docs_root):
    return Ledger(docs_root, now=lambda: "2026-06-06T00:00Z")


def test_record_spec_creates_draft(docs_root):
    led = make_ledger(docs_root)
    sid = led.record("spec", "Virtual DJ Playlist")
    assert sid == "SPEC-virtual-dj-playlist"
    a = Artifact.load(docs_root / "specs" / f"{sid}.md")
    assert a.status == Status.DRAFT
    assert a.meta["title"] == "Virtual DJ Playlist"


def test_record_adr_creates_proposed_monotonic(docs_root):
    led = make_ledger(docs_root)
    assert led.record("adr", "First") == "ADR-0001"
    assert led.record("adr", "Second") == "ADR-0002"
    a = Artifact.load(docs_root / "adr" / "ADR-0001-first.md")
    assert a.status == Status.PROPOSED
```

- [ ] **Step 2: Run → FAIL**, then implement (start the module)

```python
# src/specledger/ledger.py
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import ids
from .artifacts import Artifact, ArtifactType, Status
from .frontmatter import render


class Ledger:
    def __init__(self, root: Path, now: Callable[[], str]):
        self.root = Path(root)
        self.specs = self.root / "specs"
        self.adr = self.root / "adr"
        self.reviews = self.root / ".reviews"
        for d in (self.specs, self.adr, self.reviews):
            d.mkdir(parents=True, exist_ok=True)
        self._now = now

    def record(self, type: str, title: str, slug: str | None = None) -> str:
        atype = ArtifactType(type)
        if atype is ArtifactType.ADR:
            aid = ids.next_adr_id(self.adr)
            status = Status.PROPOSED
            path = self.adr / f"{aid}-{ids.slugify(title)}.md"
        else:
            aid = ids.make_spec_id(self.specs, title, slug)
            status = Status.DRAFT
            path = self.specs / f"{aid}.md"
        meta = {
            "id": aid, "type": str(atype), "title": title,
            "status": str(status), "date": self._now(),
        }
        path.write_text(render(meta, f"# {title}\n\n"), encoding="utf-8")
        return aid

    def _resolve(self, artifact_id: str) -> Path:
        for d in (self.specs, self.adr):
            for p in d.glob(f"{artifact_id}*.md"):
                if Artifact.load(p).id == artifact_id:
                    return p
        from .errors import ArtifactNotFoundError
        raise ArtifactNotFoundError(artifact_id)
```

- [ ] **Step 3: Run → PASS**, `ruff check .`

- [ ] **Step 4: Commit**

```bash
git add src/specledger/ledger.py tests/test_ledger.py
git commit -m "feat: Ledger.record for ADR and spec"
```

### Task 8: `Ledger.status` with report-and-repair

**Files:**
- Modify: `src/specledger/ledger.py`
- Test: `tests/test_ledger.py`

Spec ref: §5 status row, §9. `status(id=None)` returns a report. For each artifact: if `status == approved/accepted` and `recompute_hash() != meta['content_hash']`, **write back** `status=in_review` (specs) and include `needs_review=True` in the report. ADRs that are accepted with a hash mismatch are NOT auto-reset (immutable) but are flagged `tampered=True`.

- [ ] **Step 1: Write failing tests**

```python
def test_status_reports_all(docs_root):
    led = make_ledger(docs_root)
    led.record("spec", "A")
    led.record("adr", "B")
    rep = led.status()
    assert {r["id"] for r in rep} == {"SPEC-a", "ADR-0001"}


def test_status_repairs_tampered_approved_spec(docs_root):
    led = make_ledger(docs_root)
    sid = led.record("spec", "A")
    a = Artifact.load(docs_root / "specs" / f"{sid}.md")
    a.meta["status"] = "approved"
    a.meta["content_hash"] = a.recompute_hash()
    a.save()
    # tamper the body out-of-band
    a2 = Artifact.load(a.path)
    a2.body += "\nsneaky edit\n"
    a2.save()
    rep = {r["id"]: r for r in led.status()}
    assert rep[sid]["status"] == "in_review"           # written back
    assert Artifact.load(a.path).status == Status.IN_REVIEW
    assert rep[sid]["needs_review"] is True


def test_status_flags_tampered_accepted_adr_without_reset(docs_root):
    led = make_ledger(docs_root)
    aid = led.record("adr", "Decide")
    p = led._resolve(aid)
    a = Artifact.load(p)
    a.meta["status"] = "accepted"
    a.meta["content_hash"] = a.recompute_hash()
    a.save()
    a2 = Artifact.load(p); a2.body += "\ntamper\n"; a2.save()
    rep = {r["id"]: r for r in led.status()}
    assert rep[aid]["tampered"] is True
    assert Artifact.load(p).status == Status.ACCEPTED   # NOT reset
```

- [ ] **Step 2: Run → FAIL**, then implement (append to `Ledger`)

```python
    def _all_paths(self):
        yield from self.specs.glob("*.md")
        yield from self.adr.glob("*.md")

    def status(self, artifact_id: str | None = None) -> list[dict]:
        paths = [self._resolve(artifact_id)] if artifact_id else list(self._all_paths())
        report = []
        for p in paths:
            a = Artifact.load(p)
            entry = {"id": a.id, "type": str(a.type), "status": str(a.status),
                     "needs_review": False, "tampered": False}
            stored = a.meta.get("content_hash")
            if a.status in (Status.APPROVED, Status.ACCEPTED) and stored:
                if a.recompute_hash() != stored:
                    if a.type is ArtifactType.SPEC:
                        a.meta["status"] = str(Status.IN_REVIEW)
                        a.save()
                        entry["status"] = str(Status.IN_REVIEW)
                        entry["needs_review"] = True
                    else:  # accepted ADR is immutable: flag, do not reset
                        entry["tampered"] = True
            report.append(entry)
        return report
```

- [ ] **Step 3: Run → PASS**, `ruff check .`

- [ ] **Step 4: Commit**

```bash
git add src/specledger/ledger.py tests/test_ledger.py
git commit -m "feat: Ledger.status with report-and-repair writeback"
```

### Task 9: `Ledger.supersede`

**Files:**
- Modify: `src/specledger/ledger.py`
- Test: `tests/test_ledger.py`

Spec ref: §5 supersede, §4 ADR rule. `supersede(old_id, new_id)`: both must be ADRs; sets old `status=superseded` + `superseded_by=new_id`, sets new `supersedes=old_id`. Raises if either is not an ADR.

- [ ] **Step 1: Write failing tests**

```python
import pytest
from specledger.errors import ImmutableArtifactError


def test_supersede_links_both(docs_root):
    led = make_ledger(docs_root)
    old = led.record("adr", "Old")
    new = led.record("adr", "New")
    led.supersede(old, new)
    a_old = Artifact.load(led._resolve(old))
    a_new = Artifact.load(led._resolve(new))
    assert a_old.status == Status.SUPERSEDED
    assert a_old.meta["superseded_by"] == new
    assert a_new.meta["supersedes"] == old


def test_supersede_rejects_non_adr(docs_root):
    led = make_ledger(docs_root)
    sid = led.record("spec", "S")
    aid = led.record("adr", "A")
    with pytest.raises(ImmutableArtifactError):
        led.supersede(sid, aid)
```

- [ ] **Step 2: Run → FAIL**, then implement

```python
    def supersede(self, old_id: str, new_id: str) -> None:
        a_old = Artifact.load(self._resolve(old_id))
        a_new = Artifact.load(self._resolve(new_id))
        if a_old.type is not ArtifactType.ADR or a_new.type is not ArtifactType.ADR:
            from .errors import ImmutableArtifactError
            raise ImmutableArtifactError("supersede applies to ADRs only")
        a_old.meta["status"] = str(Status.SUPERSEDED)
        a_old.meta["superseded_by"] = new_id
        a_old.save()
        a_new.meta["supersedes"] = old_id
        a_new.save()
```

- [ ] **Step 3: Run → PASS**, `ruff check .`

- [ ] **Step 4: Commit**

```bash
git add src/specledger/ledger.py tests/test_ledger.py
git commit -m "feat: Ledger.supersede (ADR-only transition)"
```

### Task 10: `Ledger.index`

**Files:**
- Modify: `src/specledger/ledger.py`
- Test: `tests/test_ledger.py`

Spec ref: §8. `index() -> Path` writes `docs/INDEX.md` grouping artifacts by 🔴 unreviewed (draft/proposed) / 🟡 in_review / 🟢 approved/accepted, each row: id, title, approved_by, date, linked_adrs. Runs `status()` first so the dashboard reflects repaired states.

- [ ] **Step 1: Write failing tests**

```python
def test_index_groups_by_status(docs_root):
    led = make_ledger(docs_root)
    led.record("spec", "Draft One")
    sid = led.record("spec", "Approved One")
    a = Artifact.load(docs_root / "specs" / f"{sid}.md")
    a.meta["status"] = "approved"; a.meta["content_hash"] = a.recompute_hash(); a.save()
    out = led.index()
    text = out.read_text(encoding="utf-8")
    assert out.name == "INDEX.md"
    assert "🟢" in text and "🔴" in text
    assert "SPEC-approved-one" in text
    assert text.index("🔴") < text.index("🟢")  # unreviewed section appears first
```

- [ ] **Step 2: Run → FAIL**, then implement

```python
    _GROUPS = [
        ("🔴 미검토", {Status.DRAFT, Status.PROPOSED}),
        ("🟡 검토중", {Status.IN_REVIEW}),
        ("🟢 승인", {Status.APPROVED, Status.ACCEPTED}),
    ]

    def index(self) -> Path:
        self.status()  # repair first
        arts = [Artifact.load(p) for p in self._all_paths()]
        lines = ["# Specledger Index", ""]
        for label, statuses in self._GROUPS:
            members = [a for a in arts if a.status in statuses]
            lines.append(f"## {label} ({len(members)})")
            lines.append("")
            if members:
                lines.append("| id | title | approved_by | date | linked_adrs |")
                lines.append("|---|---|---|---|---|")
                for a in members:
                    linked = ", ".join(a.meta.get("linked_adrs") or [])
                    lines.append(
                        f"| {a.id} | {a.meta.get('title','')} | {a.meta.get('approved_by','')} "
                        f"| {a.meta.get('date','')} | {linked} |"
                    )
            lines.append("")
        out = self.root / "INDEX.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        return out
```

- [ ] **Step 3: Run → PASS**, `ruff check .`

- [ ] **Step 4: Commit**

```bash
git add src/specledger/ledger.py tests/test_ledger.py
git commit -m "feat: Ledger.index dashboard generation"
```

---

## Chunk 4: Review gate (critique + approve)

### Task 11: `critique.py`

**Files:**
- Create: `src/specledger/critique.py`
- Create: `tests/helpers.py` (shared test doubles: `FakeCritic`)
- Test: `tests/test_critique.py`

Spec ref: §5 critique contract, §4 sidecar. A `Critic` protocol decouples the LLM. `AnthropicCritic` implements it via the `anthropic` SDK (returns structured issues from a tool-use / JSON response). `critique(ledger, artifact_id, critic, now)`:
1. Loads artifact; gathers linked ADR bodies.
2. Calls `critic.find_issues(body, linked_adr_bodies, RUBRIC)` → list of `(category, severity, description)`.
3. Assigns `I-NNN` ids, writes the sidecar with `critiqued_hash = artifact.recompute_hash()`.
4. Sets artifact `status=in_review`, saves.
Fail-closed: if `critic` raises, propagate `CritiqueError` and do not change status.

- [ ] **Step 1: Create the shared `FakeCritic` double**

```python
# tests/helpers.py — shared test doubles (importable because pythonpath includes "tests")
class FakeCritic:
    def __init__(self, issues=None, boom=False):
        self.issues = issues or [("missing-invariant", "high", "no invariant")]
        self.boom = boom
        self.seen = None

    def find_issues(self, body, linked_adrs, rubric):
        if self.boom:
            raise RuntimeError("api down")
        self.seen = (body, linked_adrs, rubric)
        return self.issues
```

- [ ] **Step 2: Write failing tests (import FakeCritic from helpers)**

```python
# tests/test_critique.py
import pytest
from specledger.ledger import Ledger
from specledger.artifacts import Artifact, Status
from specledger.critique import critique, RUBRIC
from specledger.errors import CritiqueError
from helpers import FakeCritic


def led(docs_root):
    return Ledger(docs_root, now=lambda: "2026-06-06T13:00Z")


def test_critique_writes_sidecar_and_sets_in_review(docs_root):
    l = led(docs_root)
    sid = l.record("spec", "A")
    from specledger.sidecar import Sidecar
    issues = critique(l, sid, FakeCritic(), now=lambda: "2026-06-06T13:00Z")
    assert issues[0].issue_id == "I-001"
    sc = Sidecar.read(docs_root / ".reviews" / f"{sid}.md")
    assert sc.critiqued_hash == Artifact.load(l._resolve(sid)).recompute_hash()
    assert Artifact.load(l._resolve(sid)).status == Status.IN_REVIEW


def test_critique_passes_linked_adr_bodies(docs_root):
    l = led(docs_root)
    aid = l.record("adr", "Decision")
    sid = l.record("spec", "A")
    a = Artifact.load(l._resolve(sid)); a.meta["linked_adrs"] = [aid]; a.save()
    fc = FakeCritic()
    critique(l, sid, fc, now=lambda: "t")
    assert any("Decision" in body for body in fc.seen[1])  # linked ADR body present


def test_critique_fail_closed(docs_root):
    l = led(docs_root)
    sid = l.record("spec", "A")
    with pytest.raises(CritiqueError):
        critique(l, sid, FakeCritic(boom=True), now=lambda: "t")
    assert Artifact.load(l._resolve(sid)).status == Status.DRAFT  # unchanged
```

- [ ] **Step 3: Run → FAIL**, then implement

```python
# src/specledger/critique.py
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .artifacts import Artifact, Status
from .errors import CritiqueError
from .sidecar import Issue, Sidecar

RUBRIC = [
    "risky-assumption", "missing-invariant", "unverifiable-claim",
    "scope-creep", "adr-contradiction", "undefined", "untestable-requirement",
]


class Critic(Protocol):
    def find_issues(
        self, body: str, linked_adr_bodies: list[str], rubric: list[str]
    ) -> list[tuple[str, str, str]]:
        """Return list of (category, severity, description)."""


def critique(ledger, artifact_id: str, critic: Critic, now: Callable[[], str]) -> list[Issue]:
    art = Artifact.load(ledger._resolve(artifact_id))
    linked = []
    for adr_id in (art.meta.get("linked_adrs") or []):
        try:
            linked.append(Artifact.load(ledger._resolve(adr_id)).body)
        except Exception:  # noqa: BLE001 - missing link is non-fatal context
            continue
    try:
        raw = critic.find_issues(art.body, linked, RUBRIC)
    except Exception as e:  # noqa: BLE001 - fail closed regardless of cause
        raise CritiqueError(str(e)) from e
    issues = [
        Issue(f"I-{i + 1:03d}", cat, sev, desc, "open", None)
        for i, (cat, sev, desc) in enumerate(raw)
    ]
    sc = Sidecar(
        target=art.id, critiqued_hash=art.recompute_hash(), critiqued_at=now(),
        issues=issues, narrative="",
    )
    sc.write(ledger.reviews / f"{art.id}.md")
    art.meta["status"] = str(Status.IN_REVIEW)
    art.save()
    return issues
```

- [ ] **Step 4: Implement `AnthropicCritic` + test it with a stubbed client**

```python
# append to critique.py
import json
import os

_PROMPT = (
    "You are an independent spec reviewer. Find concrete issues in the DESIGN DOC below, "
    "each tagged with one rubric category: {rubric}. Return ONLY a JSON array of objects "
    '{{"category","severity","description"}} where severity is high|medium|low. '
    "Check especially for contradictions with the LINKED ADRS.\n\n"
    "=== DESIGN DOC ===\n{body}\n\n=== LINKED ADRS ===\n{adrs}\n"
)


class AnthropicCritic:
    def __init__(self, client=None, model: str = "claude-opus-4-8", max_tokens: int = 2000):
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def find_issues(self, body, linked_adr_bodies, rubric):
        prompt = _PROMPT.format(
            rubric=", ".join(rubric), body=body,
            adrs="\n---\n".join(linked_adr_bodies) or "(none)",
        )
        resp = self._client.messages.create(
            model=self._model, max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        data = json.loads(text)
        return [(d["category"], d["severity"], d["description"]) for d in data]
```

```python
# tests/test_critique.py — stubbed client test
class _Block:
    type = "text"
    def __init__(self, text): self.text = text

class _Resp:
    def __init__(self, text): self.content = [_Block(text)]

class _Client:
    def __init__(self, text): self._text = text; self.messages = self
    def create(self, **kw): return _Resp(self._text)


def test_anthropic_critic_parses_json():
    from specledger.critique import AnthropicCritic
    client = _Client('[{"category":"scope-creep","severity":"low","description":"x"}]')
    crit = AnthropicCritic(client=client)
    assert crit.find_issues("body", [], RUBRIC) == [("scope-creep", "low", "x")]
```

- [ ] **Step 5: Run → PASS** (`pytest tests/test_critique.py -q`), `ruff check .`

- [ ] **Step 6: Commit**

```bash
git add src/specledger/critique.py tests/test_critique.py tests/helpers.py
git commit -m "feat: critique (Critic protocol, fail-closed, AnthropicCritic)"
```

### Task 12: `review.py` — approve

**Files:**
- Create: `src/specledger/review.py`
- Test: `tests/test_review.py`

Spec ref: §6 approve validation. `approve(ledger, artifact_id, dispositions, approver, now)`:
- Validation (raise `ReviewError` on any failure):
  - sidecar must exist (else fail-closed: no critique → no approval);
  - every open issue has a disposition (matched by `issue_id`);
  - `rejected`/`deferred` require non-empty `reason`;
  - if any disposition is `accepted`, current `artifact.recompute_hash() != sidecar.critiqued_hash` (edit-proof).
- On success — validate everything first, then persist **sidecar first, artifact last** (fail-safe ordering: if the process dies between the two writes, the artifact stays un-stamped/`in_review`, so the gate keeps denying — never a false "approved"). True cross-file atomicity is out of scope for the solo MVP; this ordering makes the failure mode safe rather than dangerous.
  - update each sidecar issue's `status`/`disposition_reason`; set sidecar `approved_by`/`approved_at`;
  - set artifact `status=approved` (spec) or `accepted` (adr), `approved_by`, `reviewed_at`, `content_hash=recompute_hash()`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_review.py
import pytest
from specledger.ledger import Ledger
from specledger.artifacts import Artifact, Status
from specledger.critique import critique
from specledger.review import approve
from specledger.errors import ReviewError
from helpers import FakeCritic


def setup(docs_root, body_issue=True):
    l = Ledger(docs_root, now=lambda: "t")
    sid = l.record("spec", "A")
    critique(l, sid, FakeCritic(), now=lambda: "t")
    return l, sid


def test_approve_requires_all_issues_dispositioned(docs_root):
    l, sid = setup(docs_root)
    with pytest.raises(ReviewError, match="undispositioned"):
        approve(l, sid, [], "eisen", now=lambda: "t2")


def test_reject_requires_reason(docs_root):
    l, sid = setup(docs_root)
    with pytest.raises(ReviewError, match="reason"):
        approve(l, sid, [{"issue_id": "I-001", "disposition": "rejected"}], "eisen", now=lambda: "t2")


def test_accepted_requires_body_edit(docs_root):
    l, sid = setup(docs_root)
    # accepted but body unchanged since critique -> reject
    with pytest.raises(ReviewError, match="미수정"):
        approve(l, sid, [{"issue_id": "I-001", "disposition": "accepted"}], "eisen", now=lambda: "t2")


def test_accepted_with_edit_succeeds_and_stamps(docs_root):
    l, sid = setup(docs_root)
    a = Artifact.load(l._resolve(sid)); a.body += "\nfixed the invariant\n"; a.save()
    approve(l, sid, [{"issue_id": "I-001", "disposition": "accepted"}], "eisen", now=lambda: "t2")
    a2 = Artifact.load(l._resolve(sid))
    assert a2.status == Status.APPROVED
    assert a2.meta["approved_by"] == "eisen"
    assert a2.meta["content_hash"] == a2.recompute_hash()


def test_all_rejected_no_edit_required(docs_root):
    l, sid = setup(docs_root)
    approve(l, sid, [{"issue_id": "I-001", "disposition": "rejected", "reason": "wrong"}],
            "eisen", now=lambda: "t2")
    assert Artifact.load(l._resolve(sid)).status == Status.APPROVED


def test_approve_fail_closed_without_sidecar(docs_root):
    l = Ledger(docs_root, now=lambda: "t")
    sid = l.record("spec", "A")  # never critiqued
    with pytest.raises(ReviewError, match="critique"):
        approve(l, sid, [], "eisen", now=lambda: "t2")
```

- [ ] **Step 2: Run → FAIL**, then implement

```python
# src/specledger/review.py
from __future__ import annotations

from collections.abc import Callable

from .artifacts import Artifact, ArtifactType, Status
from .errors import ReviewError
from .sidecar import Sidecar

_VALID = {"accepted", "rejected", "deferred"}


def approve(ledger, artifact_id, dispositions, approver, now: Callable[[], str]) -> None:
    art = Artifact.load(ledger._resolve(artifact_id))
    sc_path = ledger.reviews / f"{art.id}.md"
    if not sc_path.exists():
        raise ReviewError(f"no critique sidecar for {art.id}; run critique first")
    sc = Sidecar.read(sc_path)

    by_id = {d["issue_id"]: d for d in dispositions}
    open_issues = [i for i in sc.issues if i.status == "open"]
    missing = [i.issue_id for i in open_issues if i.issue_id not in by_id]
    if missing:
        raise ReviewError(f"undispositioned issues: {missing}")

    has_accept = False
    for i in open_issues:
        d = by_id[i.issue_id]
        disp = d.get("disposition")
        if disp not in _VALID:
            raise ReviewError(f"invalid disposition for {i.issue_id}: {disp}")
        if disp in ("rejected", "deferred") and not (d.get("reason") or "").strip():
            raise ReviewError(f"{disp} requires a reason for {i.issue_id}")
        has_accept = has_accept or disp == "accepted"

    if has_accept and art.recompute_hash() == sc.critiqued_hash:
        raise ReviewError("accepted 했으나 문서 미수정 (본문 해시 불변)")

    # --- all validated: mutate in memory, then persist sidecar then artifact ---
    for i in sc.issues:
        if i.issue_id in by_id:
            i.status = by_id[i.issue_id]["disposition"]
            i.disposition_reason = by_id[i.issue_id].get("reason")
    sc.approved_by = approver
    sc.approved_at = now()

    final = Status.ACCEPTED if art.type is ArtifactType.ADR else Status.APPROVED
    art.meta["status"] = str(final)
    art.meta["approved_by"] = approver
    art.meta["reviewed_at"] = now()
    art.meta["content_hash"] = art.recompute_hash()

    sc.write(sc_path)
    art.save()
```

- [ ] **Step 3: Run → PASS**, `ruff check .`

- [ ] **Step 4: Commit**

```bash
git add src/specledger/review.py tests/test_review.py
git commit -m "feat: approve gate (disposition validation + edit-proof + atomic stamp)"
```

---

## Chunk 5: Enforcement (config, gate, hook)

### Task 13: `config.py`

**Files:**
- Create: `src/specledger/config.py`
- Test: `tests/test_config.py`

Spec ref: §7. Loads `<project>/.specledger/config.yaml`. Keys: `exempt_paths` (globs), `allow_globs` (default `["docs/**", "tests/**"]`), `khala` (optional dict). Missing file → defaults.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config.py
from specledger.config import SpecledgerConfig


def test_defaults_when_missing(tmp_path):
    cfg = SpecledgerConfig.load(tmp_path)
    assert cfg.allow_globs == ["docs/**", "tests/**"]
    assert cfg.exempt_paths == []
    assert cfg.khala is None


def test_loads_yaml(tmp_path):
    d = tmp_path / ".specledger"; d.mkdir()
    (d / "config.yaml").write_text(
        "exempt_paths: ['scripts/**']\nkhala: {url: 'http://x'}\n", encoding="utf-8")
    cfg = SpecledgerConfig.load(tmp_path)
    assert cfg.exempt_paths == ["scripts/**"]
    assert cfg.khala == {"url": "http://x"}
    assert cfg.allow_globs == ["docs/**", "tests/**"]  # default retained
```

- [ ] **Step 2: Run → FAIL**, then implement

```python
# src/specledger/config.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

_DEFAULT_ALLOW = ["docs/**", "tests/**"]


@dataclass
class SpecledgerConfig:
    exempt_paths: list[str] = field(default_factory=list)
    allow_globs: list[str] = field(default_factory=lambda: list(_DEFAULT_ALLOW))
    khala: dict | None = None

    @classmethod
    def load(cls, project_root: Path) -> "SpecledgerConfig":
        path = Path(project_root) / ".specledger" / "config.yaml"
        if not path.exists():
            return cls()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            exempt_paths=data.get("exempt_paths", []),
            allow_globs=data.get("allow_globs", list(_DEFAULT_ALLOW)),
            khala=data.get("khala"),
        )
```

- [ ] **Step 3: Run → PASS**, `ruff check .`

- [ ] **Step 4: Commit**

```bash
git add src/specledger/config.py tests/test_config.py
git commit -m "feat: SpecledgerConfig loader with defaults"
```

### Task 14: `gate.py` — active marker + begin/end

**Files:**
- Create: `src/specledger/gate.py`
- Test: `tests/test_gate.py`

Spec ref: §5 marker contract. Marker at `<project>/.specledger/active.json` `{spec_id, set_at, set_by}`. `begin_implementation(spec_id, set_by, now)` overwrites (single active). `end_implementation()` deletes. `active_spec()` returns id or None.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_gate.py
from specledger.gate import Gate


def test_begin_sets_single_active(tmp_path):
    g = Gate(tmp_path, now=lambda: "t")
    g.begin_implementation("SPEC-a", set_by="agent")
    assert g.active_spec() == "SPEC-a"
    g.begin_implementation("SPEC-b", set_by="user")  # overwrite
    assert g.active_spec() == "SPEC-b"


def test_end_clears(tmp_path):
    g = Gate(tmp_path, now=lambda: "t")
    g.begin_implementation("SPEC-a", set_by="agent")
    g.end_implementation()
    assert g.active_spec() is None
```

- [ ] **Step 2: Run → FAIL**, then implement (start module)

```python
# src/specledger/gate.py
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path


class Gate:
    def __init__(self, project_root: Path, now: Callable[[], str]):
        self.root = Path(project_root)
        self._dir = self.root / ".specledger"
        self._marker = self._dir / "active.json"
        self._now = now

    def begin_implementation(self, spec_id: str, set_by: str = "agent") -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._marker.write_text(
            json.dumps({"spec_id": spec_id, "set_at": self._now(), "set_by": set_by}),
            encoding="utf-8",
        )

    def end_implementation(self) -> None:
        self._marker.unlink(missing_ok=True)

    def active_spec(self) -> str | None:
        if not self._marker.exists():
            return None
        return json.loads(self._marker.read_text(encoding="utf-8"))["spec_id"]
```

- [ ] **Step 3: Run → PASS**, `ruff check .`

- [ ] **Step 4: Commit**

```bash
git add src/specledger/gate.py tests/test_gate.py
git commit -m "feat: Gate active-spec marker (begin/end/active)"
```

### Task 15: `Gate.check_gate` with precedence + writeback

**Files:**
- Modify: `src/specledger/gate.py`
- Test: `tests/test_gate.py`

Spec ref: §5 check_gate, §7 precedence. `check_gate(paths, ledger, config)` → `{allowed, spec_id, status, open_issue_count, reason}`. Precedence per path: ① matches `exempt_paths` → allowed (and append to `.specledger/exempt.log`); ② matches `allow_globs` → allowed; ③ else evaluate active spec: no marker → deny; spec not approved (after `ledger.status()` repair) → deny; approved → allow. Aggregate: allowed only if **all** paths allowed.

- [ ] **Step 1: Write failing tests**

```python
import json
from specledger.ledger import Ledger
from specledger.artifacts import Artifact, Status
from specledger.config import SpecledgerConfig


def _approved_spec(docs_root):
    led = Ledger(docs_root, now=lambda: "t")
    sid = led.record("spec", "A")
    a = Artifact.load(led._resolve(sid))
    a.meta["status"] = "approved"; a.meta["content_hash"] = a.recompute_hash(); a.save()
    return led, sid


def test_gate_denies_without_marker(tmp_path):
    led, _ = _approved_spec(tmp_path / "docs")
    g = Gate(tmp_path, now=lambda: "t")
    res = g.check_gate(["src/app.py"], led, SpecledgerConfig())
    assert res["allowed"] is False
    assert "활성 spec" in res["reason"]


def test_gate_allows_when_active_spec_approved(tmp_path):
    led, sid = _approved_spec(tmp_path / "docs")
    g = Gate(tmp_path, now=lambda: "t")
    g.begin_implementation(sid)
    res = g.check_gate(["src/app.py"], led, SpecledgerConfig())
    assert res["allowed"] is True
    assert res["spec_id"] == sid


def test_gate_denies_when_active_spec_unapproved(tmp_path):
    led = Ledger(tmp_path / "docs", now=lambda: "t")
    sid = led.record("spec", "A")  # draft
    g = Gate(tmp_path, now=lambda: "t")
    g.begin_implementation(sid)
    res = g.check_gate(["src/app.py"], led, SpecledgerConfig())
    assert res["allowed"] is False
    assert res["status"] == "draft"


def test_allow_globs_bypass_gate(tmp_path):
    led = Ledger(tmp_path / "docs", now=lambda: "t")
    g = Gate(tmp_path, now=lambda: "t")
    res = g.check_gate(["docs/readme.md", "tests/test_x.py"], led, SpecledgerConfig())
    assert res["allowed"] is True


def test_exempt_path_allows_and_logs(tmp_path):
    led = Ledger(tmp_path / "docs", now=lambda: "t")
    g = Gate(tmp_path, now=lambda: "t")
    cfg = SpecledgerConfig(exempt_paths=["scripts/**"])
    res = g.check_gate(["scripts/gen.py"], led, cfg)
    assert res["allowed"] is True
    log = (tmp_path / ".specledger" / "exempt.log").read_text(encoding="utf-8")
    assert "scripts/gen.py" in log
```

- [ ] **Step 2: Run → FAIL**, then implement (append to `Gate`)

```python
    def _matches(self, path: str, globs: list[str]) -> bool:
        from fnmatch import fnmatch
        return any(fnmatch(path, g) for g in globs)

    def _log_exempt(self, path: str, tool: str = "") -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        with (self._dir / "exempt.log").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": self._now(), "path": path, "tool": tool}) + "\n")

    def check_gate(self, paths, ledger, config) -> dict:
        active = self.active_spec()
        spec_status = None
        open_count = 0
        if active is not None:
            rep = {r["id"]: r for r in ledger.status()}  # repair + read
            entry = rep.get(active, {})
            spec_status = entry.get("status")
            # open issue count from sidecar if present
            sc_path = ledger.reviews / f"{active}.md"
            if sc_path.exists():
                from .sidecar import Sidecar
                open_count = Sidecar.read(sc_path).open_issue_count()

        for path in paths:
            if self._matches(path, config.exempt_paths):
                self._log_exempt(path)
                continue
            if self._matches(path, config.allow_globs):
                continue
            # source path -> needs approved active spec
            if active is None:
                return {"allowed": False, "spec_id": None, "status": None,
                        "open_issue_count": 0,
                        "reason": "활성 spec 없음 — begin_implementation 필요"}
            if spec_status not in ("approved", "accepted"):
                return {"allowed": False, "spec_id": active, "status": spec_status,
                        "open_issue_count": open_count,
                        "reason": f"spec {active} 미승인 (status={spec_status}, "
                                  f"open={open_count})"}
        return {"allowed": True, "spec_id": active, "status": spec_status,
                "open_issue_count": open_count, "reason": "ok"}
```

- [ ] **Step 3: Run → PASS** (`pytest tests/test_gate.py -q`), `ruff check .`

- [ ] **Step 4: Commit**

```bash
git add src/specledger/gate.py tests/test_gate.py
git commit -m "feat: check_gate with exempt/allow/default-deny precedence"
```

### Task 16: `hooks/pretooluse_gate.py`

**Files:**
- Create: `hooks/pretooluse_gate.py`
- Test: `tests/test_hook.py`

Claude Code PreToolUse contract: receives JSON on stdin (`tool_name`, `tool_input`, `cwd`). For `Write`/`Edit`/`MultiEdit` it extracts `file_path`(s), makes them relative to `cwd`, runs `check_gate`. Allow → exit 0. Deny → print reason to stderr, exit 2 (blocks the tool and surfaces stderr to the model). The hook resolves the docs root as `<cwd>/docs` and project root as `cwd`; both overridable via env `SPECLEDGER_DOCS` / `SPECLEDGER_ROOT`. Decision logic is delegated to a pure `decide(payload, root, docs_root, now)` function so it is unit-testable without subprocess/stdin.

- [ ] **Step 1: Write failing tests for the pure `decide`**

```python
# tests/test_hook.py
from pathlib import Path
import importlib.util


def load_hook():
    spec = importlib.util.spec_from_file_location(
        "pretooluse_gate", Path("hooks/pretooluse_gate.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _approved(tmp_path):
    from specledger.ledger import Ledger
    from specledger.artifacts import Artifact
    led = Ledger(tmp_path / "docs", now=lambda: "t")
    sid = led.record("spec", "A")
    a = Artifact.load(led._resolve(sid))
    a.meta["status"] = "approved"; a.meta["content_hash"] = a.recompute_hash(); a.save()
    from specledger.gate import Gate
    Gate(tmp_path, now=lambda: "t").begin_implementation(sid)
    return sid


def test_decide_allows_non_edit_tool(tmp_path):
    hook = load_hook()
    d = hook.decide({"tool_name": "Read", "tool_input": {"file_path": "src/x.py"},
                     "cwd": str(tmp_path)}, now=lambda: "t")
    assert d["allow"] is True


def test_decide_allows_source_with_approved_active_spec(tmp_path):
    _approved(tmp_path)
    hook = load_hook()
    d = hook.decide({"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / "src/x.py")},
                     "cwd": str(tmp_path)}, now=lambda: "t")
    assert d["allow"] is True


def test_decide_denies_source_without_marker(tmp_path):
    (tmp_path / "docs").mkdir()
    hook = load_hook()
    d = hook.decide({"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "src/x.py")},
                     "cwd": str(tmp_path)}, now=lambda: "t")
    assert d["allow"] is False
    assert "활성 spec" in d["reason"]
```

- [ ] **Step 2: Run → FAIL**, then implement

```python
# hooks/pretooluse_gate.py
"""Claude Code PreToolUse hook: blocks code edits unless the active spec is approved."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# allow running from a checkout without install
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from specledger.config import SpecledgerConfig  # noqa: E402
from specledger.gate import Gate  # noqa: E402
from specledger.ledger import Ledger  # noqa: E402

_EDIT_TOOLS = {"Write", "Edit", "MultiEdit"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_paths(tool_input: dict) -> list[str]:
    paths = []
    if "file_path" in tool_input:
        paths.append(tool_input["file_path"])
    for edit in tool_input.get("edits", []) or []:
        if "file_path" in edit:
            paths.append(edit["file_path"])
    return paths


def decide(payload: dict, now=_utc_now) -> dict:
    if payload.get("tool_name") not in _EDIT_TOOLS:
        return {"allow": True, "reason": "non-edit tool"}
    cwd = Path(payload.get("cwd", "."))
    root = Path(os.environ.get("SPECLEDGER_ROOT", cwd))
    docs = Path(os.environ.get("SPECLEDGER_DOCS", cwd / "docs"))
    if not docs.exists():
        return {"allow": True, "reason": "no specledger docs root; not governed"}
    rel = []
    for p in _extract_paths(payload.get("tool_input", {})):
        ap = Path(p)
        try:
            rel.append(str(ap.relative_to(root)).replace("\\", "/"))
        except ValueError:
            rel.append(str(ap).replace("\\", "/"))
    gate = Gate(root, now=now)
    ledger = Ledger(docs, now=now)
    res = gate.check_gate(rel, ledger, SpecledgerConfig.load(root))
    return {"allow": res["allowed"], "reason": res["reason"]}


def main() -> int:
    payload = json.load(sys.stdin)
    d = decide(payload)
    if d["allow"]:
        return 0
    print(f"[specledger] blocked: {d['reason']}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run → PASS** (`pytest tests/test_hook.py -q`), `ruff check .`

- [ ] **Step 4: Commit**

```bash
git add hooks/pretooluse_gate.py tests/test_hook.py
git commit -m "feat: PreToolUse hook gating code edits on spec approval"
```

---

## Chunk 6: Wiring (publish, MCP server, integration, docs)

### Task 17: `publish.py` — optional Khala sink

**Files:**
- Create: `src/specledger/publish.py`
- Test: `tests/test_publish.py`

Spec ref: §8. `publish(ledger, artifact_id, config, sink=None)`. If `config.khala is None` → return `{"published": False, "reason": "khala not configured"}` (no-op). Else build an ingest payload `{id, title, status, approved_by, body, source}` and hand to `sink.ingest(payload)` (a `KhalaSink` protocol). `KhalaHttpSink` posts to `config.khala['url']`. Tests use a FakeSink; no network.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_publish.py
from specledger.ledger import Ledger
from specledger.config import SpecledgerConfig
from specledger.publish import publish


class FakeSink:
    def __init__(self): self.payloads = []
    def ingest(self, payload): self.payloads.append(payload); return {"ok": True}


def test_publish_noop_without_khala(tmp_path):
    led = Ledger(tmp_path, now=lambda: "t")
    sid = led.record("spec", "A")
    res = publish(led, sid, SpecledgerConfig(), sink=FakeSink())
    assert res["published"] is False


def test_publish_sends_payload(tmp_path):
    led = Ledger(tmp_path, now=lambda: "t")
    sid = led.record("spec", "A")
    sink = FakeSink()
    cfg = SpecledgerConfig(khala={"url": "http://x"})
    res = publish(led, sid, cfg, sink=sink)
    assert res["published"] is True
    assert sink.payloads[0]["id"] == sid
    assert "body" in sink.payloads[0]
```

- [ ] **Step 2: Run → FAIL**, then implement

```python
# src/specledger/publish.py
from __future__ import annotations

from typing import Protocol

from .artifacts import Artifact


class KhalaSink(Protocol):
    def ingest(self, payload: dict) -> dict: ...


class KhalaHttpSink:
    def __init__(self, url: str):
        self._url = url

    def ingest(self, payload: dict) -> dict:
        import urllib.request

        req = urllib.request.Request(
            self._url, data=__import__("json").dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req) as resp:  # noqa: S310 - configured URL
            return {"status": resp.status}


def publish(ledger, artifact_id, config, sink: KhalaSink | None = None) -> dict:
    if config.khala is None:
        return {"published": False, "reason": "khala not configured"}
    art = Artifact.load(ledger._resolve(artifact_id))
    if sink is None:
        sink = KhalaHttpSink(config.khala["url"])
    payload = {
        "id": art.id, "title": art.meta.get("title", ""), "status": str(art.status),
        "approved_by": art.meta.get("approved_by"), "body": art.body,
        "source": str(art.path),
    }
    sink.ingest(payload)
    return {"published": True, "reason": "ok"}
```

- [ ] **Step 3: Run → PASS**, `ruff check .`

- [ ] **Step 4: Commit**

```bash
git add src/specledger/publish.py tests/test_publish.py
git commit -m "feat: optional Khala publish (no-op without config)"
```

### Task 18: `server.py` — FastMCP wiring

**Files:**
- Create: `src/specledger/server.py`
- Test: `tests/test_server.py`

Thin adapter: constructs `Ledger`/`Gate` from env (`SPECLEDGER_DOCS`, `SPECLEDGER_ROOT`) and a real-clock `now`, then registers one MCP tool per core operation (`record`, `critique`, `approve`, `status`, `supersede`, `check_gate`, `begin_implementation`, `end_implementation`, `index`, `publish`). Each tool is a 1–3 line wrapper calling core. No business logic here. Provide a `build_app(ledger, gate, critic, config)` factory so the wiring is testable without env/process.

- [ ] **Step 1: Write a failing wiring test**

```python
# tests/test_server.py
from specledger.server import build_app
from specledger.ledger import Ledger
from specledger.gate import Gate
from specledger.config import SpecledgerConfig
from helpers import FakeCritic


def test_build_app_registers_tools(tmp_path):
    import asyncio
    led = Ledger(tmp_path / "docs", now=lambda: "t")
    gate = Gate(tmp_path, now=lambda: "t")
    app = build_app(led, gate, FakeCritic(), SpecledgerConfig())
    tools = asyncio.run(app.list_tools())  # public FastMCP API -> list[Tool]
    names = {t.name for t in tools}
    assert {"record", "critique", "approve", "status", "check_gate", "index",
            "supersede", "begin_implementation", "end_implementation", "publish"} == names
```

- [ ] **Step 2: Run → FAIL**, then implement

```python
# src/specledger/server.py
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import review
from .config import SpecledgerConfig
from .critique import AnthropicCritic, critique
from .gate import Gate
from .ledger import Ledger
from .publish import publish


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_app(ledger: Ledger, gate: Gate, critic, config: SpecledgerConfig) -> FastMCP:
    app = FastMCP("specledger")

    @app.tool()
    def record(type: str, title: str, slug: str | None = None) -> str:
        return ledger.record(type, title, slug)

    @app.tool(name="critique")
    def critique_doc(artifact_id: str) -> list[dict]:
        return [i.to_dict() for i in critique(ledger, artifact_id, critic, now=_utc_now)]

    @app.tool()
    def approve(artifact_id: str, dispositions: list[dict], approver: str) -> dict:
        review.approve(ledger, artifact_id, dispositions, approver, now=_utc_now)
        return {"ok": True}

    @app.tool()
    def status(artifact_id: str | None = None) -> list[dict]:
        return ledger.status(artifact_id)

    @app.tool()
    def supersede(old_id: str, new_id: str) -> dict:
        ledger.supersede(old_id, new_id)
        return {"ok": True}

    @app.tool()
    def begin_implementation(spec_id: str) -> dict:
        gate.begin_implementation(spec_id, set_by="agent")
        return {"ok": True}

    @app.tool()
    def end_implementation() -> dict:
        gate.end_implementation()
        return {"ok": True}

    @app.tool()
    def check_gate(paths: list[str]) -> dict:
        return gate.check_gate(paths, ledger, config)

    @app.tool()
    def index() -> str:
        return str(ledger.index())

    @app.tool(name="publish")
    def publish_doc(artifact_id: str) -> dict:
        return publish(ledger, artifact_id, config)

    return app


def main() -> None:
    root = Path(os.environ.get("SPECLEDGER_ROOT", "."))
    docs = Path(os.environ.get("SPECLEDGER_DOCS", root / "docs"))
    config = SpecledgerConfig.load(root)
    ledger = Ledger(docs, now=_utc_now)
    gate = Gate(root, now=_utc_now)
    critic = AnthropicCritic()
    build_app(ledger, gate, critic, config).run()


if __name__ == "__main__":
    main()
```

> Note: `critique_doc`/`publish_doc` use `@app.tool(name="critique")` / `@app.tool(name="publish")` so the MCP-exposed names match the spec without shadowing the imported `critique`/`publish` functions. `name=` is the documented FastMCP argument; verify it against the installed `mcp` version during implementation. If `list_tools()` is not awaitable in the installed SDK, adapt the test's listing call accordingly — the `name=` wiring is the load-bearing part.

- [ ] **Step 3: Run → PASS**, `ruff check .`

- [ ] **Step 4: Commit**

```bash
git add src/specledger/server.py tests/test_server.py
git commit -m "feat: FastMCP server wiring (all tools)"
```

### Task 19: End-to-end integration test

**Files:**
- Test: `tests/test_integration.py`

- [ ] **Step 1: Write the full-flow test**

```python
# tests/test_integration.py
from specledger.ledger import Ledger
from specledger.gate import Gate
from specledger.config import SpecledgerConfig
from specledger.artifacts import Artifact, Status
from specledger.critique import critique
from specledger.review import approve
from helpers import FakeCritic


def test_record_critique_fix_approve_then_gate_allows(tmp_path):
    docs = tmp_path / "docs"
    led = Ledger(docs, now=lambda: "t")
    gate = Gate(tmp_path, now=lambda: "t")
    cfg = SpecledgerConfig()

    sid = led.record("spec", "Playlist Self-Update")
    # gate blocks before approval
    gate.begin_implementation(sid)
    assert led.status(sid)[0]["status"] == "draft"
    assert gate.check_gate(["src/app.py"], led, cfg)["allowed"] is False

    critique(led, sid, FakeCritic(), now=lambda: "t")
    a = Artifact.load(led._resolve(sid)); a.body += "\nadded the invariant\n"; a.save()
    approve(led, sid, [{"issue_id": "I-001", "disposition": "accepted"}], "eisen", now=lambda: "t")

    assert Artifact.load(led._resolve(sid)).status == Status.APPROVED
    assert gate.check_gate(["src/app.py"], led, cfg)["allowed"] is True


def test_tamper_after_approval_reblocks_gate(tmp_path):
    docs = tmp_path / "docs"
    led = Ledger(docs, now=lambda: "t")
    gate = Gate(tmp_path, now=lambda: "t")
    sid = led.record("spec", "A")
    critique(led, sid, FakeCritic(), now=lambda: "t")
    a = Artifact.load(led._resolve(sid)); a.body += "\nfix\n"; a.save()
    approve(led, sid, [{"issue_id": "I-001", "disposition": "accepted"}], "eisen", now=lambda: "t")
    gate.begin_implementation(sid)
    assert gate.check_gate(["src/x.py"], led, SpecledgerConfig())["allowed"] is True
    # tamper -> status() repairs to in_review -> gate now denies
    a2 = Artifact.load(led._resolve(sid)); a2.body += "\nsneaky\n"; a2.save()
    assert gate.check_gate(["src/x.py"], led, SpecledgerConfig())["allowed"] is False
```

- [ ] **Step 2: Run → PASS** (`pytest tests/test_integration.py -q`), then full suite `pytest -q`

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: end-to-end gate flow (record→critique→fix→approve→gate; tamper re-blocks)"
```

### Task 20: README + hook registration docs

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`** covering: what specledger is (one paragraph from spec §1), install (`pip install -e ".[dev]"`), the MCP server registration snippet for `.mcp.json`/Claude Code, and the PreToolUse hook registration in `settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          { "type": "command",
            "command": "python /abs/path/specledger/hooks/pretooluse_gate.py" }
        ]
      }
    ]
  }
}
```

Include the `SPECLEDGER_ROOT`/`SPECLEDGER_DOCS`/`ANTHROPIC_API_KEY` env vars and a "first consumer: Engception" quickstart (record → critique → disposition → approve → begin_implementation).

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with install, MCP + hook registration"
```

---

## Done criteria

- `pytest -q` green; `ruff check .` clean.
- All 10 MCP tools exposed by `build_app`; hook blocks source edits unless the active spec is approved; tamper-after-approval re-blocks via report-and-repair.
- Khala publish is a no-op without config; never a hard dependency.
- First real use: register Engception's scattered specs and drive one through record → critique → disposition → approve.

## Deferred (per spec §1 Non-goals — do NOT build here)
Team auth / real approver identity; `governs:` path-glob precision mapping; code-drift auto `stale`; comprehension questions; spec-as-source codegen; auto-publish-on-approve.
