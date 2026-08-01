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
- **Give new dependencies an upper bound when they gate an import path you rely on**
  (e.g. `mcp>=1.2.0,<2`). Constraints stop CI from drifting; the bound is what stops a
  fresh `pip install` outside CI from picking up an incompatible major.
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

## License

The repository is MIT licensed (see [LICENSE](./LICENSE)). The root license
covers every tool in the monorepo.
