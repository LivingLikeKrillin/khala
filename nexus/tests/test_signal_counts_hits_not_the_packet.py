"""`search_log.n_snippets` 가 세는 것과 응답의 `evidence_snippets` 가 세는 것은 **다르다.**

⛔ **실측 2026-09-18, 같은 한 번의 호출.** `POST /search/answer {"top_k": 8}` 에서
응답은 `evidence_snippets=13` 인데 기록은 `n_snippets=8` 이었다. 다른 에이전트가 이것을
「관측이 응답과 어긋난다」로 읽고 장애를 의심했고, 나도 몇 걸음 쫓아갔다. **어긋난 것이
아니라 다른 집합이다** — 앞엣것은 검색 히트, 뒤엣것은 모델에게 실제로 간 묶음이다.

⛔ **그래서 이 검사는 「같아야 한다」가 아니라 「달라도 된다」를 고정한다.** 다음 사람이
어긋남으로 읽고 한쪽을 다른 쪽에 맞추면, `search_log` 1,190행의 뜻이 조용히 바뀐다.

⚠ 그리고 **어느 코퍼스를 봤는가**는 `tenant` 가 아니다. 그 칸은 principal 귀속이고
(2026-09-02 에 목록을 TEXT 칸에 넣었다가 신호가 34시간 죽은 뒤 그렇게 정해졌다),
답은 `read_scope` 와 `evidence_tenants` 에 있다.
"""

from __future__ import annotations

import pathlib

from nexus.search import signals


def _src(mod) -> str:
    return pathlib.Path(mod.__file__).read_text(encoding="utf-8")


def test_the_signal_counts_hits():
    """⛔ 이 한 줄이 두 수가 갈리는 이유 전부다."""
    assert "n_snippets=len(hits)" in _src(signals)


def test_the_packet_side_counts_the_packet():
    from nexus.search import evidence_packet

    assert "n_snippets=len(packet.snippets)" in _src(evidence_packet)


def test_both_sites_say_they_are_not_the_same_number():
    """⚠ 주석이 없으면 다음 사람이 어긋남으로 읽는다 — 실제로 그렇게 읽혔다."""
    from nexus.search import evidence_packet

    for mod in (signals, evidence_packet):
        src = _src(mod)
        assert "n_snippets" in src
        assert "맞추지 마라" in src, f"{mod.__name__} 에 그 사실이 안 적혀 있다"


def test_the_corpus_question_is_answered_by_another_field():
    """⛔ `tenant` 로 「picasso 가 얼마나 쓰이나」를 세면 **0 으로 보인다** — 그 칸은
    principal 귀속이다. 답은 `read_scope`·`evidence_tenants` 에 있고, 둘 다 신호에 있다."""
    fields = set(signals.SearchSignals.__dataclass_fields__)
    assert {"read_scope", "evidence_tenants"} <= fields, (
        "코퍼스를 답하는 칸이 신호에 없다 — 있다고 적어 둔 문장이 거짓이 된다")
    assert "tenant" in fields


def test_the_attribution_decision_is_written_down_where_it_is_made():
    """⚠ 이유가 코드 옆에 없으면 다음 사람이 '버그' 로 보고 고친다 — 고치면 34시간 사고가
    다시 난다(목록을 TEXT 칸에 넣는 그 경로다)."""
    api = pathlib.Path(signals.__file__).parents[1] / "api.py"
    src = api.read_text(encoding="utf-8")
    # 셋이다 — `/search` · `/search/answer` · **스트리밍**. 셋째가 빠져 있어서 웹 채팅이
    # 컷오버가 연 교차 코퍼스를 못 읽었던 적이 있다(api.py 1098 주석).
    assert src.count("req.tenant = principal.tenant") == 3, "귀속이 세 경로에 다 있어야 한다"
    assert "귀속" in src
