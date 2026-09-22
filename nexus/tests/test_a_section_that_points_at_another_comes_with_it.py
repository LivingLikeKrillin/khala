"""가리키기만 하는 절이 **가리킨 절을 데리고 온다** — 같은 문서 안에서.

⛔ **왜 생겼나 (실측 2026-09-22, 설명 층 두 판).** SOP-03 §5 2항이 *"§4 의 세 조건을
확인한다"* 라고 **가리키기만** 한다. 조각내기가 §5 와 §4 를 갈라 놓으므로 조각 5 는 혼자
가고, 받는 쪽은 **조건 없는 포인터**를 받는다. 탐색 줄의 절차 절 인용이 **T0·T2 두 판 다
0/1** 이었다 — 채널을 켜도 안 왔다.

⚠ **문서를 고칠 일이 아니다.** 실제 절차서가 원래 그렇게 쓴다. 원문을 읽는 사람에게는
멀쩡한 문장이고, 깨지는 것은 **조각으로 나뉘는 순간**이다.

⭐ **범위를 측정으로 정했다.** 라이브에서 `§N` 이 660/2415 조각이고 `N절`·`N장` 은 합쳐
3건이다. § 참조 388건 중 **같은 문서 안에서 풀리는 것은 24건(6%)** — 나머지는 다른 문서의
절을 가리킨다. 그쪽은 **안 한다.** 이 파일이 지키는 것은 그 24건이고, **안 하는 쪽도 같이
지킨다** — 범위가 조용히 넓어지면 문서 하나가 통째로 딸려 온다.
"""

from __future__ import annotations

import pytest

from nexus.search.crossrefs import (
    MAX_SECTIONS,
    TOP_HITS,
    referenced_numbers,
    section_number,
)


class _Hit:
    def __init__(self, rid, doc_rid, chunk_text):
        self.rid, self.doc_rid, self.chunk_text = rid, doc_rid, chunk_text


# ── 무엇을 참조로 보는가 ──────────────────────────────────────────────────────

def test_it_reads_the_notation_the_corpus_actually_uses():
    """⭐ 실측으로 고른 표기 하나. `§4` 와 `§ 4` 둘 다."""
    assert referenced_numbers("2. §4 의 세 조건을 확인한다.") == ["4"]
    assert referenced_numbers("§ 4 를 보라") == ["4"]
    assert referenced_numbers("§15.183 을 보라") == ["15.183"]


def test_it_keeps_the_order_the_document_wrote():
    """⛔ **상한에 잘릴 때 잘리는 것이 뒤에 적힌 참조여야 한다** — 문서가 먼저 가리킨 것이 먼저."""
    assert referenced_numbers("§7 과 §2 와 §7 을 보라") == ["7", "2"]


def test_a_number_that_is_not_a_reference_is_not_one():
    """⚠ **넓히면 문서 하나가 통째로 딸려 온다.** `N절`·`N장` 은 합쳐 3건이라 안 받는다."""
    assert referenced_numbers("4절을 보라") == []
    assert referenced_numbers("2장에 적혀 있다") == []
    assert referenced_numbers("조건은 세 개이고 4 가지가 아니다") == []
    assert referenced_numbers(None) == []


def test_a_section_says_its_own_number():
    assert section_number("SOP-03 … > 4. 대체 슬롯은 기본이 아니다") == "4"
    assert section_number("문서 > 머리말") is None
    assert section_number(None) is None


def test_a_subsection_does_not_answer_to_its_parents_number():
    """⛔ **출하 전에 이 검사가 잡았다 (2026-09-23).**

    앞 판의 정규식은 번호 뒤에 마침표를 요구했다. 그러면 `6.1 제목` 에서 **`6.1` 을 잡았다가
    되돌아가 `6` + 마침표**로 맞는다 — 하위 절이 **제 부모 번호로 앉고**, `§6` 참조가
    엉뚱하게 `6.1` 을 데려온다. 가리킨 절을 데려온다는 이 모듈의 약속이 그 자리에서 깨진다.
    """
    assert section_number("문서 > 6.1 `SOURCE_MISSING` 은 …") == "6.1"
    assert section_number("문서 > 6. 탐색 대장에 남는 것") == "6"
    assert section_number("문서 > 15.183 어떤 항목") == "15.183"


# ── 데려오는가 ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_pointed_at_section_is_asked_for(monkeypatch):
    """⛔ **이것이 이 파일의 핵심이다.** 조각 5 를 받으면 조각 4 도 온다.

    표현이 아니라 **행동**을 단언한다 — `fill_for_sections` 가 **무엇을 요청받았는지** 본다.
    """
    from nexus.search import crossrefs

    async def fake_rows(*a, **k):
        return [{"doc_rid": "d1", "section_path": "SOP-03 > 4. 대체 슬롯은 기본이 아니다"},
                {"doc_rid": "d1", "section_path": "SOP-03 > 5. 절차"}]
    monkeypatch.setattr(crossrefs.db, "fetch_all", fake_rows)

    asked = {}

    async def fake_fill(tenant, clearance, sections, exclude):
        asked["sections"] = sections
        return [{"rid": "c4"}]
    import nexus.search.section_fill as sf
    monkeypatch.setattr(sf, "fill_for_sections", fake_fill)

    out = await crossrefs.referenced_chunks(
        [_Hit("c5", "d1", "2. §4 의 세 조건을 확인한다.")], "picasso", "INTERNAL")

    assert asked["sections"] == [("d1", "SOP-03 > 4. 대체 슬롯은 기본이 아니다")], \
        "가리킨 절을 요청하지 않았다 — 받는 쪽은 조건 없는 포인터를 받는다"
    assert out == [{"rid": "c4"}]


@pytest.mark.asyncio
async def test_an_ambiguous_number_is_not_guessed(monkeypatch):
    """⛔ **한 번호에 절이 둘이면 안 고른다.**

    고르면 **문서가 안 가리킨 절을 데려온다.** 이 모듈이 절을 고르지 않는다는 규율이
    여기서 시험된다 — 고르는 것은 문서이지 이 코드가 아니다.
    """
    from nexus.search import crossrefs

    async def fake_rows(*a, **k):
        return [{"doc_rid": "d1", "section_path": "문서 > 4. 앞의 것"},
                {"doc_rid": "d1", "section_path": "부록 > 4. 뒤의 것"}]
    monkeypatch.setattr(crossrefs.db, "fetch_all", fake_rows)

    called = False

    async def fake_fill(*a, **k):
        nonlocal called
        called = True
        return []
    import nexus.search.section_fill as sf
    monkeypatch.setattr(sf, "fill_for_sections", fake_fill)

    out = await crossrefs.referenced_chunks(
        [_Hit("c5", "d1", "§4 를 보라")], "picasso", "INTERNAL")

    assert out == []
    assert not called, "애매한 번호를 하나 집어 요청했다"


@pytest.mark.asyncio
async def test_nothing_happens_when_the_text_points_nowhere(monkeypatch):
    """⭐ **대조군** — 참조가 없으면 DB 를 안 친다. 없으면 프롬프트가 오늘과 같다."""
    from nexus.search import crossrefs

    async def boom(*a, **k):
        raise AssertionError("참조가 없는데 조회했다")
    monkeypatch.setattr(crossrefs.db, "fetch_all", boom)

    assert await crossrefs.referenced_chunks(
        [_Hit("c1", "d1", "참조가 없는 본문")], "picasso", "INTERNAL") == []
    assert await crossrefs.referenced_chunks([], "picasso", "INTERNAL") == []


# ── 터진 것과 없는 것을 가른다 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_failure_is_not_an_absence(monkeypatch):
    """⛔ **빈 목록 하나로 「가리킨 절이 없다」와 「못 봤다」를 둘 다 말하지 않는다** (#533)."""
    from nexus.search import crossrefs

    async def boom(*a, **k):
        raise RuntimeError("조회가 터졌다")
    monkeypatch.setattr(crossrefs.db, "fetch_all", boom)

    failed: list = []
    out = await crossrefs.referenced_chunks(
        [_Hit("c5", "d1", "§4 를 보라")], "picasso", "INTERNAL", failed=failed)

    assert out == []
    assert failed == ["crossrefs"], "터진 것이 빈 것과 같은 값으로 나온다"


# ── 배선 · 상한 ───────────────────────────────────────────────────────────────

def test_the_one_seam_is_wired():
    """⛔ 답변 경로 셋이 `packet_for_answer` 로 모이므로 **여기 한 곳**이면 된다."""
    import inspect

    from nexus.search.reconcile import packet_for_answer

    src = inspect.getsource(packet_for_answer)
    assert "cross_reference_fill" in src
    assert "referenced_chunks" in src
    assert "failed=result.enrichment_failed" in src


def test_the_caps_are_small_and_stated():
    """⚠ 참조가 **45개**인 조각이 실재한다 — 상한이 없으면 한 조각이 문서를 통째로 데려온다."""
    assert MAX_SECTIONS == 5
    assert TOP_HITS == 3
