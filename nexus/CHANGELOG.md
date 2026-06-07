# Changelog

All notable changes to **nexus** will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Breaking Changes

- **Package rename:** Python package `khala` → `nexus`. All imports change from `from khala.*` to `from nexus.*`.
- **CLI entry point:** `khala` command → `nexus` (pyproject `[project.scripts]` entry `nexus = "nexus.cli:app"`). Scripts and shell aliases invoking `khala` must be updated.
- **MCP tool names:** The six knowledge-base MCP tools are renamed:
  - `khala_search` → `nexus_search`
  - `khala_answer` → `nexus_answer`
  - `khala_graph` → `nexus_graph`
  - `khala_suggest` → `nexus_suggest`
  - `khala_diff` → `nexus_diff`
  - `khala_status` → `nexus_status`

  Any MCP client configuration referencing the old `khala_*` names must be updated.

  **Note:** The `archon_claim_value` and `archon_grade_authority` MCP tools are **unchanged**.

- **pyproject name:** `name = "khala"` → `name = "nexus"`.
- **Database credentials:** All DB/container identifiers renamed:
  - Database name: `khala` → `nexus`
  - DB user: `khala` → `nexus`
  - Container name: `khala-db` → `nexus-db`
  - `DATABASE_URL`: `postgresql://khala:khala@khala-db:5432/khala` → `postgresql://nexus:nexus@nexus-db:5432/nexus`

  Update `.env` files and any external tooling (pgAdmin, Grafana data sources, etc.) referencing the old credentials.
