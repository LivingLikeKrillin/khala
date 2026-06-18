# Specledger

Specledger is a Python MCP server and Claude Code `PreToolUse` hook that records AI-generated ADRs and design specs in a consistent Markdown+frontmatter format, enforces accountable review (AI critique → human issue-disposition → sign-off) before any code edits are written, and optionally publishes approved documents to an external Nexus sink. The gate is active during implementation: `begin_implementation` arms it, `end_implementation` disarms it. Until a spec is approved and stamped with a content hash, all `Write`/`Edit`/`MultiEdit` calls targeting non-exempt source paths are blocked.

---

## Install

```bash
pip install -e ".[dev]"
```

---

## MCP Server Registration (`.mcp.json`)

Add to your project's `.mcp.json` (or the global `~/.claude/mcp.json`):

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

`SPECLEDGER_ROOT` — project root where `.specledger/` state lives (defaults to `.`).
`SPECLEDGER_DOCS` — directory where spec and ADR Markdown files are written (defaults to `$SPECLEDGER_ROOT/docs`).
`ANTHROPIC_API_KEY` — required only when using the built-in `AnthropicCritic` (the `critique` tool).

---

## PreToolUse Hook Registration (`settings.json`)

Register the gate hook in `.claude/settings.json` (project-level) or `~/.claude/settings.json` (global):

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

The hook reads the tool payload from stdin and exits `0` (allow) or `2` (block). It respects the same `SPECLEDGER_ROOT` / `SPECLEDGER_DOCS` environment variables.

> **MVP note:** The `Bash` tool is not intercepted — only the first-class file-edit tools (`Write`, `Edit`, `MultiEdit`) are gated.

---

## Exposed MCP Tools (10 total)

| Tool | Purpose |
|---|---|
| `record` | Create a new spec or ADR |
| `critique` | Run AI critique → open issues in sidecar |
| `approve` | Disposition issues + sign off → stamp content hash |
| `status` | Report status (and detect tampering) |
| `supersede` | Mark one ADR superseded by another |
| `begin_implementation` | Arm the gate for a specific spec |
| `end_implementation` | Disarm the gate |
| `check_gate` | Query whether a list of paths is currently allowed |
| `index` | Regenerate `INDEX.md` |
| `publish` | Push an approved doc to the Nexus sink (no-op if not configured) |

---

## Quickstart: First Consumer (Engception)

```
1. record       → Claude calls `record("spec", "Playlist Self-Update")`
                  Returns a spec ID, e.g. "SPEC-playlist-self-update"

2. critique     → Claude calls `critique("SPEC-playlist-self-update")`
                  AI reviews the body and opens issues (e.g. I-001: missing-invariant)

3. fix + disposition
                → Human edits the spec body to address each issue.
                  Then calls `approve` with dispositions:
                  [{"issue_id": "I-001", "disposition": "accepted"}]

4. approve      → Claude calls `approve("SPEC-playlist-self-update", dispositions, "eisen")`
                  Verifies body was modified, stamps content hash, sets status=approved.

5. begin_implementation
                → Claude calls `begin_implementation("SPEC-playlist-self-update")`
                  Arms the gate. Subsequent Write/Edit calls on src/ paths are now allowed.

6. end_implementation
                → Claude calls `end_implementation()` when coding is complete.
```

---

## Nexus Integration (optional)

`publish` delivers an approved doc to Nexus over **A2A** (the `ingest_governed_doc` skill), with
the doc's content hash riding along as provenance. Add to `.specledger/config.yaml`:

```yaml
nexus:
  url: "https://your-nexus-instance"   # Nexus base URL (A2A card is discovered under it)
  token: "<write-capability token>"     # or set SPECLEDGER_NEXUS_TOKEN
```

Then call the `publish` tool. Ingest is **capability-gated** server-side: the token must carry
Nexus's `ingest_governed` write capability — a read-only token is denied. A denied/failed task
maps gracefully to `{"published": false, "reason": ...}`. Without any config, `publish` is a safe
no-op returning `{"published": false, "reason": "nexus not configured"}`.

> The bespoke HTTP sink was retired; A2A is the sole transport (SPEC-specledger-a2a-publish-phase3 §16).

---

## MVP Boundaries

- **Path-agnostic gate:** paths are normalized relative to `SPECLEDGER_ROOT`; no project-structure assumptions beyond the `docs/**` and `tests/**` allow-globs (configurable via `allow_globs` in config).
- **Bash not gated:** only `Write`, `Edit`, and `MultiEdit` tools are intercepted by the PreToolUse hook.
- **Solo-user:** the approve flow is designed for a single human approver; no multi-reviewer workflow is implemented.
- **No database:** all state lives in Markdown files under `SPECLEDGER_DOCS` and a small `.specledger/` JSON marker in `SPECLEDGER_ROOT`.
