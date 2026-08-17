"""앵커 상태가 **답변까지 나온다** (SPEC-nexus-doc-code-anchors §3.4 읽기 경로).

앵커는 2026-08-17 까지 쓰기만 있고 읽기가 없었다 — 라이브에 2,544행이 앉아 있는데
검색·답변·웹 어디도 `doc_code_anchors` 를 읽지 않았다. 쌓기만 하는 산출물의 품질은
아직 값이 0이다. 여기서 지키는 것 넷:

- 상태 어휘는 **하나다** — 재검사(`recheck`)와 요청 경로가 같은 함수로 판정한다.
  둘로 갈리면 CLI 가 `changed` 라고 한 것을 답변이 `fresh` 라고 부르게 된다.
- **요청 경로에 N+1 을 두지 않는다.** `nexus code drift` 는 앵커마다 해소를 한 번씩 쳐서
  10분이 걸렸다. 그 모양이 검색 응답에 들어가면 안 된다 — 질의당 쿼리는 **한 개**다.
- 앵커가 없으면 프롬프트는 **바이트 단위로 오늘과 같다.** 평가 팩(`default` 테넌트)에는
  앵커가 없고, 거기에 한 줄이라도 새로 들어가면 지금까지의 점수와 비교가 끊긴다.
- 앵커 조회가 실패해도 **검색은 산다.** 진단이 진단 대상을 죽이면 안 된다.
"""

from __future__ import annotations

import pytest

from nexus.index.anchors import (
    AMBIGUOUS_NOW,
    CHANGED,
    FRESH,
    ORPHANED,
    recheck,
    status_from_counts,
)
from nexus.search.anchor_status import (
    AnchorStatus,
    DeletedMention,
    describe,
    statuses_for_chunks,
    summarize,
)
from nexus.search.evidence_packet import assemble_packet, format_for_llm
from nexus.search.hybrid import SearchHit


# ------------------------------------------------- 어휘는 하나다

@pytest.mark.parametrize("bound, matches", [
    ("h1", [("W", "W.java", "h1")]),
    ("h1", [("W", "W.java", "h2")]),
    ("h1", []),
    ("h1", [("W", "A.java", "h1"), ("W", "B.java", "h9")]),
])
def test_set_query_counts_and_recheck_agree(bound, matches):
    """집합 쿼리는 행을 세어 판정하고 재검사는 목록을 훑어 판정한다. 같은 답이어야 한다."""
    n_match = len(matches)
    n_same = sum(1 for m in matches if m[2] == bound)

    assert status_from_counts(n_match, n_same) == recheck(bound, matches)


# ------------------------------------------------- 요약 (응답용)

def test_summary_counts_the_denominator_and_names_only_the_drifted():
    """수는 전부 세고 **이름은 문제인 것만** 낸다 — 20개 fresh 를 나열하면 아무도 안 읽는다."""
    out = summarize([
        AnchorStatus("Alpha", FRESH),
        AnchorStatus("Beta", FRESH),
        AnchorStatus("Gamma", CHANGED),
        AnchorStatus("Delta", ORPHANED),
        AnchorStatus("Epsilon", AMBIGUOUS_NOW),
    ])

    assert out["total"] == 5
    assert out["fresh"] == 2
    assert out["changed"] == ["Gamma"]
    assert out["orphaned"] == ["Delta"]
    assert out["ambiguous_now"] == ["Epsilon"]


def test_no_anchors_has_no_summary():
    assert summarize([]) is None


# ------------------------------------------------- 한 줄 서술 (프롬프트용)

def test_description_names_the_missing_symbol():
    line = describe([AnchorStatus("Alpha", FRESH), AnchorStatus("OldName", ORPHANED)])

    assert "2개" in line
    assert "OldName" in line


def test_description_of_all_fresh_still_states_the_denominator():
    """'전부 있다' 도 사실이다. 없을 때만 말하면 침묵이 두 가지 뜻을 갖는다."""
    line = describe([AnchorStatus("Alpha", FRESH), AnchorStatus("Beta", FRESH)])

    assert "2개" in line
    assert "Alpha" not in line   # 멀쩡한 것은 이름을 안 부른다


def test_description_caps_the_name_list():
    """드리프트가 40건인 문단이 프롬프트를 이름으로 채우면 안 된다."""
    line = describe([AnchorStatus(f"Sym{i}", ORPHANED) for i in range(12)])

    assert "Sym0" in line
    assert "Sym11" not in line
    assert "외 " in line


def test_empty_anchors_describe_to_nothing():
    assert describe([]) == ""


# ------------------------------------------------- 프롬프트

def _hit(rid: str = "chunk:1") -> SearchHit:
    return SearchHit(
        rid=rid, doc_rid="doc:1", doc_title="설계 노트", section_path="§3",
        source_uri="git://x", snippet="본문", chunk_text="본문", score=0.5,
    )


async def test_prompt_is_byte_identical_when_there_are_no_anchors():
    """평가 팩과의 비교가 끊기지 않는다 — 앵커 없는 테넌트의 프롬프트는 안 바뀐다."""
    packet = await assemble_packet([_hit()])

    assert "코드 앵커" not in format_for_llm(packet)


async def test_prompt_carries_the_anchor_line_when_anchors_exist():
    packet = await assemble_packet([_hit()])
    packet.snippets[0].code_anchors = [
        AnchorStatus("Alpha", FRESH), AnchorStatus("OldName", ORPHANED)]

    out = format_for_llm(packet)

    assert "코드 앵커" in out
    assert "OldName" in out


# ------------------------------------------------- 요청 경로의 모양

def _row(chunk_rid, name, *, kind="anchor", n_match=1, n_same=1,
         date="", commit="", subject=""):
    """쿼리가 돌려주는 행 하나. 앵커 가지와 삭제 가지가 **같은 모양**으로 온다(UNION ALL)."""
    return {"chunk_rid": chunk_rid, "name": name, "kind": kind,
            "n_match": n_match, "n_same": n_same,
            "deleted_date": date, "deleted_commit": commit, "subject": subject}


class _Counter:
    """`db.fetch_all` 을 세는 가짜. 앵커 수가 늘어도 쿼리 수는 1이어야 한다."""

    def __init__(self, rows):
        self.rows, self.calls = rows, 0

    async def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.rows


async def test_one_query_regardless_of_how_many_anchors(monkeypatch):
    rows = [
        _row("c1", f"Sym{i}")
        for i in range(50)
    ]
    fake = _Counter(rows)
    monkeypatch.setattr("nexus.search.anchor_status.db.fetch_all", fake)

    out = await statuses_for_chunks("t", ["c1", "c2", "c3"])

    assert fake.calls == 1
    assert len(out["c1"].anchors) == 50


async def test_no_chunks_touches_no_database(monkeypatch):
    fake = _Counter([])
    monkeypatch.setattr("nexus.search.anchor_status.db.fetch_all", fake)

    assert await statuses_for_chunks("t", []) == {}
    assert fake.calls == 0


async def test_a_failed_lookup_does_not_take_the_search_down(monkeypatch):
    """앵커는 보강이다. 없으면 답이 조금 덜 말할 뿐, 답 자체가 사라지면 안 된다."""
    async def _boom(*args, **kwargs):
        raise RuntimeError("relation does not exist")

    monkeypatch.setattr("nexus.search.anchor_status.db.fetch_all", _boom)

    packet = await assemble_packet([_hit()], tenant="t")

    assert packet.snippets[0].code_anchors == []
    assert packet.snippets[0].code_deleted == []
    assert "본문" in format_for_llm(packet)


# ------------------------------------------------- 지워진 이름 (②b)
#
# 문서가 부르는데 코드에 없는 이름의 이유는 셋이고 처분이 다르다: 외부 타입(문서 잘못 아님) ·
# 미구현(설계 문서에선 정상) · **지워짐**(드리프트). 라이브 실측 비율은 99 : 1,354 : 63 이었다.
# 셋을 안 가르고 다 올리면 목록이 신뢰를 잃는다 — 그래서 여기 오는 것은 세 번째뿐이다.


def _gone(name="Avatar", date="2026-02-19"):
    return DeletedMention(name, date, "abc1234", "refactor: merge domain models")


def test_a_deleted_name_is_not_counted_in_the_anchor_denominator():
    """분모는 '걸린 참조' 를 센다. 걸 곳이 사라진 이름을 섞으면 5/7 이 무엇의 5인지 모른다."""
    out = summarize([AnchorStatus("Alpha", FRESH)], [_gone()])

    assert out["total"] == 1 and out["fresh"] == 1
    assert [d["name"] for d in out["deleted"]] == ["Avatar"]


def test_a_chunk_with_only_deleted_names_still_reports():
    """앵커가 0개라고 침묵하면 안 된다 — 지워진 이름만 부르는 문단이 정확히 최악의 경우다."""
    out = summarize([], [_gone()])

    assert out is not None and out["total"] == 0
    assert len(out["deleted"]) == 1


def test_the_description_carries_the_date_because_that_is_what_makes_it_actionable():
    line = describe([], [_gone(date="2026-02-19")])

    assert "Avatar" in line
    assert "2026-02-19" in line


def test_the_description_lists_anchors_and_deleted_names_in_one_line():
    line = describe([AnchorStatus("Alpha", FRESH)], [_gone()])

    assert "1개 중 1개" in line
    assert "Avatar" in line


def test_deleted_names_are_capped_like_the_others():
    line = describe([], [_gone(name=f"Gone{i}") for i in range(12)])

    assert "Gone0" in line
    assert "Gone11" not in line
    assert "외 " in line


async def test_the_prompt_stays_silent_when_nothing_was_deleted():
    packet = await assemble_packet([_hit()])

    assert "지워진" not in format_for_llm(packet)


async def test_the_prompt_names_the_deleted_symbol(monkeypatch):
    rows = [_row("chunk:1", "Avatar", kind="deleted", n_match=0, n_same=0,
                 date="2026-02-19", commit="abc1234", subject="refactor: drop avatar module")]
    monkeypatch.setattr("nexus.search.anchor_status.db.fetch_all", _Counter(rows))

    packet = await assemble_packet([_hit()], tenant="t")
    out = format_for_llm(packet)

    assert "Avatar" in out and "2026-02-19" in out


async def test_one_query_still_answers_both_facts(monkeypatch):
    """앵커 상태와 지워진 이름이 **한 쿼리**로 온다 — UNION ALL 로 묶은 이유가 이것이다."""
    rows = [_row("c1", "Alpha"),
            _row("c1", "Avatar", kind="deleted", n_match=0, n_same=0, date="2026-02-19")]
    fake = _Counter(rows)
    monkeypatch.setattr("nexus.search.anchor_status.db.fetch_all", fake)

    out = await statuses_for_chunks("t", ["c1"])

    assert fake.calls == 1
    assert [a.name for a in out["c1"].anchors] == ["Alpha"]
    assert [d.name for d in out["c1"].deleted] == ["Avatar"]


async def test_statuses_are_keyed_back_to_their_chunk(monkeypatch):
    rows = [
        _row("c1", "Alpha"),
        _row("c2", "Beta", n_match=0, n_same=0),
    ]
    monkeypatch.setattr("nexus.search.anchor_status.db.fetch_all", _Counter(rows))

    out = await statuses_for_chunks("t", ["c1", "c2"])

    assert out["c1"].anchors == [AnchorStatus("Alpha", FRESH)]
    assert out["c2"].anchors == [AnchorStatus("Beta", ORPHANED)]
