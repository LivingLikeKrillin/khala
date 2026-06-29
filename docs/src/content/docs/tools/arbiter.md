---
title: Arbiter
description: Decision accountability — records AI-generated specs/ADRs and gates code edits behind accountable, signed-off review.
---

Arbiter (formerly specledger) makes the moment of judgment accountable instead of assumed. It is a Python MCP server plus a Claude Code `PreToolUse` hook: it records AI-generated ADRs and design specs in a consistent Markdown + frontmatter format and enforces accountable review — **AI critique → human issue-disposition → sign-off** — before any code edits are written, optionally publishing approved documents to a Nexus sink.

The problem it calibrates: when an assistant produces a confident spec, the path of least resistance is to approve it. Review degrades into ceremony — a green checkmark on text nobody truly read. Arbiter forces judgment to happen where it is cheap and where it leaves a trace. Until a spec is approved and stamped with a content hash, all `Write`/`Edit`/`MultiEdit` calls targeting non-exempt source paths are **blocked**. The gate is active during implementation: `begin_implementation` arms it, `end_implementation` disarms it.

One-line identity: a ledger that makes "who approved what, and why" a recorded, attributable act — so you cannot rubber-stamp your way past it.

<img
  src="/diagrams/specledger.svg"
  alt="Spec lifecycle: Recorded → Critiqued (issues) → Approved (content-hashed) → Implementing (gate armed, edits allowed) → Done. Write/Edit stays blocked until approval."
  style="max-width: 100%; height: auto; display: block; margin: 1.5rem auto;"
/>

## Core concepts

- **The gate.** Until a spec is `approved` and content-hash-stamped, file-edit tools on non-exempt paths are blocked. `docs/**` and `tests/**` are allow-globbed by default (configurable via `allow_globs`).
- **Arm / disarm.** `begin_implementation` arms the gate for a specific spec; `end_implementation` disarms it. The gate is only enforced during implementation.
- **Accountable review flow.** `critique` runs AI review and opens issues in a sidecar; the human edits the body to address each; `approve` takes per-issue dispositions, verifies the body actually changed, then stamps the content hash and sets `status=approved`.
- **Content-hash stamping + tamper detection.** Approval binds the spec to a hash; `status` reports state and detects tampering.
- **No database.** All state lives in Markdown files under `SPECLEDGER_DOCS` plus a small `.specledger/` marker under `SPECLEDGER_ROOT`.
- **Optional Nexus publish.** `publish` pushes an approved doc to a configured Nexus sink — a safe no-op when not configured.

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
    "specledger": {
      "command": "python",
      "args": ["-m", "specledger.server"],
      "env": {
        "SPECLEDGER_ROOT": "/abs/path/to/your/project",
        "SPECLEDGER_DOCS": "/abs/path/to/your/project/docs",
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

`SPECLEDGER_ROOT` is the project root where `.specledger/` state lives (defaults to `.`); `SPECLEDGER_DOCS` is where spec/ADR Markdown is written (defaults to `$SPECLEDGER_ROOT/docs`); `ANTHROPIC_API_KEY` is required only for the built-in `AnthropicCritic`.

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
            "command": "python /abs/path/specledger/hooks/pretooluse_gate.py"
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
4. approve                → approve(id, [{"issue_id":"I-001","disposition":"accepted"}], "eisen")
                             verifies body changed, stamps content hash, status=approved
5. begin_implementation   → arms the gate; Write/Edit on src/ paths now allowed
6. end_implementation     → disarms the gate when coding is complete
```

### Check whether paths are currently allowed

Use `check_gate` to query whether a list of paths would pass the gate, and `status` to report state and detect tampering — useful before starting an edit session.

### Publish an approved doc to Nexus (optional)

Add to `.specledger/config.yaml`:

```yaml
nexus:
  url: "https://your-nexus-instance/ingest"
```

Then call `publish`. Without this config it returns `{"published": false, "reason": "nexus not configured"}`.

## Reference

- Source repo README: [github.com/LivingLikeKrillin/specledger](https://github.com/LivingLikeKrillin/specledger) (`README.md`); roadmap in `BACKLOG.md`.
- Ten MCP tools: `record`, `critique`, `approve`, `status`, `supersede`, `begin_implementation`, `end_implementation`, `check_gate`, `index`, `publish`.
- MVP boundaries: the `Bash` tool is *not* gated (only `Write`/`Edit`/`MultiEdit`); single-approver flow; no database.

:::note[Last verified]
Source repo README (site re-run verification pending).
:::
