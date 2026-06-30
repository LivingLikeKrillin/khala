"""Nexus A2A (Agent2Agent) Phase 0 spike — grounded-retrieval server.

A flag-gated, additive A2A surface that lets an external A2A agent discover Nexus,
delegate a query, and receive Nexus's full grounded answer (answer + evidence +
provenance + confidence) over A2A — with classification/clearance enforced server-side.

Off by default (``NEXUS_A2A_ENABLED`` unset/false ⇒ no routes, no overhead). Reversal =
delete this package + the conditional mount in ``api.py``. See
specs/SPEC-nexus-a2a-server-phase0-spike.md and adr/ADR-0001.
"""
