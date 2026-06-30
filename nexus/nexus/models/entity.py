"""Entity 도메인 모델."""

from __future__ import annotations

from dataclasses import dataclass, field

from nexus.models.resource import NexusResource


@dataclass
class Entity(NexusResource):
    """시스템 내 식별 가능한 객체 (Service, Topic 등)."""

    entity_type: str = ""
    name: str = ""
    aliases: list[str] = field(default_factory=list)
    description: str = ""

    def __post_init__(self) -> None:
        self.rtype = "entity"
