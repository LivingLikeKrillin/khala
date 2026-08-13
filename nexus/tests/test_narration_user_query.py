"""답변자는 사용자가 **실제로 친 문장**도 본다 (SPEC-nexus-multi-turn-narration §3.1, U2).

재작성 단계는 "검색과 무관한 요청" 을 질의에서 뺀다 — 검색 질의로서는 옳다. 그런데 떼어낸
조각이 **아무 데도 전달되지 않아** 답변자는 "세 줄로" 라는 말을 들은 적이 없다. 그래서 사용자는
자기가 한 말이 무시된 답을 받는다.

**여기서 넣는 것은 이력이 아니다.** 넣는 것은 이번 턴 사용자가 친 문장이고, 그것은 이미 서버에
도착해 있던 값이다 — LLM 이 만든 텍스트가 아니고, 새로 열리는 경로도 없다. 선행 SPEC 의
"이력은 답변 프롬프트에 안 들어간다" 는 그대로 살아 있고, 이 파일이 그것도 함께 지킨다.

지키는 불변식 (SPEC §4):

  I1  원문 == 재작성이면 프롬프트가 **바이트 단위로** 오늘과 같다
  I2  이력은 답변 프롬프트에 들어가지 않는다
  I3  프롬프트에 들어가는 사용자 텍스트는 `req.query` **그대로**다 (LLM 산물이 아니다)
  I4  근거는 패킷에서만 온다 — 원문이 있다고 인용/숫자 규칙이 느슨해지지 않는다
  I5  검색은 안 바뀐다 — `hybrid_search` 가 받는 **인자 값**이 같다
"""

from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.api import app  # noqa: E402
from nexus.llm import prompt_version as V  # noqa: E402
from nexus.llm import prompts as P  # noqa: E402

_TOKEN = "x" * 40
_AUTH = {"Authorization": "Bearer " + _TOKEN}

_EVIDENCE = "## 근거\n[문서 A > 1절]\n레플리카 수는 지표 평균으로 정한다."


# ── I1 — 재작성이 없으면 오늘과 바이트 단위로 같다 ──────────────────────────────

def test_prompts_are_byte_identical_to_today_when_nothing_was_rewritten():
    """오늘의 프롬프트를 **문자 그대로** 박아 둔다.

    "같은 함수를 두 번 부르면 같다" 는 동어반복이라 아무것도 지키지 못한다. 회귀는 함수가
    조용히 다른 문자열을 내기 시작할 때 오고, 그러면 이력 없는 단일턴 트래픽 100% 가 새
    프롬프트를 받는다 — §5.3 이 "대조군이 회귀하면 켜지 않는다" 고 적어 둔 바로 그 사고다.
    """
    system, user = P.build_prompts("레플리카 수는 무엇으로 정하나", _EVIDENCE)

    assert system == P.SYSTEM_PROMPT
    assert user == (
        "## 사용자 질문\n"
        "레플리카 수는 무엇으로 정하나\n"
        "\n"
        f"{_EVIDENCE}\n"
        "\n"
        "위 근거를 바탕으로 질문에 답변해주세요. 근거에 없는 내용은 포함하지 마세요."
    )


def test_a_rewrite_that_changed_nothing_is_the_same_as_no_rewrite():
    """보수적 재작성의 **정상 결과가 "원문과 같음"** 이다. 그 흔한 경로가 오늘과 갈라지면
    이력이 붙은 트래픽 대부분이 이유 없이 다른 프롬프트를 받는다."""
    q = "레플리카 수는 무엇으로 정하나"
    assert P.build_prompts(q, _EVIDENCE, user_query=q) == P.build_prompts(q, _EVIDENCE)


# ── §3.1 — 두 문장이 **둘 다** 도착하고, 역할이 갈린다 ─────────────────────────

def test_the_users_own_sentence_reaches_the_answerer_verbatim():
    system, user = P.build_prompts(
        "수평 파드 오토스케일링은 레플리카 수를 무엇을 보고 정하나",
        _EVIDENCE,
        user_query="그거 세 줄로 요약해줘",
    )
    assert "그거 세 줄로 요약해줘" in user, "사용자가 친 문장이 답변자에게 도착하지 않았다"
    assert "수평 파드 오토스케일링은 레플리카 수를 무엇을 보고 정하나" in user, (
        "재작성 질의가 사라졌다 — 근거가 왜 이것인지 답변자가 모르게 된다")
    assert system != P.SYSTEM_PROMPT, "역할을 가르는 규칙이 시스템 프롬프트에 없다"


def test_the_system_prompt_says_which_sentence_governs_what():
    """§3.1: 재작성 질의는 **무엇을 찾았는지**, 원문은 **사용자가 무엇을 요청했는지**.

    그리고 §4 I4·I6 — 원문이 프롬프트에 있다고 근거 규칙이 바뀌지 않는다. 규칙을 **이름으로
    부르지 않으면** 모델이 피해 간다(인용 SPEC 에서 같은 실수를 한 적이 있다)."""
    system, _ = P.build_prompts("찾은 질의", _EVIDENCE, user_query="원래 질문")

    assert system.startswith(P.SYSTEM_PROMPT), "기존 규칙이 통째로 앞에 남아 있어야 한다"
    tail = system[len(P.SYSTEM_PROMPT):]
    assert "형식" in tail, "형식 요청을 따르라는 말이 없으면 U2 가 재는 것이 프롬프트에 없다"
    assert "근거" in tail, "원문이 근거 규칙을 이기지 못한다는 말이 있어야 한다 (I4·I6)"


def test_the_prompt_fingerprint_covers_the_role_rule(monkeypatch):
    """지문은 **모델에게 가는 바이트**에서 파생돼야 한다. 규칙을 상수 하나로 빼 놓고 지문이
    그것을 안 읽으면, 그 문구를 고친 날 기록은 조용히 거짓이 된다."""
    before = V.answer_prompt_sha()
    monkeypatch.setattr(P, "USER_REQUEST_RULE", P.USER_REQUEST_RULE + "\n한 줄 더.")
    assert V.answer_prompt_sha() != before


# ── I2 — 이력은 여전히 들어가지 않는다 ─────────────────────────────────────────

def test_history_still_never_reaches_the_answer_prompt():
    """선행 SPEC I3 을 물려받는다. 답변 프롬프트 조립 함수는 이력을 받을 **자리조차** 없다."""
    params = set(inspect.signature(P.build_prompts).parameters)
    assert "history" not in params, (
        f"조립 함수가 이력을 받는다: {sorted(params)} — I2 는 인자 수준에서 지켜야 한다")


# ── I4 — 숫자 검증은 답변자가 본 것을 기준으로 한다 ────────────────────────────

class _FakeLLM:
    """`test_citation_validation.py` 의 것과 같은 모양 — 답변 문자열만 정해 준다."""

    def __init__(self, answer: str):
        self._answer = answer
        self.configured = True
        self.seen: tuple[str, str] | None = None

    async def generate_full(self, system, user, max_tokens=4096):
        from nexus.providers.llm import LLMResult, Usage
        self.seen = (system, user)
        return LLMResult(text=self._answer, usage=Usage(None, None, None, "fake"))


def _packet():
    from nexus.search.evidence_packet import EvidencePacket, EvidenceSnippet

    return EvidencePacket(snippets=[EvidenceSnippet(
        chunk_rid="c1", doc_rid="d1", doc_title="문서 A", section_path="1절",
        source_uri="u", text="레플리카 수는 지표 평균으로 정한다.", score=0.9,
        classification="INTERNAL")])


@pytest.mark.asyncio
async def test_a_number_the_user_typed_is_not_reported_as_invented():
    """사용자가 "상위 25개" 라고 썼고 답변이 25 를 되풀이했다. LLM 이 그 숫자를 본 것은 사실이다.

    검증기가 원문을 모르면 **사용자 자신의 숫자**가 무근거로 찍힌다 — 웹·슬랙이 그것을 배지로
    띄우므로 조용한 오차가 아니라 화면에 뜨는 거짓 경고다."""
    from nexus.llm.answer import generate_answer

    llm = _FakeLLM("상위 25개를 보여드립니다. [출처: 문서 A, 1절]")
    res = await generate_answer("레플리카 수 결정 기준", _packet(), llm,   # type: ignore[arg-type]
                                user_query="상위 25개만 표로")
    assert res.unverified_numbers == 0, (
        f"사용자가 직접 쓴 숫자가 무근거로 찍혔다: {res.numbers}")


@pytest.mark.asyncio
async def test_a_number_from_nowhere_is_still_reported():
    """대조군. 위 완화가 검증기를 통째로 끄지 않았음을 보인다 — 그물은 일부러 깨뜨려 확인한다."""
    from nexus.llm.answer import generate_answer

    llm = _FakeLLM("응답 시간은 47ms 입니다. [출처: 문서 A, 1절]")
    res = await generate_answer("레플리카 수 결정 기준", _packet(), llm,   # type: ignore[arg-type]
                                user_query="상위 25개만 표로")
    assert res.unverified_numbers == 1, f"지어낸 숫자가 통과했다: {res.numbers}"


@pytest.mark.asyncio
async def test_the_answerer_actually_sends_both_sentences_to_the_model():
    """`generate_answer` 가 조립 함수를 부르기만 하고 결과를 안 쓰는 배선 누락을 막는다 —
    이 리포에서 '테스트 초록인데 동작 안 함' 의 흔한 모양이다."""
    from nexus.llm.answer import generate_answer

    llm = _FakeLLM("답 [출처: 문서 A, 1절]")
    await generate_answer("재작성된 질의", _packet(), llm,   # type: ignore[arg-type]
                          user_query="그거 세 줄로 요약해줘")
    system, user = llm.seen
    assert "그거 세 줄로 요약해줘" in user and "재작성된 질의" in user
    assert system != P.SYSTEM_PROMPT


# ── I3·I5 — 배선 (HTTP 표면) ───────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    """`test_history_wire.py` 와 같은 이유로 풀을 되돌린다 — TestClient 의 루프가 닫히면
    모듈 전역 asyncpg 풀은 죽은 손잡이가 되고, 다음 테스트가 그것을 집어 죽는다."""
    from nexus import db

    monkeypatch.setenv("NEXUS_DEV_TOKEN", _TOKEN)
    saved = db._pool
    try:
        yield TestClient(app)
    finally:
        db._pool = saved


def _wire(monkeypatch, seen: dict, *, rewritten: str):
    """검색·신호·재작성을 세우고, 답변자와 검색이 **무엇을 받았는지** 받아 적는다."""
    from nexus.llm.answer import AnswerResult
    from nexus.search.hybrid import SearchHit, SearchResult
    from nexus.search.rewrite import Rewrite

    async def one_hit(*a, **k):
        seen["search"] = k
        return SearchResult(hits=[SearchHit(rid="c1", doc_rid="d1", doc_title="문서",
                                            chunk_text="근거 본문", score=0.9)],
                            route_used="keyword_only", timing_ms={"total_ms": 1})
    monkeypatch.setattr("nexus.api.hybrid_search", one_hit)

    async def no_signal(*a, **k):
        return None
    monkeypatch.setattr("nexus.api.record_search", no_signal)

    async def fake_rewrite(query, history, llm_svc, **kw):
        return Rewrite(query=rewritten, called=True, changed=rewritten != query)
    monkeypatch.setattr("nexus.api.rewrite_query", fake_rewrite)

    async def spy_answer(query, packet, **kw):
        seen["answer"] = {"query": query, **kw}
        return AnswerResult(answer="답", evidence_snippets=[], provenance=[],
                            route_used="keyword_only")
    monkeypatch.setattr("nexus.api.generate_answer", spy_answer)


def _turns(n: int = 2) -> list[dict]:
    return [{"role": "user" if i % 2 == 0 else "assistant", "content": "앞 턴"} for i in range(n)]


@pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"),
                    reason="NEXUS_TEST_DB_URL 필요 — 답변 경로를 끝까지 태워야 한다")
def test_the_answerer_gets_the_users_sentence_exactly_as_it_arrived(client, monkeypatch):
    """§4 I3. 문자열 **동일**이다 — 비슷한 것도, 다듬은 것도 아니다."""
    seen: dict = {}
    _wire(monkeypatch, seen, rewritten="수평 파드 오토스케일링 레플리카 수 결정 기준")

    body = {"query": "그거 세 줄로 요약해줘", "route": "keyword_only", "history": _turns()}
    r = client.post("/search/answer", json=body, headers=_AUTH)
    assert r.status_code == 200, r.text

    assert seen["answer"]["query"] == "수평 파드 오토스케일링 레플리카 수 결정 기준"
    assert seen["answer"]["user_query"] == body["query"], (
        "답변자가 받은 사용자 문장이 요청 본문의 값과 다르다 — I3 는 문자열 동일이다")


@pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"),
                    reason="NEXUS_TEST_DB_URL 필요")
def test_search_receives_exactly_what_it_received_before(client, monkeypatch):
    """§4 I5. 시그니처가 아니라 **값**이다. U2 가 검색에 한 글자도 닿으면 안 된다."""
    seen: dict = {}
    _wire(monkeypatch, seen, rewritten="다시 쓴 질의")

    client.post("/search/answer",
                json={"query": "그거 세 줄로", "route": "keyword_only", "history": _turns()},
                headers=_AUTH)

    assert seen["search"]["query"] == "다시 쓴 질의"
    assert seen["search"]["channels"] == [("다시 쓴 질의", 1.3), ("그거 세 줄로", 0.5)]
    assert "user_query" not in seen["search"], "U2 의 값이 검색으로 샜다"


@pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"),
                    reason="NEXUS_TEST_DB_URL 필요")
def test_without_history_the_answerer_sees_no_second_sentence(client, monkeypatch):
    """§4 I1 을 표면에서. 이력이 없으면 재작성도 없고, 따로 줄 원문도 없다."""
    seen: dict = {}
    _wire(monkeypatch, seen, rewritten="쓰이지 않는다")

    client.post("/search/answer", json={"query": "레플리카 수", "route": "keyword_only"},
                headers=_AUTH)

    assert seen["answer"]["query"] == "레플리카 수"
    assert seen["answer"].get("user_query") in (None, "레플리카 수")


@pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"),
                    reason="NEXUS_TEST_DB_URL 필요")
def test_the_streaming_surface_is_wired_the_same_way(client, monkeypatch):
    """웹이 쓰는 것은 이 경로다. 비스트림만 고치면 사람이 보는 표면은 그대로 무시한다 —
    이 리포가 반복한 '사본이 정본 그물 밖' 이다."""
    seen: dict = {}
    _wire(monkeypatch, seen, rewritten="다시 쓴 질의")

    captured: dict = {}

    class _LLM:
        configured = True

        async def stream(self, system, user, usage_out=None):
            captured["system"], captured["user"] = system, user
            yield "답"

    monkeypatch.setattr("nexus.api.LLMService", lambda *a, **k: _LLM())

    with client.stream("POST", "/search/answer/stream",
                       json={"query": "그거 표로 정리해줘", "route": "keyword_only",
                             "history": _turns()},
                       headers=_AUTH) as r:
        assert r.status_code == 200
        for _ in r.iter_lines():
            pass

    assert "그거 표로 정리해줘" in captured["user"], "스트림 답변자가 사용자 문장을 못 받았다"
    assert "다시 쓴 질의" in captured["user"]
    assert captured["system"] != P.SYSTEM_PROMPT, "스트림에 역할 규칙이 안 붙었다"
