from pathlib import Path

import pytest

from khala.claims.value_query import ValueQueryService
from khala.index.code_source import CodeValueResolver
from khala.models.claim import Claim

FIX = Path(__file__).parent / "fixtures"


class FakeRepo:
    def __init__(self, claims):
        self._c = claims

    async def find_by_concept(self, concept, tenant, clearance):
        return [c for c in self._c if concept in c.concepts]


def _claim(**kw):
    base = dict(
        claim_id="associate-max-playlists",
        kind="invariant",
        concepts=["준회원"],
        statement="준회원 최대 N개",
        value_source="PlaylistPolicy.ASSOCIATE_MAX_PLAYLISTS",
        value_ref_kind="code_constant",
        owner="@be",
    )
    base.update(kw)
    return Claim(**base)


@pytest.mark.asyncio
async def test_live_value_high_confidence_fresh():
    svc = ValueQueryService(FakeRepo([_claim()]), CodeValueResolver(FIX))
    res = await svc.query_value("준회원", "default", "INTERNAL")
    assert res[0].value == "5" and res[0].confidence == "high" and res[0].fresh is True


@pytest.mark.asyncio
async def test_drift_noted_when_stored_hash_differs():
    svc = ValueQueryService(FakeRepo([_claim(value_symbol_hash="OLD")]), CodeValueResolver(FIX))
    res = await svc.query_value("준회원", "default", "INTERNAL")
    assert res[0].value == "5"  # 값 자체는 항상 현재값(결정론)
    assert res[0].drifted is True
    assert "변경" in res[0].note


@pytest.mark.asyncio
async def test_missing_source_is_honest():
    svc = ValueQueryService(FakeRepo([_claim(value_source="Foo.BAR")]), CodeValueResolver(FIX))
    res = await svc.query_value("준회원", "default", "INTERNAL")
    assert res[0].value is None and res[0].confidence == "low"
