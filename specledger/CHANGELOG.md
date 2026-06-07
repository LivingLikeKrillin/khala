# Changelog

All notable changes to **specledger** will be documented in this file.

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
