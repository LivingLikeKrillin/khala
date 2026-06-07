"""ValueQueryService — concept → 매칭 claim의 현재값을 코드에서 재읽기.

값 조회는 결정론(코드 상수) → confidence=high, 조회 시 재읽기 → fresh.
저장 hash와 현재 hash가 다르면 drifted 표기(값 자체는 현재값으로 정확).
소스 해석 실패 → 정직 표기(거짓말 금지 = 캘리브레이션).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValueAnswer:
    claim_id: str
    statement: str
    value: str | None
    source: str | None
    confidence: str
    fresh: bool
    drifted: bool = False
    note: str = ""


class ValueQueryService:
    def __init__(self, repo, resolver):
        self.repo = repo
        self.resolver = resolver

    async def query_value(self, concept, tenant, clearance) -> list[ValueAnswer]:
        out: list[ValueAnswer] = []
        for c in await self.repo.find_by_concept(concept, tenant, clearance):
            if not c.value_source:
                out.append(
                    ValueAnswer(c.claim_id, c.statement, None, None,
                                c.confidence, False, note="value-bearing 아님")
                )
                continue
            r = self.resolver.resolve(c.value_source)
            if not r.found:
                out.append(
                    ValueAnswer(c.claim_id, c.statement, None, c.value_source,
                                "low", False, note="소스 심볼을 코드에서 찾지 못함")
                )
                continue
            drifted = bool(c.value_symbol_hash) and c.value_symbol_hash != r.symbol_hash
            note = "마지막 검증 이후 코드 변경됨(현재값은 정확)" if drifted else ""
            out.append(
                ValueAnswer(c.claim_id, c.statement, r.value, c.value_source,
                            "high", True, drifted=drifted, note=note)
            )
        return out
