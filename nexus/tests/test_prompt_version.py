"""프롬프트 버전이 **잊을 수 없는 방식으로** 남는가.

`PROMPT_VERSION = 3` 같은 상수는 고치는 사람이 올려야 하고, 그 규율은 반드시 한 번 깨진다 —
깨진 순간 기록은 조용히 거짓이 된다. 그래서 값은 프롬프트 텍스트에서 파생된다.
"""

from __future__ import annotations

from nexus.llm import prompt_version as V


def test_the_same_prompt_gives_the_same_value():
    """실행마다 달라지면 구간을 못 가른다."""
    assert V.answer_prompt_sha() == V.answer_prompt_sha()
    assert V.rewrite_prompt_sha() == V.rewrite_prompt_sha()


def test_the_two_prompts_are_told_apart():
    """턴당 프롬프트가 둘이다. 한 칸에 뭉뚱그리면 어느 쪽이 바뀌었는지 못 본다."""
    assert V.answer_prompt_sha() != V.rewrite_prompt_sha()


def test_changing_the_system_prompt_changes_the_value(monkeypatch):
    """**이 검사가 이 파일의 전부다.** 값이 안 바뀌면 기록은 아무것도 말하지 않는다."""
    before = V.answer_prompt_sha()
    import nexus.llm.prompts as P
    monkeypatch.setattr(P, "SYSTEM_PROMPT", P.SYSTEM_PROMPT + "\n한 줄 더.")
    assert V.answer_prompt_sha() != before


def test_changing_the_user_template_changes_the_value(monkeypatch):
    """근거를 어떻게 감싸는지도 행동이다 — 시스템 프롬프트만 보면 그 변경이 안 보인다."""
    before = V.answer_prompt_sha()
    import nexus.llm.prompts as P

    def other(query: str, evidence_text: str) -> str:
        return f"{query}\n{evidence_text}\n다르게 지시한다."
    monkeypatch.setattr(P, "build_user_prompt", other)
    assert V.answer_prompt_sha() != before


def test_the_query_and_evidence_do_not_enter_the_value():
    """질의·근거를 넣으면 모든 행이 서로 달라 아무것도 구분하지 못한다 — 그리고 텍스트가 샌다."""
    a = V.fingerprint("시스템", "템플릿")
    b = V.fingerprint("시스템", "템플릿")
    assert a == b
    # 조각 경계가 있어야 이어붙임 모호성이 없다: ("ab","c") 와 ("a","bc") 는 달라야 한다.
    assert V.fingerprint("ab", "c") != V.fingerprint("a", "bc")


def test_an_unreadable_source_does_not_break_the_answer_path(monkeypatch):
    """진단이 답변을 죽일 수 없다 — 소스를 못 읽는 배포(동결 바이너리 등)도 있다."""
    monkeypatch.setattr(V.inspect, "getsource", lambda _fn: (_ for _ in ()).throw(OSError()))
    assert isinstance(V.answer_prompt_sha(), str)
    assert len(V.answer_prompt_sha()) == 12


# ── 기록에 실제로 남는가 ────────────────────────────────────────────────────────

from nexus.search import signals as S  # noqa: E402


def _sig(**kw):
    from nexus.search.hybrid import SearchResult

    base = dict(path="search", tenant="t", clearance="INTERNAL", query="q", latency_ms=1)
    return S.extract_signals(SearchResult(), kw.pop("answer", None), **{**base, **kw})


def test_an_answer_row_carries_the_answer_prompt():
    from nexus.llm.answer import AnswerResult

    sig = _sig(path="search_answer", answer=AnswerResult(answer="답"))
    assert sig.answer_prompt_sha == V.answer_prompt_sha()


def test_a_search_only_row_claims_no_answer_prompt():
    """검색 전용 경로에 답변 프롬프트 지문을 적으면 그것은 거짓이다."""
    assert _sig().answer_prompt_sha == ""


def test_the_rewrite_prompt_is_recorded_only_when_it_ran():
    from nexus.search.rewrite import Rewrite

    assert _sig().rewrite_prompt_sha == ""
    assert _sig(rewrite=Rewrite(query="q", called=False)).rewrite_prompt_sha == ""
    called = _sig(rewrite=Rewrite(query="q2", called=True, changed=True))
    assert called.rewrite_prompt_sha == V.rewrite_prompt_sha()


def test_the_signal_carries_the_fingerprint_not_the_prompt():
    from nexus.llm.answer import AnswerResult

    sig = _sig(path="search_answer", answer=AnswerResult(answer="답"))
    blob = repr(sig)
    from nexus.llm.prompts import SYSTEM_PROMPT
    assert SYSTEM_PROMPT[:40] not in blob, "프롬프트 본문이 신호에 실렸다"
    assert len(sig.answer_prompt_sha) == 12
