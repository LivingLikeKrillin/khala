# Conventions

Shared conventions for the Khala monorepo. Per-tool rules (language style, lint
config) live in each tool's own `CLAUDE.md` / docs; this file covers what applies
across the ecosystem.

## Terminology

- **Khala = the ecosystem** — the umbrella over all the tools, the shared link
  through which they connect. "Khala" is never a single runnable component.
- **Nexus = the knowledge-base component** — one of the tools (Enterprise RAG +
  GraphRAG), the grounded body the others read from and write to.

Do not use "Khala" to mean the knowledge base, and do not use "Nexus" to mean the
ecosystem. When in doubt: Khala is the alliance, Nexus is a member.

### Which language a term is written in

`GLOSSARY.md` is the record of what each thing is called and why. It is also what
`scripts/check_terms.py` reads — there is no second list. Three rules decide new terms:

1. **Things the machine handles keep their original name.** `embedding`, `chunk`,
   `corpus`, `tenant`, `RRF`, `Recall@10`. The repo already does this: 토큰 228 uses,
   청크 173, 코퍼스 135, 임베딩 73 — all transliterated, none translated.
2. **Things a person judges are written in Korean — but only where the field already
   has a Korean word.** 대조군, 표본, 유의수준, 천장 효과 come from statistics; they were
   not invented here.
3. ⭐ **If you would have to invent the translation, don't translate.** Rule 2 not
   finding a word is the signal to fall back to rule 1.

Rule 3 exists because of measurement, not taste. A sweep of 230 prose files on 2026-08-27
found thirteen physical-object words doing technical work. Five carried meanings invented
here, standing in for terms the field already had — `자` alone appeared 136 times across
21 files and had reached an approved SPEC filename. Two more were real terms rendered as
body parts (`arm` → `팔`, `trigger` → `방아쇠`), which is rule 2 applied without checking what
practitioners actually say.

The invented five were all born the same way: the concept belonged to rule 2, no Korean
word existed, and one got made up. Inventing a word feels like precision and reads as
jargon to everyone else.

Records keep the words of their time: approved SPECs, ADRs, the public engineering log,
and dated measurement reports are not rewritten. This is the same rule the component
rename followed.

The rules cover code comments, docstrings and user-facing strings as well as prose —
same words, same readers. **They also cover what an agent says in the conversation**, which
is where they were broken three times after the sweep finished: `check_terms.py` reads a
diff, and a reported sentence is not one. The `Stop` hook (`scripts/hooks/terms_guard.py`)
runs the same judgement over the turn's own message and blocks it once, with the
replacement word. Quoting a retired term is done in backticks, as this file does. They stop at **data**: evaluation labels and questions are the
input to measurement and are bound by signatures and manifests, and the retraction ledger
is stamped. `GLOSSARY.md` lists what is frozen and why.

## Naming

- **A lowercase top-level directory is a tool.** `nexus/`, `observer/`,
  `arbiter/`, `probe/`, `adept/`, `adept-web/`, `docs/`. The directory name is the tool's canonical
  name. Adding a tool means adding a lowercase directory and a row in the
  README tool map. (Exception: shared non-tool directories such as `assets/`
  are also lowercase but are not tools and do not get a README entry.)
- Within a tool, follow that tool's own file-naming convention (e.g. Observer
  uses kebab-case TypeScript files; Nexus uses Python module
  conventions).

## Versioning

- **Each tool is versioned independently** with its own semantic version
  (`MAJOR.MINOR.PATCH`). There is no single monorepo version.
- **Each tool keeps its own `CHANGELOG.md`** at the root of its directory (e.g.
  `nexus/CHANGELOG.md`). Record breaking changes, features, and fixes per tool —
  do not maintain a shared changelog.
- A change that touches one tool only bumps that tool's version.

## Dependencies

- **`pyproject.toml` declares what is required; `constraints.txt` records which versions we
  tested.** Every Python subproject carries a committed `constraints.txt` with the fully
  resolved set, and every install in CI, the Taskfile, and the nexus image passes it with
  `pip install ... -c constraints.txt`.
- **After adding, removing, or upgrading a dependency, run `task deps:lock` and commit the
  regenerated `constraints.txt`** alongside the `pyproject.toml` change. CI's `deps` job
  fails the build if a declared requirement is not pinned, or if a pin violates its
  declared specifier.
- **Every requirement carries an upper bound**, set at the next major above the version we
  test (`<1` for a 0.x dependency, e.g. `anthropic>=0.39.0,<1`). Constraints stop CI from
  drifting; the bound is what stops a fresh `pip install` *outside* CI — a new checkout, a
  rebuilt image, a developer's machine — from picking up an incompatible major.
  For CalVer dependencies the year is the major (`structlog>=24.4.0,<27`), which makes the
  yearly bump a deliberate one.
- **Raising a bound is a deliberate change**, not a side effect: bump it, run
  `task deps:lock`, and let the suites say whether the new major is actually fine.
  The one exception is this repo's own path dependencies (`khala-adept`), which are
  versioned in lockstep rather than resolved from an index.
- **Node subprojects install from their lockfiles** — `npm ci` and
  `pnpm install --frozen-lockfile`, never bare `npm install`.

Why: on 2026-08-01 `mcp` 2.0.0 shipped and removed `mcp.server.fastmcp`. Both nexus and
arbiter declared an unbounded requirement and CI re-resolved on every run, so two
documentation PRs that touched no code failed with `ModuleNotFoundError`. The version we
tested was never the version we declared.

## Contribution flow

- **Branches:** one logical change per branch. Name branches by type and scope:
  `feat/<tool>-<short-desc>`, `fix/<tool>-<short-desc>`, `chore/<short-desc>`,
  `docs/<short-desc>`.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/).
  ```
  feat:     a new feature
  fix:      a bug fix
  refactor: code change that neither fixes a bug nor adds a feature
  docs:     documentation only
  test:     adding or correcting tests
  chore:    build, tooling, or config
  ```
  Scope by tool when it helps, e.g. `feat(probe): add review grounder`.
- Keep each PR scoped to a single tool and a single concern where possible.

## Retracting a claim in a signed document

An approved SPEC or accepted ADR is stamped with a hash of its **body**. Later work
sometimes proves one conclusion inside it wrong. The document does not become
un-approved for that — what is wrong is a claim, not the decision — so the claim is
**retracted from outside the body**.

1. Add an entry to [`specs/retractions.yaml`](./specs/retractions.yaml): `target`,
   `retracted_by` (the SPEC or ADR that overturns it), `signed_by`, `signed_at`, the
   `quote` of the sentence being withdrawn, and `why`.
2. Add `retractions: [<retracted_by>]` to the target's **frontmatter**. Frontmatter is
   not covered by the body hash — `content_hash` lives there itself — so this is the one
   layer a frozen document can still gain a marker in.
3. Leave `status` alone. The document is still approved.
4. **Do not touch the body**, and do not re-stamp.

`scripts/ledger_integrity.py` fails the build if the two halves drift: an entry whose
target does not point back, a pointer with no entry behind it, or a quote that does not
appear in the target.

Why: on 2026-08-14 two retractions were written as footnotes *inside* the approved
bodies. That broke both stamps and `master` stayed red for fifteen merges — every other
regression in that window hid behind it. Re-stamping would have fixed the red and made
"edit the body, then re-stamp" the routine, which is the exact motion the stamp exists to
detect. The rule that keeps this honest is the second one: **a retraction nobody can see
is worse than a broken hash**, which is why the pointer is enforced rather than suggested.

## License

The repository is MIT licensed (see [LICENSE](./LICENSE)). The root license
covers every tool in the monorepo.
