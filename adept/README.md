# Adept — cognitive-debt meter

`ken` (Scots/English: "to know, to understand") measures whether a *named human* can
currently **vouch** for an artifact — not via a rubber-stamp click, but by passing
graded, grounded comprehension questions generated from the artifact's actual content.

A passing vouch is bound to the artifact's `content_hash`, so it goes **stale** when the
artifact changes. Per-question mastery is tracked on a spaced-repetition ladder, so
questions resurface for re-testing until they are passed again. The org-level metric is
**cognitive-debt coverage**: the fraction of registered critical artifacts a person can
vouch for — plus the **orphan list** (artifacts with no current voucher) = the
cognitive-debt hotlist. It never consults git history, so it is AI-authorship-safe.

## Install

```bash
uv tool install ./ken           # or: pipx install ./ken  — installs the global `ken` command
pip install -e 'ken[dev]'       # development (editable + pytest/ruff)
pip install -e 'ken[postgres]'  # optional Postgres backend
```

## CLI

Run `ken` from anywhere in your project — the root is the nearest `ken.manifest.yaml`
(walking up from the current directory). Artifact paths are stored relative to that root,
so the manifest is clone-portable.

```bash
ken register PATH                              # register an artifact; prints its artifact_id
ken due --as PERSON                            # list due questions / artifacts needing questions
ken save-questions ARTIFACT_ID --hash HASH     # store questions (one per stdin line)
ken record-attempt --as PERSON --question QID --artifact AID --passed|--failed
ken coverage --as PERSON                       # covered/total, orphan hotlist, weakness map
ken review ARTIFACT_ID --as PERSON             # headless self-drive (needs ANTHROPIC_API_KEY)
```

The agent-driven loop (`due` → `save-questions` → `record-attempt` → `coverage`) needs no
API key — a Claude Code session supplies the cognition (question generation, grading,
remediation). Only `ken review` calls the model directly and therefore needs
`ANTHROPIC_API_KEY`.
