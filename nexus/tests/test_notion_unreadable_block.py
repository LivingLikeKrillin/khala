"""읽지 못한 하위 블록은 **구멍**이지 문서의 죽음이 아니다 — 그리고 `--dry-run` 은 쓰지 않는다.

**왜 이 파일이 있나 (2026-08-25 라이브 실측).** 조직 코퍼스에 정책 문서가 15건뿐이었는데, 그중
**4건이 빠진 이유가 각 페이지 안의 `synced_block` 하나**였다. 원본 블록이 이 integration 에
공유돼 있지 않아 Notion 이 404 를 내고, 그 예외가 변환기를 뚫고 올라가 `import_notion` 의
per-page `except` 에 잡혔다 — **블록 하나 때문에 페이지가 통째로 버려지고 `skipped` 숫자 뒤에
묻혔다.** 종료 코드는 0 이었다.

같은 자리에서 두 번째 함정도 드러났다: `--dry-run` 의 도움말은 *"DB 는 건드리지 않는다"* 인데
실제로는 **재조정 계획만** 말랐고 적재는 그대로 썼다. 계획을 보려던 사람이 라이브 코퍼스에
쓰게 된다.
"""

from __future__ import annotations

import pytest

from nexus.ingest.sources.base import ConvertedDoc
from nexus.ingest.sources.notion_convert import HOLE_NOTE, blocks_to_markdown
from nexus.ingest.sources.notion_importer import import_notion


def _para(bid: str, text: str) -> dict:
    return {"id": bid, "type": "paragraph",
            "paragraph": {"rich_text": [{"plain_text": text}]}}


def _synced(bid: str) -> dict:
    return {"id": bid, "type": "synced_block", "has_children": True,
            "synced_block": {"synced_from": {"type": "block_id", "block_id": "elsewhere"}}}


def _children_of(mapping: dict):
    """`children_of` 페이크. 매핑에 없는 id 는 Notion 의 404 처럼 **던진다**."""
    def _fn(bid: str) -> list[dict]:
        if bid not in mapping:
            raise RuntimeError(f"Could not find block with ID: {bid}")
        return mapping[bid]
    return _fn


# ── 변환기: 나머지 본문이 살아남는가 ────────────────────────────────────────────

def test_unreadable_child_leaves_a_hole_and_the_page_survives():
    """읽을 수 없는 `synced_block` 이 있어도 **앞뒤 문단이 남는다.**

    이것이 이 변경의 전부다: 예전에는 여기서 예외가 올라가 문서 전체가 사라졌다.
    """
    blocks = [_para("b1", "앞 문단"), _synced("b2"), _para("b3", "뒤 문단")]
    holes: list[dict] = []
    md, _ = blocks_to_markdown(blocks, _children_of({}), hole_sink=holes)

    assert "앞 문단" in md and "뒤 문단" in md
    assert HOLE_NOTE.format(kind="synced_block") in md
    assert [h["block_id"] for h in holes] == ["b2"]
    assert holes[0]["type"] == "synced_block"
    assert "Could not find block" in holes[0]["error"]


def test_readable_children_are_still_expanded():
    """대조군 — 읽히는 자식은 예전 그대로 펼쳐지고, 구멍은 하나도 안 생긴다.

    구멍 처리를 넣다가 정상 경로를 막으면 이 검사가 죽는다.
    """
    blocks = [_synced("b2")]
    holes: list[dict] = []
    md, _ = blocks_to_markdown(
        blocks, _children_of({"b2": [_para("c1", "동기화 블록 안의 규칙")]}), hole_sink=holes)

    assert "동기화 블록 안의 규칙" in md
    assert "읽지 못한 블록" not in md
    assert holes == []


def test_unreadable_table_becomes_a_hole_too():
    """표도 자식을 가지러 들어간다 — 같은 규율."""
    blocks = [{"id": "t1", "type": "table", "has_children": True, "table": {}}]
    holes: list[dict] = []
    md, _ = blocks_to_markdown(blocks, _children_of({}), hole_sink=holes)
    assert HOLE_NOTE.format(kind="표") in md
    assert [h["block_id"] for h in holes] == ["t1"]


def test_hole_note_carries_no_block_id():
    """본문 표식에 블록 id 를 넣지 않는다 — 그 텍스트는 코퍼스에 남는다.

    진단용 id 는 `hole_sink` 와 로그에만 있다. 여기 넣으면 Notion 식별자가 청크로 들어간다.
    """
    holes: list[dict] = []
    md, _ = blocks_to_markdown([_synced("bd41f1e2-dead-beef")], _children_of({}), hole_sink=holes)
    assert "bd41f1e2" not in md
    assert holes[0]["block_id"] == "bd41f1e2-dead-beef"


def test_hole_sink_is_optional():
    """sink 를 안 줘도 크래시하지 않는다(옛 호출부·테스트)."""
    md, _ = blocks_to_markdown([_synced("b2")], _children_of({}))
    assert HOLE_NOTE.format(kind="synced_block") in md


# ── importer: 부분 본문은 세어지고, dry-run 은 쓰지 않는다 ──────────────────────

def _conv(pid: str, holes: list | None = None) -> ConvertedDoc:
    return ConvertedDoc(page_id=pid, markdown="# 제목\n\n본문",
                        frontmatter={"title": f"문서 {pid}", "origin_url": f"u/{pid}"},
                        holes=holes or [])


class _FakeSource:
    def __init__(self, convs: dict):
        self._convs = convs

    def live_index(self):
        return {i: {"root"} for i in self._convs}

    def page_ref(self, pid):
        return type("R", (), {"id": pid, "url": f"u/{pid}", "last_edited": "t"})()

    def fetch_markdown(self, ref):
        return self._convs[ref.id]


class _Outcome:
    def __init__(self, rid):
        self.resource_rid, self.idempotent_hit = rid, False


@pytest.mark.asyncio
async def test_partial_body_is_ingested_and_counted():
    """구멍이 있어도 **적재된다** — 그리고 그 사실이 보고에 남는다.

    예전 동작은 `ingested=0, skipped=1` 이었다. 부분 본문이라도 있는 편이 낫지만, 조용히
    완전한 문서인 척하면 안 된다.
    """
    convs = {"a": _conv("a", holes=[{"block_id": "b2", "type": "synced_block", "error": "404"}])}
    seen = []

    async def fake_ingest(csf, tenant, *, force: bool = False):
        seen.append(csf["id"])
        return _Outcome("doc_a")

    report = await import_notion(_FakeSource(convs), "acme", fake_ingest)
    assert report.ingested == 1 and report.skipped == 0
    assert report.holes == 1
    assert seen == ["ext-notion-a"]


@pytest.mark.asyncio
async def test_dry_run_writes_nothing():
    """`--dry-run` 은 **ingest_fn 을 부르지 않는다.**

    이 단언 하나가 이 변경의 전부다: 예전에는 여기서 라이브 코퍼스에 썼다.
    """
    convs = {"a": _conv("a"), "b": _conv("b")}
    calls = []

    async def fake_ingest(csf, tenant, *, force: bool = False):
        calls.append(csf["id"])
        return _Outcome("doc_x")

    report = await import_notion(_FakeSource(convs), "acme", fake_ingest, dry_run=True)
    assert calls == []
    assert report.ingested == 0
    assert report.would_ingest == 2


@pytest.mark.asyncio
async def test_without_dry_run_it_still_writes():
    """대조군 — 기본 경로는 예전 그대로 적재한다."""
    convs = {"a": _conv("a")}
    calls = []

    async def fake_ingest(csf, tenant, *, force: bool = False):
        calls.append(csf["id"])
        return _Outcome("doc_a")

    report = await import_notion(_FakeSource(convs), "acme", fake_ingest)
    assert calls == ["ext-notion-a"]
    assert report.ingested == 1 and report.would_ingest == 0
