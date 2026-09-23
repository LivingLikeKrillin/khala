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

import datetime as _dt
from dataclasses import dataclass, field

import yaml

from nexus.claims.repository import ClaimRepository
from nexus.index.code_source import CodeValueResolver
from nexus.models.claim import RULING_FIELDS, Claim


@dataclass
class SeedReport:
    """적재 결과. `total` 만 보고하면 안 붙은 것이 숨는다."""

    total: int = 0
    #: 값이 코드에 붙은 claim 수.
    bound: int = 0
    #: (claim_id, 왜 못 붙었나). 해석기의 이유를 그대로 옮긴다 — "심볼이 없다"와
    #: "모호하다"와 "코드 경로가 없다"는 처방이 전부 다르다.
    unbound: list[tuple[str, str]] = field(default_factory=list)
    #: 소유자 판정이 붙은 claim 수.
    rulings: int = 0
    #: 코드 값을 가리키지 않고 판정만 있는 claim. 「안 붙음」이 아니다 — 해석기가 못 읽는
    #: 모양(`if (count > 49)`)에도 판정은 있다. 따로 세지 않으면 unbound 로 오독한다.
    ruling_only: list[str] = field(default_factory=list)

    def __int__(self) -> int:          # 옛 호출부 호환 (`n = await seed_claims(...)`)
        return self.total


def _normalize_ruling(it: dict) -> None:
    """YAML 은 날짜를 date 로, 값을 int 로 읽어 온다 — 저장 칸은 TEXT 다. 그리고 판정에는
    **누가·언제** 가 반드시 있어야 한다. 없으면 판정이 아니라 메모이고, 조용히 들어가면
    「누가 언제 정했나」를 영영 못 묻는다."""
    present = [f for f in RULING_FIELDS if it.get(f) is not None]
    if not present:
        return
    for f in ("ruled_by", "ruled_on"):
        if not it.get(f):
            raise ValueError(
                f"claim {it.get('claim_id')}: 판정({', '.join(present)})에는 {f} 가 필수다 "
                "— 소유자와 날짜 없는 판정은 판정이 아니다")
    for f in RULING_FIELDS:
        v = it.get(f)
        if isinstance(v, (_dt.date, _dt.datetime)):
            it[f] = v.isoformat()
        elif v is not None and not isinstance(v, str):
            it[f] = str(v)


async def seed_claims(yaml_path: str, repo: ClaimRepository, resolver: CodeValueResolver):
    with open(yaml_path, encoding="utf-8") as f:
        items = yaml.safe_load(f) or []
    report = SeedReport()
    for it in items:
        if not it.get("owner") or it["owner"] == "unknown":
            raise ValueError(f"claim {it.get('claim_id')}: owner 필수(비-unknown)")  # 소유권=생존변수
        _normalize_ruling(it)
        c = Claim(**it)
        if c.has_ruling:
            report.rulings += 1
            if not c.value_source:
                report.ruling_only.append(c.claim_id)
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
