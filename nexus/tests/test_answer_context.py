"""`answer_context` — **답변 프롬프트에만** 들어가는 요청자의 자료. 검색에는 안 닿는다.

⛔ **왜 생겼나 (2026-09-27, 설명 레이어 자문).** 진단 경로는 후보 목록(별칭 · 식별자 · 대상)을 답에
넘겨야 한다. 그런데 요청에는 `query` 하나뿐이라, 후보를 거기 실으면 그 글이 **BM25 · 벡터 ·
식별자 채널 · 재작성기에 다 들어간다** — 검색이 측정해 온 경로가 달라지고, 후보 이름이 답변 근거
순위를 끌고 간다. 검색에 쓰는 글과 답에 보여 줄 글은 다른 것이다.

계약(편지 15, 소유자 승인 2026-09-30):
- 문자열 하나, 상한 8,000 글자 — 넘으면 **422** 이고 조용히 자르지 않는다
- 사용자 프롬프트 안, 질문 다음 · 답변 근거 앞의 **표시된 절**
- 닿지 않는 곳: 검색(BM25 · 벡터 · 식별자 채널) · 재작성기 · 충분성 판정자 · 질문 원문 보존
- 기록은 길이와 해시만. `/search` 는 받지 않는다(422)
- 없으면 프롬프트 바이트가 오늘과 같다
- 숫자 검증의 `grounded` 는 「모델에게 보여 준 것 어딘가」 — 이 자료도 그 안이다
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus import api  # noqa: E402
from nexus.llm import prompts as P  # noqa: E402

_TOKEN = "x" * 40
_AUTH = {"Authorization": "Bearer " + _TOKEN}
_EVIDENCE = "## 검색된 근거 (Evidence)\n\n### 근거 1 [절차서] (§4)\n정원은 30 이다."
_CONTEXT = "후보\nA · picking-arm-2 · 파지 실패 재시도 한도 17\nB · agv-7 · 경로 차단"


# ── 프롬프트 ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("absent", [None, "", "   \n "], ids=["none", "empty", "blank"])
def test_without_a_context_the_prompt_is_todays_byte_for_byte(absent):
    """평가 팩·대조군이 오늘 프롬프트에서 돈다 — 안 준 요청의 바이트가 바뀌면 비교가 끊긴다."""
    assert P.build_user_prompt("질문", _EVIDENCE, answer_context=absent) == \
        P.build_user_prompt("질문", _EVIDENCE)
    assert P.build_user_prompt("찾은 질의", _EVIDENCE, "원래 질문", answer_context=absent) == \
        P.build_user_prompt("찾은 질의", _EVIDENCE, "원래 질문")


def test_the_context_sits_between_the_question_and_the_evidence():
    out = P.build_user_prompt("질문", _EVIDENCE, answer_context=_CONTEXT)
    q, h, c, e = (out.index("## 사용자 질문"), out.index(P.ANSWER_CONTEXT_HEADER),
                  out.index(_CONTEXT), out.index(_EVIDENCE))
    assert q < h < c < e, "절의 자리가 질문 다음 · 근거 앞이 아니다"


def test_the_section_says_what_it_is_and_what_it_cannot_do():
    """자료이지 답변 근거가 아니다 — 인용하지 말 것, 별칭으로 가리킬 것, 핵심 규칙을 못 이긴다는 것."""
    out = P.build_user_prompt("질문", _EVIDENCE, answer_context=_CONTEXT)
    assert P.ANSWER_CONTEXT_RULE in out
    for must in ("인용하지 마세요", "별칭", "핵심 규칙"):
        assert must in P.ANSWER_CONTEXT_RULE, f"절 머리말에 「{must}」가 없다"
    assert out.rstrip().endswith(P.ANSWER_CONTEXT_CLOSING), "닫는 문장이 끝에 없다"


def test_the_two_sentence_turn_keeps_its_order_too():
    out = P.build_user_prompt("찾은 질의", _EVIDENCE, "원래 질문", answer_context=_CONTEXT)
    order = [out.index(s) for s in ("## 사용자 질문", "## 검색에 사용한 질의",
                                    P.ANSWER_CONTEXT_HEADER, _EVIDENCE)]
    assert order == sorted(order)


def test_the_system_prompt_is_not_touched():
    """규칙은 절 머리말에 있다 — 시스템 프롬프트를 바꾸면 자료가 없는 요청까지 바뀐다."""
    sys_with, _ = P.build_prompts("질문", _EVIDENCE, answer_context=_CONTEXT)
    sys_without, _ = P.build_prompts("질문", _EVIDENCE)
    assert sys_with == sys_without


# ── 숫자 검증 — 보여 준 것은 지어낸 것이 아니다 ─────────────────────────────────

def test_a_number_the_model_was_shown_in_the_context_is_grounded():
    """자료에서 옮겨 적은 수를 「지어낸 수」로 세면 `unverified_numbers` 가 뜻을 잃는다."""
    from nexus.llm.numbers import validate_numbers

    report = validate_numbers("재시도 한도는 17 회입니다", _EVIDENCE, "질문", context=_CONTEXT)
    assert [(n.value, n.grounded) for n in report.numbers] == [("17", True)]
    assert validate_numbers("재시도 한도는 17 회입니다", _EVIDENCE, "질문").unverified_count == 1


# ── 요청 경계 ─────────────────────────────────────────────────────────────────

class _LLM:
    """두 API 표면이 **다른 메서드**를 부른다 — 받은 프롬프트를 적어 둔다."""

    configured = True

    def __init__(self, seen: dict, answer: str):
        self.seen, self.answer = seen, answer

    async def generate_full(self, system, user):
        from nexus.providers.llm import LLMResult, Usage

        self.seen["user"] = user
        return LLMResult(text=self.answer, usage=Usage(None, None, None, "테스트-모델"))

    async def stream(self, system, user, usage_out=None):
        from nexus.providers.llm import Usage

        self.seen["user"] = user
        yield self.answer
        if usage_out is not None:
            usage_out.append(Usage(None, None, None, "테스트-모델"))


@pytest.fixture
def wired(monkeypatch):
    """DB·임베딩 없이 두 엔드포인트의 본문을 돌린다. 답변 근거 한 조각짜리 근거 묶음을 접합부 자리에 둔다.

    받아 적는 것: 검색이 받은 인자 · 모델이 받은 사용자 프롬프트 · 기록될 신호와 판정자 입력."""
    from nexus import db
    from nexus.search.evidence_packet import EvidencePacket, EvidenceSnippet
    from nexus.search.hybrid import SearchResult

    monkeypatch.setenv("NEXUS_DEV_TOKEN", _TOKEN)
    seen: dict = {"search": [], "rows": [], "judge": [], "query_text": []}

    async def _noop_async(*a, **k):
        return None

    async def _search(*a, **k):
        seen["search"].append((a, k))
        return SearchResult(route_used="keyword_only", timing_ms={"total_ms": 1})

    async def _packet(*a, **k):
        return EvidencePacket(snippets=[EvidenceSnippet(
            chunk_rid="c1", doc_rid="d1", doc_title="절차서", section_path="§4",
            source_uri="t:sop.md", text="정원은 30 이다.", score=1.0,
            classification="INTERNAL", full_text="정원은 30 이다.")],
            searched_tenants=["default"], prompt_version="a1b2c3d4e5f6")

    async def _record(sig, judge_input=None, **k):
        seen["rows"].append(sig)
        seen["judge"].append(judge_input)
        seen["query_text"].append(k.get("query_text"))

    monkeypatch.setattr(api, "_load_config", lambda *a, **k: {})
    monkeypatch.setattr(api, "embedding_service_from_config", lambda *a, **k: None)
    monkeypatch.setattr(api.db, "get_pool", _noop_async)
    monkeypatch.setattr(api, "PostgresGraphRepository", lambda *a, **k: None)
    monkeypatch.setattr(api, "_load_gazetteer", lambda *a, **k: {})
    monkeypatch.setattr(api, "_build_entity_patterns", lambda *a, **k: {})
    monkeypatch.setattr(api, "find_entities_in_text", lambda *a, **k: [])
    monkeypatch.setattr(api, "hybrid_search", _search)
    monkeypatch.setattr(api, "packet_for_answer", _packet)
    monkeypatch.setattr(api, "record_search", _record)

    def llm(answer="권고: A\n이유: 재시도 한도 17 을 넘었다 [출처: 절차서, §4]"):
        monkeypatch.setattr(api, "LLMService", lambda *a, **k: _LLM(seen, answer))

    llm()
    saved = db._pool
    try:
        yield TestClient(api.app), seen, llm
    finally:
        db._pool = saved


def _answer(client, **body):
    return client.post("/search/answer", json={"query": "파지 실패 원인", **body}, headers=_AUTH)


def _stream(client, **body) -> dict:
    done, event = {}, ""
    with client.stream("POST", "/search/answer/stream",
                       json={"query": "파지 실패 원인", **body}, headers=_AUTH) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: ") and event == "done":
                done = json.loads(line[6:])
    return done


@pytest.mark.parametrize("surface", ["answer", "stream"])
def test_both_answer_surfaces_put_it_in_front_of_the_model(wired, surface):
    """⛔ **한 경로만 받으면 조용히 갈린다**(A44). 웹 채팅은 스트림을, 진단 경로는 비스트림을 탄다."""
    client, seen, _ = wired
    if surface == "answer":
        assert _answer(client, answer_context=_CONTEXT).status_code == 200
    else:
        _stream(client, answer_context=_CONTEXT)
    assert _CONTEXT in seen["user"], "모델이 자료를 못 받았다"
    assert P.ANSWER_CONTEXT_HEADER in seen["user"]


@pytest.mark.parametrize("surface", ["answer", "stream"])
def test_it_never_reaches_search_rewrite_judge_or_retention(wired, surface):
    """자료가 검색에 들어가면 이 필드를 만든 이유가 통째로 사라진다."""
    client, seen, _ = wired
    if surface == "answer":
        _answer(client, answer_context=_CONTEXT)
    else:
        _stream(client, answer_context=_CONTEXT)
    blob = repr(seen["search"])
    assert "picking-arm-2" not in blob, "자료가 검색 인자에 들어갔다"
    assert seen["query_text"] == ["파지 실패 원인"], "보존되는 질문 원문에 자료가 섞였다"
    for judge in seen["judge"]:
        if judge is not None:
            assert "picking-arm-2" not in judge.evidence and "picking-arm-2" not in judge.query
    assert "picking-arm-2" not in repr(seen["rows"]), "기록 신호에 자료 본문이 실렸다"


@pytest.mark.parametrize("surface", ["answer", "stream"])
def test_the_record_keeps_only_its_length_and_hash(wired, surface):
    client, seen, _ = wired
    if surface == "answer":
        _answer(client, answer_context=_CONTEXT)
    else:
        _stream(client, answer_context=_CONTEXT)
    (row,) = seen["rows"]
    assert row.answer_context_len == len(_CONTEXT)
    assert row.answer_context_sha256 == hashlib.sha256(_CONTEXT.encode("utf-8")).hexdigest()


def test_a_request_without_it_records_nothing_and_sends_todays_prompt(wired):
    client, seen, _ = wired
    _answer(client)
    (row,) = seen["rows"]
    assert (row.answer_context_len, row.answer_context_sha256) == (0, "")
    assert P.ANSWER_CONTEXT_HEADER not in seen["user"]


@pytest.mark.parametrize("surface", ["answer", "stream"])
def test_the_response_says_how_much_of_it_was_used(wired, surface):
    """⭐ **받았다는 것을 응답이 말한다.** 알 수 없는 필드의 422 는 「이름이 틀렸다」만 막는다 — 필드가
    선 뒤에 빈 문자열이 오면 그것은 조용히 「안 준 것」이 되고, 호출자는 그 차이를 못 본다."""
    client, _, _ = wired
    if surface == "answer":
        data = _answer(client, answer_context=_CONTEXT).json()["data"]
    else:
        data = _stream(client, answer_context=_CONTEXT)
    assert data.get("answer_context_len") == len(_CONTEXT)


@pytest.mark.parametrize("surface", ["answer", "stream"])
def test_a_number_copied_from_it_is_not_counted_as_made_up(wired, surface):
    client, _, _ = wired
    if surface == "answer":
        data = _answer(client, answer_context=_CONTEXT).json()["data"]
    else:
        data = _stream(client, answer_context=_CONTEXT)
    assert data["numbers"] == [{"value": "17", "grounded": True, "found_in": ["context"]}]
    assert data["unverified_numbers"] == 0


def test_the_cap_is_refused_not_trimmed(wired):
    """조용히 자르면 호출자는 무엇이 빠졌는지 모른 채 틀린 판단을 받는다."""
    client, seen, _ = wired
    over = _answer(client, answer_context="가" * (api.ANSWER_CONTEXT_MAX + 1))
    assert over.status_code == 422
    err = over.json()["detail"][0]
    assert err["loc"] == ["body", "answer_context"]
    assert err["ctx"]["max_length"] == api.ANSWER_CONTEXT_MAX == 8000, "상한이 본문에 없다"
    assert seen["search"] == [], "거절한 요청이 검색까지 갔다"
    assert _answer(client, answer_context="가" * api.ANSWER_CONTEXT_MAX).status_code == 200


def test_the_search_only_route_refuses_it(wired):
    """`/search` 는 답을 안 만든다 — 받는 척하면 그 자료는 아무 데도 안 간다."""
    client, _, _ = wired
    r = client.post("/search", json={"query": "q", "answer_context": _CONTEXT}, headers=_AUTH)
    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "extra_forbidden"
