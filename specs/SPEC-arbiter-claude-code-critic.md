---
id: SPEC-arbiter-claude-code-critic
type: spec
title: A keyless Arbiter critic — run the gate through claude -p, no paid key
status: approved
linked_adrs:
- ADR-0004
- ADR-0005
- ADR-0007
tags:
- arbiter
- critic
- dev
- provider
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-11T17:12:24Z'
content_hash: sha256:6d3e4bb3c1f44c549bb58aaf9db338d3bf7c2de8b11caa768fd71fc43f5e8659
---

## 0. Naming (per ADR-0005/0007)

This component is **Arbiter** — the package `khala.arbiter` (`arbiter/`). [[ADR-0004]] is a pre-rename
record and still calls it `specledger` with `specledger/src/...` symbols; [[ADR-0005]] mapped
`specledger → Arbiter` and [[ADR-0007]] records that the directory/package migration **landed**
(`arbiter/` is the shipping code). So an ADR-0004 "specledger" reference resolves to this package;
the binding is the import path `khala.arbiter`, not ADR-0004's frozen name.

## 1. Goal

Let the Arbiter critique gate run **without a paid `ANTHROPIC_API_KEY`**, by adding a critic backend
that reviews through the `claude` CLI already authenticated on the host. This is the sibling of the
Nexus keyless narration backend — same idea, one layer over: the deterministic gate machinery
(record → critique → disposition → approve) is already keyless; only the LLM *critic* needed a key.

The consumer is real and present: every SPEC/ADR gate this project runs needs the critic, the key is
exhausted, and the keyless critic has so far been hand-written in a throwaway script each time. This
productizes that. (That the throwaway script works is context, not the evidence for this design — the
evidence is §7's unit tests and §8's live check; the falsifiable artifact of a keyless gate is the
sidecar it writes, not this sentence.)

## 2. Non-goals

- **Replacing `AnthropicCritic`.** It stays the default; `claude-code` is opt-in. Team/CI with a key
  is unchanged.
- **A host bridge.** Unlike Nexus (containerized, reaches the host CLI over HTTP), **Arbiter runs on
  the host** — the CLI and MCP server are host processes. So the critic shells `claude` directly; no
  bridge, no port, no token.
- **A general multi-LLM critic framework.** Two backends behind the existing `Critic` Protocol, one
  selector. No plugin system.
- **Changing the gate semantics.** `critique()` / `approve()` and the sidecar are untouched; this
  only adds a `Critic` implementation and a selector for who constructs it.

## 3. What exists (verified 2026-07-11)

- `arbiter/src/khala/arbiter/critique.py`: the `Critic` Protocol
  (`find_issues(body, linked_adr_bodies, rubric) -> list[(category, severity, description)]`),
  `AnthropicCritic` (Anthropic SDK, lazy key), the shared `_PROMPT` and `_unwrap_json`, and
  `critique()` which is **fail-closed** (any critic exception → `CritiqueError`).
- Two construction sites, both hardcoding `AnthropicCritic()`: `cli.py:124` (`main()` →
  `build_cli(root, docs, AnthropicCritic())`) and `server.py:92` (MCP → `build_app(ledger, gate,
  critic, config)`). Both take the critic as an injected argument, so only the *default construction*
  changes.
- `claude` CLI on the host (v2.1.207). The pinned doors-closed invocation
  `claude -p --output-format text --allowed-tools "" --strict-mcp-config --setting-sources "" --no-session-persistence`
  returns text keyless — the invocation is pinned against **that CLI version**; the §7 unit tests
  assert what argv we *pass*, and the §8 live check is where a CLI-version drift (a flag rename or
  semantics change) would actually surface. This SPEC moves the keyless critic into the package.

## 4. Design

### 4.1 `ClaudeCodeCritic` (keyless)

A `Critic` in `critique.py` that mirrors `AnthropicCritic` but runs the host CLI:

- `find_issues(body, linked, rubric)` builds the **same `_PROMPT`** the Anthropic critic uses, runs
  the pinned `claude -p` invocation (§5) with the prompt on **stdin** and `encoding=utf-8` on the
  pipes (the prompt carries em-dashes that Windows cp949 cannot encode — verified while hand-running
  the gate), and parses the JSON array with the shared `_unwrap_json`.
- The subprocess runner is **injectable** so the critic is unit-testable without spawning `claude`.
- A non-zero exit, a timeout, or unparseable output **raises** — `critique()` turns that into
  `CritiqueError` (fail-closed). A gate that cannot review must fail, never pass silently.
- **Timeout & model (I-005):** a wall-clock timeout bounds the run, default **300s** (critiques are
  long), configurable via `ARBITER_CRITIC_TIMEOUT`. The model is the CLI's session default unless
  `ARBITER_CRITIC_MODEL` is set (then `--model` is added) — no model is silently hardcoded.

### 4.2 Selector

`make_critic(name: str | None = None) -> Critic` reads `ARBITER_CRITIC` (default `anthropic`):

- `anthropic` → `AnthropicCritic()`.
- `claude-code` → `ClaudeCodeCritic()`.
- anything else → raise with a clear message (no silent fallback that hides a typo).

`cli.py main()` and the MCP `server.py` construct their critic via `make_critic()` instead of
hardcoding `AnthropicCritic()`. `build_cli(root, docs, critic)` still takes an injected critic, so
tests keep passing a `FakeCritic` — the selector only changes the default construction.

## 5. Security — the critic must not become host execution

`claude -p` can use tools and load the host's MCP servers/settings. Arbiter feeds **SPEC/ADR body
text** into the prompt — lower injection risk than Nexus's corpus documents, but a drafted artifact
could still carry an injection. So the critic uses the **same doors-closed invocation** the Nexus
bridge pinned, for the same reason and consistency:
`--allowed-tools "" --strict-mcp-config --setting-sources "" --no-session-persistence`
(no built-in tools · no MCP · no user settings/hooks/skills · no transcript persistence — the last
keeps artifact text out of the host `~/.claude` **session/transcript** store, which is the persistence
this flag controls; it is not a claim about every possible log the CLI might emit). A unit test pins
all four flags in the argv.

**What these flags do and do not protect (I-001).** They stop an injection from turning the review
into **host execution** — the load-bearing risk. They do **not** guarantee the *verdict* is
uncorrupted: an artifact could try to talk the critic into "no issues." Three things bound that, and
none is new to this backend: (a) artifacts are **human-authored** SPEC/ADRs, not adversarial external
input, so the attacker would be the author reviewing their own doc; (b) `AnthropicCritic` has the
**identical** verdict-corruption exposure — this is inherent to LLM-as-critic, not introduced here;
(c) the **human disposition and approval** step is the backstop — a corrupted "0 issues" review still
cannot self-approve; a person signs. Verdict integrity is a property of the review process, not of
the tool flags, and it is unchanged by this SPEC.

## 6. Error handling

- `ARBITER_CRITIC=claude-code` but `claude` not on PATH → the runner's `OSError`/`FileNotFoundError`
  propagates → `CritiqueError` with a message naming `claude` (fail-closed).
- **`claude` unauthenticated or out of subscription quota (I-004)** → `claude -p` exits non-zero →
  `CritiqueError` (fail-closed). "keyless" means "no `ANTHROPIC_API_KEY`", not "no auth at all" — it
  relies on an authenticated host session; if that is absent the gate fails clearly and the operator
  switches back to `ARBITER_CRITIC=anthropic`.
- Non-zero exit / timeout / unparseable JSON → raises → `CritiqueError`. The gate does not proceed on
  a review it could not obtain.
- Unknown `ARBITER_CRITIC` → raise at `make_critic()` time.
- `AnthropicCritic` keeps its existing "no key" message when it is the one selected and the key is
  absent — the two failure modes stay distinct.

## 7. Testing

- `ClaudeCodeCritic.find_issues` with an injected runner returning a JSON array yields the parsed
  `(category, severity, description)` tuples; a fenced ```json block is unwrapped by `_unwrap_json`.
- The spawned argv contains **all four** doors-closed flags (load-bearing, §5) — missing any fails.
- A non-zero runner exit, and unparseable output, each raise (fail-closed).
- The prompt fed to the runner contains the artifact body and the rubric (the same `_PROMPT` shape).
- `make_critic()` returns `AnthropicCritic` by default, `ClaudeCodeCritic` for `claude-code`, and
  raises for an unknown value.
- Existing critique tests (with `FakeCritic`) are untouched and still pass — the seam does not change
  `critique()`.

## 8. Acceptance

`ARBITER_CRITIC=claude-code arbiter critique <id>` with **no `ANTHROPIC_API_KEY`** **exits 0 and
writes the sidecar** for `<id>` — the observable, deterministic proof the gate ran keyless. The issue
*content* is not asserted (LLM output varies, and a legitimate **zero-issue** review is a valid
result, not a failure) — what is asserted is that a review completed and was recorded without a key.
A failure to reach `claude` is instead a non-zero exit with no sidecar written (fail-closed, §6), so
the two are distinguishable. Unset `ARBITER_CRITIC` (or set `anthropic`) and it uses the key exactly
as before. The unit suite proves the seam, the parse, and the four security flags without spawning
`claude`; this live check is the go-live gate — and this SPEC's own gate was that check, critiqued by
`claude -p`, keyless.
