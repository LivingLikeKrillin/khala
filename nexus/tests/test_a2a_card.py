"""Agent Card discovery (SPEC §5.2, §7).

The card must validate against the pinned A2A card schema, advertise the
``retrieve_grounded`` skill, and declare grounding *structurally* via the official
``AgentExtension`` mechanism — not as ad-hoc prose.
"""

from __future__ import annotations

import a2a.compat.v0_3.types as a2a_types

from nexus.a2a.card import GROUNDING_EXTENSION_URI, build_agent_card
from nexus.a2a.config import A2AConfig


def _card() -> dict:
    cfg = A2AConfig(enabled=True, base_url="https://nexus.example.com")
    return build_agent_card(cfg)


def test_card_validates_against_pinned_a2a_schema():
    parsed = a2a_types.AgentCard.model_validate(_card())
    assert parsed.name == "Nexus"


def test_card_lists_retrieve_grounded_skill():
    card = _card()
    skill_ids = [s["id"] for s in card["skills"]]
    assert "retrieve_grounded" in skill_ids


def test_card_lists_ingest_governed_doc_write_skill():
    card = _card()
    skills = {s["id"]: s for s in card["skills"]}
    assert "ingest_governed_doc" in skills
    # the write skill is tagged so a consumer can tell it apart from the read skill
    assert "write" in skills["ingest_governed_doc"]["tags"]
    assert "governed" in skills["ingest_governed_doc"]["tags"]


def test_card_declares_grounding_via_official_extension():
    card = _card()
    ext_uris = [e["uri"] for e in card["capabilities"]["extensions"]]
    assert GROUNDING_EXTENSION_URI in ext_uris
    grounding = next(
        e for e in card["capabilities"]["extensions"] if e["uri"] == GROUNDING_EXTENSION_URI
    )
    # machine-readable grounding declaration, not prose
    assert grounding["params"]["grounded"] is True
    assert grounding["params"]["evidenceBound"] is True
    assert grounding["params"]["clearanceModel"] == "server-enforced"


def test_skill_tags_advertise_evidence_bound_clearance():
    skill = next(s for s in _card()["skills"] if s["id"] == "retrieve_grounded")
    assert "grounded" in skill["tags"]
    assert "evidence-bound" in skill["tags"]
    assert "server-enforced-clearance" in skill["tags"]


def test_card_url_and_modes_reflect_config():
    card = _card()
    assert card["url"] == "https://nexus.example.com/a2a"
    assert "application/json" in card["defaultOutputModes"]
    assert card["capabilities"]["streaming"] is False


def test_phase0_declares_no_streaming_or_push():
    caps = _card()["capabilities"]
    assert caps["streaming"] is False
    assert caps["pushNotifications"] is False
