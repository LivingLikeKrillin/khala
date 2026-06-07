"""claims.yaml 시드 로더.

seed 시점에 value_source를 resolve해 현재 코드 hash를 스냅샷한다(이후 드리프트 판정 기준).
owner 비-unknown 강제(소유권=생존변수).
"""

from __future__ import annotations

import yaml

from nexus.claims.repository import ClaimRepository
from nexus.index.code_source import CodeValueResolver
from nexus.models.claim import Claim


async def seed_claims(yaml_path: str, repo: ClaimRepository, resolver: CodeValueResolver) -> int:
    with open(yaml_path, encoding="utf-8") as f:
        items = yaml.safe_load(f) or []
    n = 0
    for it in items:
        if not it.get("owner") or it["owner"] == "unknown":
            raise ValueError(f"claim {it.get('claim_id')}: owner 필수(비-unknown)")  # 소유권=생존변수
        c = Claim(**it)
        if c.value_source:
            r = resolver.resolve(c.value_source)
            if r.found:
                c.value_symbol_hash = r.symbol_hash
                c.source_uri = r.rel_path or ""
                c.hash = r.symbol_hash or ""
        await repo.upsert(c)
        n += 1
    return n
