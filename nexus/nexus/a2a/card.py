"""Agent Card builder (SPEC §5.2).

Builds Nexus's A2A Agent Card from config. Grounding is declared **structurally** via the
official ``AgentExtension`` mechanism (an entry in ``capabilities.extensions``) plus skill
``tags`` — a consuming agent detects "evidence-bound, server-enforced clearance" by reading
the extension and a machine-readable ``evidenceSchemaRef``, not by parsing prose.

Shapes are bound to the pinned SDK (``a2a-sdk==1.1.0``); JSON-RPC spec types live in
``a2a.compat.v0_3.types``.
"""

from __future__ import annotations

from a2a.compat.v0_3.types import (
    AgentCapabilities,
    AgentCard,
    AgentExtension,
    AgentProvider,
    AgentSkill,
)

from nexus.a2a.config import A2AConfig

# Khala-owned identifier for the grounding extension (SPEC §5.2).
GROUNDING_EXTENSION_URI = "https://khala.dev/a2a/ext/grounding/v1"

# A2A JSON-RPC protocol version implemented by the pinned compat types.
_PROTOCOL_VERSION = "0.3.0"

_SKILL_ID = "retrieve_grounded"


def build_agent_card(cfg: A2AConfig) -> dict:
    """Return the spec-shaped (camelCase) Agent Card JSON for this Nexus instance."""
    base = cfg.base_url.rstrip("/")

    grounding = AgentExtension(
        uri=GROUNDING_EXTENSION_URI,
        description="Answers are evidence-bound; classification/clearance is enforced server-side.",
        required=False,
        params={
            "grounded": True,
            "evidenceBound": True,
            "clearanceModel": "server-enforced",
            "evidenceSchemaRef": f"{base}/a2a/schemas/evidence-packet.json",
        },
    )

    skill = AgentSkill(
        id=_SKILL_ID,
        name="Grounded knowledge retrieval",
        description=(
            "Answer a question from indexed org knowledge; returns answer + evidence + "
            "provenance + confidence. Never asserts ungrounded claims."
        ),
        tags=[
            "rag", "graphrag", "grounded", "evidence-bound",
            "server-enforced-clearance", "korean",
        ],
        examples=["결제 서비스가 발행하는 토픽이 뭐야?"],
        input_modes=["text/plain"],
        output_modes=["text/plain", "application/json"],
    )

    card = AgentCard(
        name="Nexus",
        description=(
            "Grounded knowledge retrieval over org docs + OTel telemetry. "
            "Returns evidence-bound answers only."
        ),
        url=f"{base}/a2a",
        version="0.1.0-spike",
        protocol_version=_PROTOCOL_VERSION,
        preferred_transport="JSONRPC",
        provider=AgentProvider(organization="Khala", url="https://khala.dev"),
        capabilities=AgentCapabilities(
            streaming=False,
            push_notifications=False,
            extensions=[grounding],
        ),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain", "application/json"],
        skills=[skill],
    )
    return card.model_dump(mode="json", by_alias=True, exclude_none=True)
