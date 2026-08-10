"""커버리지가 **읽히는 자리에** 나오는가 — SPEC-nexus-index-completeness §6-4~§6-7.

§3.1 이 무엇을 세는지는 `test_index_coverage_db.py` 가 본다. 여기서 보는 것은 그 수가 사람과
스케줄러에게 **도달하는가**이고, 특히 §2.5 의 결론이다: 적재 프로세스가 죽어도 답이 나와야 한다.
"""

from __future__ import annotations

import pytest

from nexus.index.embed_health import exempt_tenants, log_embedding_coverage


class _Recorder:
    """structlog 대신 부르는 것을 그대로 받아 적는다. 로그 문자열이 아니라 **사건**을 단언한다."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    def _make(self, level: str):
        def _fn(event: str, **kw) -> None:
            self.events.append((level, event, kw))
        return _fn

    def __getattr__(self, name: str):
        return self._make(name)

    def names(self) -> list[str]:
        return [e for _, e, _ in self.events]


def test_exemption_is_declared_never_inferred():
    """§3.3 — 이름이나 0 커버리지로 추론하지 않는다. 선언만 면제다."""
    assert exempt_tenants({"index": {"coverage_exempt_tenants": ["ko_eval_arm"]}}) == {"ko_eval_arm"}
    assert exempt_tenants({}) == set()
    assert exempt_tenants(None) == set()
    # 이름이 아무리 평가 팩처럼 생겨도 선언 없이는 면제가 아니다
    assert "ko_eval_packb" not in exempt_tenants({"index": {"coverage_exempt_tenants": []}})


@pytest.mark.parametrize("exempt,expected", [
    ([], ["embedding_column_empty"]),
    (["pinned"], ["embedding_coverage_exempt"]),
])
async def test_a_declared_tenant_is_quiet_and_an_undeclared_one_is_not(
        monkeypatch, exempt, expected):
    """§6-6 — 같은 상태(커버리지 0)가 선언 하나로 error 와 info 로 갈린다."""
    rec = _Recorder()
    monkeypatch.setattr("nexus.index.embed_health.logger", rec)
    monkeypatch.setattr(
        "nexus.index.embed_health.fetch_coverage_by_tenant",
        _fixed([{"tenant": "pinned", "active": 289, "embedding": 0, "embedding_1024": 0,
                 "bm25": 289, "gap_768": 289, "gap_1024": 289, "gap_bm25": 0}]))

    await log_embedding_coverage("embedding_1024",
                                 {"index": {"coverage_exempt_tenants": exempt}})
    assert rec.names() == expected
    levels = {lvl for lvl, _, _ in rec.events}
    assert levels == ({"info"} if exempt else {"error"})


async def test_a_real_gap_still_fires_beside_exempt_tenants(monkeypatch):
    """§6-7·§2.3 — 면제가 진짜 신호까지 삼키면 이 SPEC 은 소음을 소음으로 바꾼 것뿐이다.

    2026-08-10 의 실제 모양이다: 면제 대상 둘이 error 를 뱉는 사이에 `pending=51` 이 끼어 있었다.
    """
    rec = _Recorder()
    monkeypatch.setattr("nexus.index.embed_health.logger", rec)
    monkeypatch.setattr(
        "nexus.index.embed_health.fetch_coverage_by_tenant",
        _fixed([
            {"tenant": "default", "active": 334, "embedding": 334, "embedding_1024": 283,
             "bm25": 334, "gap_768": 0, "gap_1024": 51, "gap_bm25": 0},
            {"tenant": "ko_eval_arm", "active": 289, "embedding": 0, "embedding_1024": 0,
             "bm25": 289, "gap_768": 289, "gap_1024": 289, "gap_bm25": 0},
            {"tenant": "ko_eval_packb", "active": 289, "embedding": 0, "embedding_1024": 0,
             "bm25": 289, "gap_768": 289, "gap_1024": 289, "gap_bm25": 0},
        ]))

    await log_embedding_coverage(
        "embedding_1024",
        {"index": {"coverage_exempt_tenants": ["ko_eval_arm", "ko_eval_packb"]}})

    warnings = [kw for lvl, ev, kw in rec.events if ev == "embedding_coverage_partial"]
    assert len(warnings) == 1 and warnings[0]["pending"] == 51
    assert "embedding_column_empty" not in rec.names(), "면제 테넌트가 error 를 뱉으면 안 된다"


def _fixed(rows):
    async def _fn():
        return rows
    return _fn
