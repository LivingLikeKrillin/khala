# Changelog

All notable changes to **probe** will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Breaking Changes

- **CLI subcommands:** Nexus-targeting subcommands renamed to reflect the backend rename:
  - `probe khala:search` → `probe nexus:search`
  - `probe khala:impact` → `probe nexus:impact`
  - `probe khala:status` → `probe nexus:status`

  Shell scripts, CI pipelines, and keybindings invoking the old `khala:*` subcommands must be updated.

- **Environment variables:** All `KHALA_*` env vars renamed:
  - `KHALA_BASE_URL` → `NEXUS_BASE_URL`
  - `KHALA_TIMEOUT_MS` → `NEXUS_TIMEOUT_MS`
  - `KHALA_TENANT` → `NEXUS_TENANT`
  - `KHALA_DISABLED` → `NEXUS_DISABLED`

  Update `.env` files, CI secret stores, and deployment manifests accordingly.

- **Config key:** Top-level config key `khala.baseUrl` (and sibling keys `khala.timeoutMs`, `khala.tenant`, `khala.disabled`) renamed to `nexus.*` in project config files (e.g., `probe.config.json`).

- **MCP tool name:** `probe.queryKhala` → `probe.queryNexus`. Update any MCP client configurations or agent instructions that reference the old tool name.

- **Internal source path:** Client module `src/khala/` → `src/nexus/`. This is an internal detail; it surfaces in stack traces and any direct imports by tests or extensions.
