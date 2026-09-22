"""적합도 계약은 **두 표면에 다 붙는다**, 그리고 판정과 **함께 근거를 낸다**.

⛔ **왜 생겼나 (실측 2026-09-22).** 설명 층이 물었다 — 인용이 붙은 답에서도 `weak_evidence`
가 유효한 판정인가. 계약을 읽으러 갔다가 둘을 찾았다.

**하나.** 스트리밍 경로의 `build_prompts` 호출이 `weak_evidence` 를 안 넘겼다. 인자에 기본값이
있으므로 **조용히 「약하지 않다」로 떨어졌다.** 그래서 `search/confidence.py` 가 막으려던 바로
그 실패 — 이름을 물었는데 근거를 채워 표를 길게 답하는 것 — 이 **사람이 보는 표면**에서
그대로 살아 있었다. 계약을 지킨 것은 비스트림뿐이었다.

⚠ `build_prompts` 머리말이 이미 적어 뒀다: *"둘을 따로 조립하면 … 테스트가 초록인 채로
프로덕션에서 조용히 틀린다."* 이번 구멍은 따로 조립한 것이 아니라 **기본값**이었다. 그리고
`docs/EMPTY_OR_FAILED_READBACK_AUDIT.md` §5 가 안 센 방법으로 `기본 인자` 를 **이름만** 적어
뒀다 — 여기가 그 실물이다.

**둘.** 그 표면에는 `weak_evidence` 자체도 안 실렸고, 비스트림은 판정만 싣고 **근거인 두 수**
(`top_distance`·`top_bm25`)를 안 실었다. 소비자는 문턱에 **겨우 걸린 것**과 한참 밖인 것을
못 가른다. 그리고 그 문턱(0.48 / 1.5)은 아직 가설이라, 옮길 트리거는 *중간 구간에서 발동한
질의*다 — 그것을 볼 수 있는 쪽은 질의를 지은 소비자이고 서버가 아니다.

⭐ 비스트림 응답의 주석이 이미 한 층 위에서 같은 문장을 적고 있었다: *"이 값이 응답에 없는
동안 표면들은 「잘 찾았다」와 「제일 덜 나쁜 걸 골랐다」를 구별할 수 없었고, 서버는 프롬프트만
바꾸고 그 사실을 혼자 알고 있었다."* 한 층 아래에서 같은 일이 나고 있었다.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.api import app  # noqa: E402
from nexus.llm import prompts as P  # noqa: E402
from nexus.search.confidence import Confidence  # noqa: E402

_TOKEN = "x" * 40
_AUTH = {"Authorization": "Bearer " + _TOKEN}

#: `Confidence.weak` 가 참이 되는 유일한 조합 — **둘 다** 약해야 한다.
_WEAK = Confidence(top_distance=0.561, top_bm25=0.4)
#: 대조군. 벡터는 멀지만 키워드가 잡았다 ⇒ 약하지 않다.
_NOT_WEAK = Confidence(top_distance=0.561, top_bm25=4.1)


@pytest.fixture
def client(monkeypatch):
    """풀을 되돌린다 — `TestClient` 의 루프가 닫히면 모듈 전역 asyncpg 풀이 죽은 식별자가
    되고 다음 테스트가 그것을 집어 죽는다(`test_narration_user_query.py` 와 같은 이유)."""
    from nexus import db

    monkeypatch.setenv("NEXUS_DEV_TOKEN", _TOKEN)
    saved = db._pool
    try:
        yield TestClient(app)
    finally:
        db._pool = saved


def _wire(monkeypatch, confidence: Confidence) -> dict:
    """검색이 그 적합도를 들고 오게 세우고, 답변자가 받은 프롬프트를 받아 적는다."""
    from nexus.search.hybrid import SearchHit, SearchResult

    captured: dict = {}

    async def one_hit(*a, **k):
        r = SearchResult(hits=[SearchHit(rid="c1", doc_rid="d1", doc_title="문서",
                                         chunk_text="근거 본문", score=0.9)],
                         route_used="keyword_only", timing_ms={"total_ms": 1})
        r.confidence = confidence
        return r
    monkeypatch.setattr("nexus.api.hybrid_search", one_hit)

    async def no_signal(*a, **k):
        return None
    monkeypatch.setattr("nexus.api.record_search", no_signal)

    class _LLM:
        """두 표면이 **다른 메서드**를 부른다 — 하나만 세우면 그 표면만 검사한다."""

        configured = True

        async def stream(self, system, user, usage_out=None):
            captured["system"] = system
            yield "답"

        async def generate_full(self, system, user):
            from nexus.providers.llm import LLMResult, Usage

            captured["system"] = system
            return LLMResult(text="답", usage=Usage(None, None, None, "테스트-모델"))

    monkeypatch.setattr("nexus.api.LLMService", lambda *a, **k: _LLM())
    return captured


def _stream(client, captured: dict) -> dict:
    """스트림을 끝까지 태우고 `done` 본문을 돌려준다."""
    done: dict = {}
    with client.stream("POST", "/search/answer/stream",
                       json={"query": "이 시스템에 없는 것을 묻는다", "route": "keyword_only"},
                       headers=_AUTH) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("data: ") and "timing_ms" in line:
                done = json.loads(line[6:])
    return done


# ── 하나 — 계약이 붙는다 ──────────────────────────────────────────────────────

@pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"),
                    reason="NEXUS_TEST_DB_URL 필요 — 답변 경로를 끝까지 태워야 한다")
def test_the_streaming_surface_actually_gets_the_weak_evidence_rule(client, monkeypatch):
    """⛔ **이것이 빠져 있던 동안 웹 채팅은 계약 밖이었다.**

    표현이 아니라 **행동**을 단언한다 — 호출 인자를 세는 것이 아니라, 모델이 실제로 받은
    시스템 프롬프트에 규칙이 들어 있는지 본다.
    """
    captured = _wire(monkeypatch, _WEAK)
    _stream(client, captured)

    assert P.WEAK_EVIDENCE_RULE in captured["system"], \
        "스트림 답변자가 적합도 규칙을 못 받았다 — 기본 인자가 「약하지 않다」로 떨어졌다"


@pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"),
                    reason="NEXUS_TEST_DB_URL 필요")
def test_a_search_that_matched_well_gets_no_such_rule(client, monkeypatch):
    """⛔ **대조군이 없으면 「늘 붙인다」도 초록이다.**

    그리고 늘 붙이는 것은 고장이다 — 정상 답변의 절반이 '코퍼스 밖' 으로 찍힌다.
    """
    captured = _wire(monkeypatch, _NOT_WEAK)
    _stream(client, captured)

    assert P.WEAK_EVIDENCE_RULE not in captured["system"], \
        "잘 맞은 검색에까지 적합도 규칙이 붙었다"


# ── 둘 — 판정과 근거가 **같이** 나간다 ────────────────────────────────────────

@pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"),
                    reason="NEXUS_TEST_DB_URL 필요")
def test_the_streaming_done_event_carries_the_verdict_and_its_basis(client, monkeypatch):
    """이 표면에는 판정 자체가 없었다 — 짧은 답을 받으면서 왜 짧은지 알 길이 없었다."""
    captured = _wire(monkeypatch, _WEAK)
    done = _stream(client, captured)

    assert done.get("weak_evidence") is True, "스트림 done 에 판정이 없다"
    assert done.get("top_distance") == pytest.approx(0.561), "판정의 근거가 안 실린다"
    assert done.get("top_bm25") == pytest.approx(0.4)


@pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"),
                    reason="NEXUS_TEST_DB_URL 필요")
def test_the_non_streaming_surface_ships_the_basis_too(client, monkeypatch):
    """⛔ **한 표면만 고치면 그 표면의 소비자만 조용히 못 본다** — 이 파일의 주제다."""
    _wire(monkeypatch, _WEAK)
    # ⚠ 이 표면은 `NexusResponse` 로 감싸므로 값은 `data` 아래에 있다. 스트림은 안 감싼다.
    body = client.post("/search/answer",
                       json={"query": "이 시스템에 없는 것을 묻는다", "route": "keyword_only"},
                       headers=_AUTH).json()["data"]

    assert body.get("weak_evidence") is True, "판정부터 안 나온다"
    assert body.get("top_distance") == pytest.approx(0.561)
    assert body.get("top_bm25") == pytest.approx(0.4)


# ── 계약 자체 — 판정은 인용과 무관하다 ───────────────────────────────────────

def test_the_verdict_is_computed_from_search_scores_not_from_citations():
    """⭐ **설명 층이 막혀 있던 자리다.** 분류기가 `weak_evidence` 를 「인용 0건일 때만」
    봤고, 그래서 **뒤에 나온 것으로 앞의 것을 가리고** 있었다.

    `Confidence` 는 인용을 입력으로 받지 않는다 — 받을 수가 없다. 이 값은 생성 **전에**
    정해져 프롬프트로 들어가고, 인용은 생성의 **산출**이다.
    """
    assert _WEAK.weak is True
    assert "citation" not in str(Confidence.__dataclass_fields__.keys())
    assert set(Confidence.__dataclass_fields__) == {"top_distance", "top_bm25"}


def test_the_rule_is_what_puts_a_citation_on_a_weak_answer():
    """⭐ **`weak=참 · 인용 1` 은 예외가 아니라 설계된 출력이다.**

    규칙 2항이 관련 문서의 **제목 한 줄**을 시키고, 제목을 알리면 인용이 하나 생긴다.
    이것을 모르면 「모른다고 말한 답」이 정상 답으로 세어진다.
    """
    assert "제목만" in P.WEAK_EVIDENCE_RULE
    assert "짧게 끝내세요" in P.WEAK_EVIDENCE_RULE


def test_a_path_that_did_not_report_is_not_a_weak_one():
    """`None` 은 **못 낸 것**이지 0 이 아니다 — 이 리포가 반복해서 찾아낸 혼동이다."""
    assert Confidence(top_distance=None, top_bm25=0.1).weak is False
    assert Confidence(top_distance=0.9, top_bm25=None).weak is False
