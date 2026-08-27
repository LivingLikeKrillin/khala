"""그림 판독이 **장부에 오르는가**.

2026-08-25 재적재는 판독 39건을 공급자로 보내고 "지출 0" 으로 보고됐다. 거짓말을 한 것이 아니라
**세는 곳이 없었다** — `dev_spend` 를 부르는 곳은 평가 스크립트 둘뿐이었고 적재 경로는 아니었다.

여기서 측정하는 것은 대부분 **세어져야 하는데 안 세어지던 입력**이다.
"""

from __future__ import annotations

import asyncio

from nexus.ingest import vision
from nexus.llm.dev_spend import Spend
from nexus.providers.llm import Usage


class _Reader:
    """`vision_extract(..., usage_out)` 계약만 흉내 내는 더블."""

    def __init__(self, usage=None, boom=False):
        self.usage, self.boom, self.calls = usage, boom, 0

    async def vision_extract(self, system, image_b64, media_type, max_tokens, usage_out=None):
        self.calls += 1
        if usage_out is not None and self.usage is not None:
            usage_out.append(self.usage)
        if self.boom:
            raise RuntimeError("공급자 500")
        return "표에 적힌 값", None


def _read(reader, sink):
    return asyncio.run(vision.read_image(b"\x89PNG...", "image/png", reader, usage_out=sink))


def test_a_successful_read_puts_one_row_in_the_ledger():
    sink: list = []
    _read(_Reader(Usage(1200, 300, 0.0045, "vision-model")), sink)
    assert len(sink) == 1 and sink[0].cost_usd == 0.0045


def test_a_failed_read_is_still_a_call():
    """**가장 중요한 대조군.** 실패를 안 세면 '몇 장을 보냈나' 를 아무도 못 센다 —
    그리고 그 수가 틀린 것이 2026-08-25 보고의 결함이었다."""
    sink: list = []
    e = _read(_Reader(usage=None, boom=True), sink)
    assert e.error and not e.ok
    assert len(sink) == 1 and sink[0] is None


def test_one_row_per_call_even_when_the_sink_is_reused():
    """같은 리스트를 여러 장에 걸쳐 쓰는 것이 실제 호출 방식이다 — 줄 수가 장수여야 한다."""
    sink: list = []
    ok, bad = _Reader(Usage(10, 5, 0.001, "m")), _Reader(usage=None, boom=True)
    _read(ok, sink)
    _read(bad, sink)
    _read(ok, sink)
    assert len(sink) == 3
    assert spend_of(sink).calls == 3


def spend_of(rows) -> Spend:
    s = Spend()
    for r in rows:
        s.add(r, kind="vision")
    return s


def test_the_ledger_separates_unknown_price_from_free():
    """브리지는 토큰을 안 준다 → `usd` 가 0 이다. 그 0 은 '공짜' 가 아니라 **'모른다'** 이고,
    `priced` 가 그 구분을 들고 간다. 섞이면 유료 실행이 공짜로 보고된다."""
    unknown = spend_of([Usage(None, None, None, "bridge"), None])
    assert (unknown.calls, unknown.priced, unknown.usd) == (2, 0, 0.0)
    assert "가격 정보 없음" in unknown.summary()

    paid = spend_of([Usage(1000, 200, 0.01, "m")])
    assert (paid.calls, paid.priced) == (1, 1) and paid.usd == 0.01
    assert "$0.0100" in paid.summary()


def test_a_reader_that_ignores_usage_out_still_counts_the_call():
    """옛 백엔드(토큰을 안 실어 주는 것)도 호출 수는 잃지 않는다."""
    sink: list = []
    _read(_Reader(usage=None), sink)
    assert sink == [None] and spend_of(sink).calls == 1


# ── 배선: 장부가 실제 경로에서 채워지는가 ────────────────────────────────────
#
# 단위 검사만으로는 부족하다는 것이 이 리포의 반복된 경험이다 — 배선이 끊긴 채로 초록인 검사가
# 여러 번 있었다. 그래서 `apply` 를 통째로 돌린다.

from nexus.ingest import vision_store  # noqa: E402
from nexus.ingest.sources.notion_convert import image_slot  # noqa: E402


class _StoreReader:
    model = "test-vision"

    def __init__(self, usage):
        self.usage, self.calls = usage, 0

    async def vision_extract(self, system, image_b64, media_type, max_tokens, usage_out=None):
        self.calls += 1
        if usage_out is not None:
            usage_out.append(self.usage)
        return "표에서 읽은 값", "end_turn"


async def _none(*a, **k):
    return None


def _apply(monkeypatch, spend, *, cached=False):
    async def _fetch(url):
        return b"\x89PNG", "image/png"

    async def _echo(t, e):
        return {"text": e.text, "truncated": e.truncated}

    monkeypatch.setattr(vision_store, "_fetch_bytes", _fetch)
    monkeypatch.setattr(vision_store, "save", _echo)
    monkeypatch.setattr(vision_store, "fill_reference", lambda *a, **k: _none())
    monkeypatch.setattr(
        vision_store, "load",
        (lambda *a, **k: _echo(None, vision.Extraction("이미 읽음", "id", "sha")))
        if cached else (lambda *a, **k: _none()))
    reader = _StoreReader(Usage(900, 120, None, "test-vision"))
    md = f"앞\n\n{image_slot('blk-1')}\n\n뒤\n"
    asyncio.run(vision_store.apply(
        md, [{"block_id": "blk-1", "url": "u", "caption": ""}],
        tenant="t", llm_svc=reader, spend=spend))
    return reader


def test_the_ledger_is_filled_through_the_real_path(monkeypatch):
    spend = Spend()
    reader = _apply(monkeypatch, spend)
    assert reader.calls == 1
    assert spend.calls == 1 and spend.by_kind == {"vision": 1}


def test_a_cache_hit_is_not_a_call(monkeypatch):
    """이미 읽은 바이트는 공급자로 나가지 않는다 — 장부에 오르면 지출이 부풀려진다."""
    spend = Spend()
    reader = _apply(monkeypatch, spend, cached=True)
    assert reader.calls == 0 and spend.calls == 0


def test_without_a_ledger_the_reader_contract_is_unchanged(monkeypatch):
    """`spend` 를 안 주면 `usage_out` 을 **아예 넘기지 않는다.** 늘 넘기면 그 인자를 모르는
    판독기가 TypeError 를 내고, 그 예외는 판독 실패로 삼켜져 **조용히 그림이 안 읽힌다.**"""
    seen = {}

    class _Old:
        async def vision_extract(self, system, image_b64, media_type, max_tokens):
            seen["called"] = True
            return "옛 계약", None

    sink_free = asyncio.run(vision.read_image(b"\x89PNG", "image/png", _Old()))
    assert seen.get("called") and sink_free.ok and not sink_free.error
