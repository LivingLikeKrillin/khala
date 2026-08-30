"""답변 경로의 검색 예산.

⛔ **왜 검사가 있나.** 이 값은 숫자 하나라서 조용히 되돌아간다. 2026-08-30 파일럿 질문에서
한 계열 12개 중 5개만 근거에 와서 답이 반쪽이 됐고, 12개는 코퍼스에도 랭킹 20 안에도 다
있었다 — 우리가 10에서 자르고 있었다. 되돌리려면 이 검사도 같이 고쳐야 하고, 그때 결정이
커밋에 남는다.
"""

from __future__ import annotations

from nexus.api import AnswerRequest, SearchRequest


def test_the_answer_path_can_hold_a_whole_set():
    assert AnswerRequest(query="x").top_k == 20


def test_the_search_only_path_stays_small():
    """⛔ 대조군. 검색 전용 경로는 사람이 목록을 보는 자리이고, 근거를 두 배로 실을 이유가
    없다. 두 기본값이 같이 움직이면 이 구분이 사라진다."""
    assert SearchRequest(query="x").top_k == 10
