"""문서-타입 정본 레지스트리 reader (S1).

document_types.yaml 을 로드·검증하고, 다운스트림이 정책 데이터를 직접 읽지 않도록
조회 API(tier_of/lifecycle_of/normalize_kind/specledger_type_of/is_promotable)만 노출한다.
tier(T1/T2/T3) ↔ lifecycle(governed/tracked/memo) 1:1 불변식을 여기서 강제한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

# tier ↔ lifecycle 1:1 불변식(정본). 레지스트리는 tier 만 선언하고 lifecycle 은 유도된다.
LIFECYCLE_BY_TIER = {"T1": "governed", "T2": "tracked", "T3": "memo"}


class RegistryError(ValueError):
    """레지스트리 데이터가 스키마를 위반할 때."""


@dataclass(frozen=True)
class DocType:
    name: str
    tier: str
    immutable: bool
    owner_required: bool
    specledger_type: str | None = None  # T1 만 보유


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, DocType], str, dict[str, str]]:
    raw = yaml.safe_load(Path(__file__).with_name("document_types.yaml").read_text("utf-8"))
    default_tier = raw.get("default_tier", "T3")
    if default_tier not in LIFECYCLE_BY_TIER:
        raise RegistryError(f"default_tier 가 알 수 없는 tier: {default_tier!r}")
    types: dict[str, DocType] = {}
    for name, spec in (raw.get("types") or {}).items():
        tier = spec.get("tier")
        if tier not in LIFECYCLE_BY_TIER:
            raise RegistryError(f"{name}: 알 수 없는 tier {tier!r}")
        st = spec.get("specledger_type")
        # 불변식: specledger_type 은 T1 에만, T1 은 반드시 보유.
        if (tier == "T1") != bool(st):
            raise RegistryError(f"{name}: specledger_type 은 T1 에만 존재해야 한다")
        types[name] = DocType(
            name=name, tier=tier,
            immutable=bool(spec.get("immutable", False)),
            owner_required=bool(spec.get("owner_required", False)),
            specledger_type=st,
        )
    aliases = {str(k): str(v) for k, v in (raw.get("aliases") or {}).items()}
    return types, default_tier, aliases


def load_registry() -> dict[str, DocType]:
    return _load()[0]


def tier_of(type_name: str) -> str:
    """알려진 타입→tier, 미지 타입→default_tier(보수적 강등)."""
    types, default_tier, _ = _load()
    dt = types.get(type_name)
    return dt.tier if dt else default_tier


def lifecycle_of(type_name: str) -> str:
    return LIFECYCLE_BY_TIER[tier_of(type_name)]


def normalize_kind(csf_kind: str) -> str:
    """레거시 CSF kind → 축-A 정본 타입. alias 없으면 그대로(상류 1회 정규화)."""
    _, _, aliases = _load()
    return aliases.get(csf_kind, csf_kind)


def specledger_type_of(type_name: str) -> str | None:
    """축-A 타입 → specledger 어휘(spec/adr). 비-T1 이면 None."""
    return _load()[0].get(type_name, DocType(type_name, "T3", False, False)).specledger_type


def is_promotable(type_name: str) -> bool:
    """거버넌스(T1)로 승격 가능한가 = specledger_type 보유."""
    return specledger_type_of(type_name) is not None
