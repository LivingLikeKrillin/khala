---
title: Arbiter
description: Records AI-generated specs and ADRs, and gates code edits behind signed-off review.
---

Arbiter makes the moment of judgment accountable instead of assumed. It's a Python MCP server plus a Claude Code `PreToolUse` hook: it records AI-generated ADRs and design specs as Markdown with frontmatter, and enforces a review sequence before any code is written: **AI critique, then human issue-disposition, then sign-off.** Approved documents can be published to a Nexus sink.

When an assistant produces a confident spec, the easiest thing to do is approve it. Review turns into ceremony: a green check on text nobody really read. Arbiter forces judgment to happen where it's cheap and where it leaves a record. Until a spec is approved and stamped with a content hash, every `Write`/`Edit`/`MultiEdit` on a non-exempt source path is **blocked**. The gate is active during implementation: `begin_implementation` arms it, `end_implementation` disarms it.

In short: a ledger that makes "who approved what, and why" a recorded, attributable act, so you can't rubber-stamp your way past it.

<svg class="kh-fig" viewBox="0 0 560 224" role="img" aria-label="Arbiter gates implementation on an approved, content-hashed spec. SPEC-014 goes Recorded → Critiqued (2 issues) → Approved and locked; the approved hash e34a17c9 must match the change hash for the gate to open — a mismatch blocks Write/Edit.">
<defs><marker id="ab-a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="kh-fig-ah" d="M0 0 L10 5 L0 10 z"/></marker></defs>
<rect class="kh-fig-box" x="24" y="28" width="120" height="38" rx="6"/>
<text class="kh-fig-d" x="84" y="47" text-anchor="middle">Recorded</text>
<path class="kh-fig-line" d="M144 47 L176 47" marker-end="url(#ab-a)"/>
<rect class="kh-fig-box" x="176" y="28" width="150" height="38" rx="6"/>
<text class="kh-fig-d" x="251" y="47" text-anchor="middle">Critiqued · 2 issues</text>
<path class="kh-fig-line" d="M326 47 L358 47" marker-end="url(#ab-a)"/>
<rect class="kh-fig-box-acc" x="358" y="28" width="164" height="38" rx="6"/>
<text class="kh-fig-d" x="440" y="47" text-anchor="middle">Approved · locked</text>
<rect class="kh-fig-panel" x="24" y="92" width="512" height="118" rx="8"/>
<text class="kh-fig-h" x="42" y="116">GATE · APPROVED_HASH</text>
<line class="kh-fig-rule" x1="42" y1="128" x2="518" y2="128"/>
<text class="kh-fig-d" x="42" y="152">approved</text>
<text class="kh-fig-d" x="140" y="152">e34a17c9</text>
<text class="kh-fig-d" x="42" y="176">change</text>
<text class="kh-fig-d" x="140" y="176">e34a17c9</text>
<path class="kh-fig-line-acc" d="M244 152 L256 152 L256 164 M244 176 L256 176 L256 164 M256 164 L274 164" marker-end="url(#ab-a)"/>
<text class="kh-fig-verified" x="286" y="164">✓ MATCH · gate open</text>
<text class="kh-fig-s" x="42" y="200">mismatch → Write / Edit blocked</text>
</svg>

## Core concepts

- **The gate.** Until a spec is `approved` and content-hash-stamped, file-edit tools on non-exempt paths are blocked. `docs/**` and `tests/**` are allow-globbed by default (configurable via `allow_globs`).
- **Arm / disarm.** `begin_implementation` arms the gate for a specific spec; `end_implementation` disarms it. The gate is only enforced during implementation.
- **Accountable review flow.** `critique` runs AI review and opens issues in a sidecar; the human edits the body to address each; `approve` takes per-issue dispositions, verifies the body actually changed, then stamps the content hash and sets `status=approved`.
- **Content-hash stamping + tamper detection.** Approval binds the spec to a hash; `status` reports state and detects tampering.
- **No database.** All state lives in Markdown files under `ARBITER_DOCS` plus a small `.arbiter/` marker under `ARBITER_ROOT`.
- **Optional Nexus publish.** `publish` pushes an approved doc to a configured Nexus sink — a safe no-op when not configured.
- **The same gate from a CLI.** You do not need MCP to run it: `arbiter record`, `status`, `critique`, `approve`, `check-gate`. The CLI calls the *same functions* the MCP server does, so a human and an agent cannot reach different verdicts on the same spec.

## Quickstart

Arbiter is a Python package; it runs as an MCP server and a PreToolUse hook. Commands transcribed exactly from the source repo README.

### Install

```bash
pip install -e ".[dev]"
```

### Register the MCP server (`.mcp.json`)

```json
{
  "mcpServers": {
    "arbiter": {
      "command": "python",
      "args": ["-m", "khala.arbiter.server"],
      "env": {
        "ARBITER_ROOT": "/abs/path/to/your/project",
        "ARBITER_DOCS": "/abs/path/to/your/project/docs",
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

`ARBITER_ROOT` is the project root where `.arbiter/` state lives (defaults to `.`); `ARBITER_DOCS` is where spec/ADR Markdown is written (defaults to `$ARBITER_ROOT/docs`); `ANTHROPIC_API_KEY` is required only for the built-in `AnthropicCritic`.

### Register the PreToolUse hook (`.claude/settings.json`)

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python /abs/path/arbiter/hooks/pretooluse_gate.py"
          }
        ]
      }
    ]
  }
}
```

The hook reads the tool payload from stdin and exits `0` (allow) or `2` (block).

## How-to

### Record → critique → approve → implement

The first-consumer flow, transcribed from the README:

```
1. record                 → record("spec", "Playlist Self-Update")  → SPEC-playlist-self-update
2. critique               → critique("SPEC-playlist-self-update")    → opens issues (e.g. I-001)
3. fix + disposition      → human edits the body to address each issue
4. approve                → approve(id, [{"issue_id":"I-001","disposition":"accepted"}], "reviewer")
                             verifies body changed, stamps content hash, status=approved
5. begin_implementation   → arms the gate; Write/Edit on src/ paths now allowed
6. end_implementation     → disarms the gate when coding is complete
```

### Check whether paths are currently allowed

Use `check_gate` to query whether a list of paths would pass the gate, and `status` to report state and detect tampering — useful before starting an edit session.

### Publish an approved doc to Nexus (optional)

Add to `.arbiter/config.yaml`:

```yaml
nexus:
  url: "https://your-nexus-instance/ingest"
```

Then call `publish`. Without this config it returns `{"published": false, "reason": "nexus not configured"}`.

## Reference

- Source: [`arbiter/` in the Khala monorepo](https://github.com/LivingLikeKrillin/khala/tree/master/arbiter) (`README.md`; roadmap in `BACKLOG.md`).
- Ten MCP tools: `record`, `critique`, `approve`, `status`, `supersede`, `begin_implementation`, `end_implementation`, `check_gate`, `index`, `publish`.
- MVP boundaries: the `Bash` tool is *not* gated (only `Write`/`Edit`/`MultiEdit`); single-approver flow; no database.

:::note[Last verified]
Source repo README (site re-run verification pending).
:::
