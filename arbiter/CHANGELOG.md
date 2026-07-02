# Changelog

All notable changes to **arbiter** will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Breaking Changes

- **Public class renames:** The two public sink types in `specledger.publish` are renamed:
  - `KhalaSink` (Protocol) → `NexusSink`
  - `KhalaHttpSink` → `NexusHttpSink`

  Any code implementing or instantiating these types must be updated. Type annotations using `KhalaSink` in function signatures are now invalid.

- **Config key:** The publish-config dictionary key `khala` → `nexus`. Callers passing a `config` object must rename the key (e.g., `{"khala": {"url": ...}}` → `{"nexus": {"url": ...}}`).

- **Error string:** The not-configured sentinel reason changed from `"khala not configured"` to `"nexus not configured"`. Code matching on this string (e.g., `result["reason"] == "khala not configured"`) must be updated.

- **Transport — `NexusHttpSink` removed; A2A is the sole transport.** The bespoke point-to-point HTTP POST sink is gone. `publish()` always builds an `A2ANexusSink` (A2A JSON-RPC: discover agent card → `ingest_governed_doc` skill → governed-doc DataPart with a write token). The `SPECLEDGER_NEXUS_TRANSPORT` env flag and the `nexus["transport"]` config key are no longer consulted. The publish-config needs a Nexus base URL (`nexus["url"]` or `nexus["base_url"]`) and a write-capability token (`SPECLEDGER_NEXUS_TOKEN` env or `nexus["token"]`). Done once the A2A provenance loop was proven end to end against a real DB (SPEC-specledger-a2a-publish-phase3 §16).
