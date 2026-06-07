# Migration & Publish Checklist

This document is the durable, canonical record of how the **Khala** monorepo was
consolidated and how it is published. It captures the owner's chosen publish
sequence so the procedure is reproducible and auditable.

The monorepo was assembled by a history-preserving integration of five formerly
separate repositories — **nexus** (formerly the `khala` package), **probe**,
**specledger**, **mutqa**, and **docs** — followed by a `Khala → Nexus` rename
(the component formerly named *Khala* became *Nexus*; the name **Khala** is now
reserved for the ecosystem / monorepo itself).

> **Posture: preserve, don't delete.** Every superseded artifact (old GitHub
> repos, original source directories) is *archived* or *kept in place* as a
> rollback safety net. Nothing is deleted by automation. The owner deletes
> originals only after confirming the published monorepo is good.

---

## Pre-publish verification (gate — all green)

The publish must not proceed unless the full monorepo verification is green and
the rename audit is clean. The last verified run:

| Subproject | Result | Baseline |
|------------|--------|----------|
| probe      | 206 passed | 206 passed |
| specledger | 71 passed | 71 passed |
| mutqa      | 39 passed | 39 passed |
| nexus      | 166 passed, 14 skipped (DB/Docker — no Docker) | 166 + 14 skipped |
| docs       | build PASS, check 0 errors, linkcheck 48/48 | same |

Rename audit (Task 13): **clean** — the only `khala` matches in tracked code are
intentional rename-history entries inside `CHANGELOG.md` files; no component-code
or docs residuals. Allowed survivals are the ecosystem name and the
`LivingLikeKrillin/khala` GitHub URLs (after publish, that repo *is* the
monorepo).

Re-run commands:

```bash
cd probe && pnpm test:run
cd specledger && python -m pytest -q
cd mutqa && python -m pytest -q
cd nexus && python -m pytest -q
cd docs && npm run build && npm run check && npm run linkcheck
```

---

## Done by automation (steps 1–4)

The controller executes these GitHub/filesystem steps automatically. They are
recorded here as the authoritative sequence.

### 1. Final placement
Move the monorepo to its permanent home:

```
C:/Users/Eisen/Desktop/Labs/_bmono/khala
      →  C:/Users/Eisen/Desktop/Labs/[projects] khala
```

### 2. Rename the old GitHub repo FIRST (collision avoidance)
The existing component repo is named `khala` on GitHub. Rename it so the
ecosystem name `khala` is free for the monorepo:

```bash
gh repo rename nexus-legacy --repo LivingLikeKrillin/khala
```

This renames `LivingLikeKrillin/khala` → `LivingLikeKrillin/nexus-legacy`.

### 3. Create + push the new monorepo repo
From inside the monorepo's permanent home:

```bash
gh repo create khala --private --source=. --remote=origin --push
```

Creates private `LivingLikeKrillin/khala` and pushes `master`.

### 4. Archive (NOT delete) the superseded repos
Archiving makes them read-only and rollback-safe — deletion is never used:

```bash
gh repo archive LivingLikeKrillin/nexus-legacy --yes
gh repo archive LivingLikeKrillin/probe --yes
gh repo archive LivingLikeKrillin/specledger --yes
```

---

## Owner manual (steps 5–6)

These steps require owner judgment and credentials; they are **not** automated.

### 5. Cloudflare Pages reconnection (manual)
Repoint the docs site to the monorepo's `docs/` subdirectory.

- **Repo connection:** point the Pages project at `LivingLikeKrillin/khala`.
- **Build command:** `npm --prefix docs run build` (or set the project root to
  `docs/`).
- **Output directory:** `docs/dist`.

### 6. Original directories (owner decision — NOT deleted)
The five original source directories are preserved as rollback until the owner
confirms the monorepo + push are good. Delete only after confirmation:

| Tool | Original location |
|------|-------------------|
| khala (→ nexus) | `C:/Users/Eisen/Desktop/Labs/[projects] khala-ecosystem/khala` |
| probe | `C:/Users/Eisen/Desktop/Labs/[projects] khala-ecosystem/probe` |
| khala-docs | `C:/Users/Eisen/Desktop/Labs/[projects] khala-ecosystem/khala-docs` |
| specledger | `C:/Users/Eisen/Desktop/Labs/[claude] mcp-tools/specledger` |
| mutqa | `C:/Users/Eisen/Desktop/Labs/[claude] skills/mutqa` |

The throwaway work clones at `_bmono/clones/` can be deleted at any time.

---

## Known follow-ups (owner)

These are pre-existing or out-of-scope items, recorded for owner follow-up. None
block publish.

- **(a) Line endings:** `nexus/LICENSE` and some files use CRLF, which differs
  from the new `.editorconfig` LF rule. The rule is additive; existing files
  were not reformatted.
- **(b) probe formatting:** probe was never run through prettier. The root
  `.prettierrc` is check-only (add-only), so probe's existing style is unchanged.
- **(c) probe docs container name:** two probe docs reference the container
  `nexus-postgres`, but the actual container is `nexus-db`.
- **(d) nexus ruff findings:** 24 pre-existing ruff findings remain in nexus
  (carried over; not introduced by the consolidation).
- **(e) docs clone-snippet URLs:** docs clone snippets point at the ecosystem
  `khala` repo — which, after publish, *is* this monorepo. Correct by design.
