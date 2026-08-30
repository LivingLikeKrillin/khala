"""claims.yaml 시드 로더.

seed 시점에 value_source를 resolve해 현재 코드 hash를 스냅샷한다(이후 드리프트 판정 기준).
owner 비-unknown 강제(소유권=생존변수).

⚠ **못 붙은 것을 말한다 (2026-08-30).** 옛 판은 `{n}건 적재` 만 찍었다. 그런데 claim 이
코드에 **안 붙는** 경우는 흔하고(심볼 오타 · 한정자 누락 · 마운트 빠짐 · 값이 코드에 없음),
그때도 행은 들어간다 — 값 없이. 그래서 11건을 심고 4건이 조용히 죽어도 화면은 `11건 적재`
였다. 이 리포가 반복해서 데인 모양이라(쓰기만 있고 읽기가 없다) 시드가 **무엇이 안 붙었고
왜인지**를 같이 낸다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from nexus.claims.repository import ClaimRepository
from nexus.index.code_source import CodeValueResolver
from nexus.models.claim import Claim


@dataclass
class SeedReport:
    """적재 결과. `total` 만 보고하면 안 붙은 것이 숨는다."""

    total: int = 0
    #: 값이 코드에 붙은 claim 수.
    bound: int = 0
    #: (claim_id, 왜 못 붙었나). 해석기의 이유를 그대로 옮긴다 — "심볼이 없다"와
    #: "모호하다"와 "코드 경로가 없다"는 처방이 전부 다르다.
    unbound: list[tuple[str, str]] = field(default_factory=list)

    def __int__(self) -> int:          # 옛 호출부 호환 (`n = await seed_claims(...)`)
        return self.total


async def seed_claims(yaml_path: str, repo: ClaimRepository, resolver: CodeValueResolver):
    with open(yaml_path, encoding="utf-8") as f:
        items = yaml.safe_load(f) or []
    report = SeedReport()
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
                report.bound += 1
            else:
                report.unbound.append(
                    (c.claim_id, r.reason or "코드에서 값을 찾지 못했다"))
        await repo.upsert(c)
        report.total += 1
    return report
