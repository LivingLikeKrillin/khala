"""그림에 갇힌 정책을 재는 관측 기제 — **기능이 아니라 게이트의 첫 하위 단계.**

ADR-0002 는 부채 상환 기능을 "관측된 **기록된 비율**이 **설정 임계**를 **롤링 윈도**에서 넘을
때" 로 게이트하고, 게이트ⓐ 에서 형식을 못박았다: *"관측 기제 자체가 첫 하위 단계이며, 그것이
존재하고 임계를 넘기 전까지 하류는 아무것도 짓지 않는다."*

2026-08-09 에 그 형식을 어길 뻔했다 — 질의 **한 건**이 그림 속 표를 못 찾은 것을 근거로 비전
추출을 짓자는 ADR 초안을 냈고, 비평이 "일화는 ADR-0002 가 요구하는 형식이 아니다" 로 잡았다.
소유자 처분: 게이트를 제대로 세운다. 이 파일이 그 관측 쪽이다.

여기서 재는 것은 **세는 일이 실제로 세는가**, 그리고 **근사가 무엇을 놓치는지 드러나는가** 이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.search.hybrid import SearchHit, SearchResult  # noqa: E402
from nexus.search.signals import extract_signals  # noqa: E402


def _hit(rid, doc_rid, n_images=0):
    return SearchHit(rid=rid, doc_rid=doc_rid, doc_title="t", section_path="s",
                     source_uri="u", snippet="x", doc_n_images=n_images, score=0.5)


def _sig(hits):
    return extract_signals(SearchResult(hits=hits, route_used="hybrid_only"),
                           path="/search", tenant="default", clearance="INTERNAL",
                           query="질의", latency_ms=1)


def test_evidence_from_an_image_bearing_document_is_counted():
    s = _sig([_hit("c1", "d1", n_images=11)])
    assert s.n_image_bearing_docs == 1


def test_a_document_without_images_is_not_counted():
    """모든 근거를 세면 신호가 아니라 검색량이 된다."""
    assert _sig([_hit("c1", "d1", n_images=0)]).n_image_bearing_docs == 0


def test_documents_are_counted_once_however_many_snippets_they_supply():
    """청크 단위로 세면 긴 문서가 신호를 부풀린다."""
    hits = [_hit("c1", "d1", 11), _hit("c2", "d1", 11), _hit("c3", "d2", 6)]
    assert _sig(hits).n_image_bearing_docs == 2


def test_a_mixed_result_counts_only_the_image_bearing_half():
    hits = [_hit("c1", "d1", 11), _hit("c2", "d2", 0), _hit("c3", "d3", 6)]
    assert _sig(hits).n_image_bearing_docs == 2


def test_no_evidence_at_all_counts_zero_and_still_records_no_answer():
    """**근사가 놓치는 경우.** 검색이 그 문서를 아예 못 가져오면 근거가 없고, 그러면 그림
    문서에서 왔는지도 알 수 없다 — 신호는 0 이 된다.

    이 검사는 그 눈먼 구간을 **고치지 않는다.** 드러낼 뿐이다: 신호를 실제 결손보다 작게
    읽어야 한다는 사실이 코드에 남아 있어야, 나중에 임계를 정할 때 그것을 감안한다.
    """
    s = _sig([])
    assert s.no_answer is True
    assert s.n_image_bearing_docs == 0


def test_a_hit_from_before_the_column_does_not_crash_the_counter():
    """옛 호출부·픽스처가 `doc_n_images` 를 모를 수 있다. 신호 수집이 요청을 깨면 안 된다."""
    class _Old:
        rid, doc_rid, doc_title, section_path = "c", "d", "t", "s"
        source_uri, snippet, score = "u", "x", 0.5

    assert _sig([_Old()]).n_image_bearing_docs == 0
