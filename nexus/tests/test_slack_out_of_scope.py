"""막다른 답에 **내가 아는 것**을 붙인다 — 그리고 붙이지 말아야 할 때 안 붙인다.

2026-08-14, 이 봇이 받은 실사용 투표는 둘뿐이고 **둘 다 👎 `not_found`** 였다. 시스템은 옳게
답했다(그 사실이 코퍼스에 없었다). 사용자가 받은 것은 막다른 문장 하나였고, 그 뒤로 질문이
오지 않았다.

여기서 지키는 것:
  · 근거 0건(사용자 몫) → 코퍼스 카드가 **붙는다**.
  · 코퍼스가 비었거나 등급 때문에 안 보이는 것(운영자 몫) → **안 붙는다**. 0건을 자랑하는
    카드가 되고, 사용자가 질문을 바꿔도 소용없는 상황에 방향 안내를 주는 것이기 때문이다.
  · 진단(`/visibility`)이 실패하면 → **안 붙는다**. 진단이 답변을 어지럽히지 않는다.
  · 근거는 있는데 잘 안 맞을 때(`weak_evidence`) → 카드가 아니라 **한 줄**. 근거 제목은
    이미 답변 아래 그려져 있다.

**핸들러를 통째로 돌린다.** 이 리포는 "단위 테스트는 초록인데 배선이 끊긴" 사고를 네 번 겪었다.
그래서 여기서는 `handle_mention` 이 실제로 게시한 블록을 본다.
"""

from __future__ import annotations

import httpx
import pytest

from nexus.slack import bot

_VIS = {
    "tenant": "default", "clearance": "INTERNAL",
    "documents_total": 116, "documents_visible": 116,
    "newest_document_at": "2026-08-11T14:31:50.682749+00:00",
    "sources": {"notion": 116},
    "sample_titles": ["로그인 정책", "파티 목록/개설 정책", "플레이리스트 정책"],
    "no_visible_documents": False,
}


def _wire(monkeypatch, *, snippets, vis=_VIS, docs=116, weak=False, visibility_fails=False):
    """봇 하나를 세운다 — `/search/answer` · `/status` · `/visibility` 를 URL 로 가른다."""
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/visibility" in url:
            if visibility_fails:
                raise httpx.ConnectError("visibility down")
            return httpx.Response(200, json={"success": True, "data": vis})
        if "/status" in url:
            return httpx.Response(200, json={"success": True, "data": {"documents_count": docs}})
        return httpx.Response(200, json={"success": True, "data": {
            "answer": "답", "evidence_snippets": snippets, "weak_evidence": weak}})

    monkeypatch.setattr(bot, "_transport", lambda: httpx.MockTransport(handler))
    monkeypatch.setattr(bot, "NEXUS_SLACK_TOKEN", "tok")


@pytest.fixture
def posted():
    """`say` 가 받은 kwargs 를 모은다. 사용자가 실제로 본 것이 여기 있다."""
    seen: list[dict] = []

    async def say(**kwargs):
        seen.append(kwargs)
        return {"ts": "1.0", "channel": "C1"}

    return seen, say


def _text_of(kwargs: dict) -> str:
    """게시된 블록 전체를 한 문자열로. 어느 블록에 실렸는지는 여기서 따지지 않는다."""
    out = [kwargs.get("text") or ""]
    for b in kwargs.get("blocks") or []:
        out.append(str(b))
    return "\n".join(out)


async def _ask(monkeypatch, posted, **wire):
    seen, say = posted
    _wire(monkeypatch, **wire)
    monkeypatch.setattr(bot.fb, "record_offer", lambda **_: None)
    await bot.handle_mention({"text": "<@U1> 질문", "channel": "C1", "ts": "1.0"}, say)
    return _text_of(seen[-1])


# ── 근거 0건: 사용자 몫이면 방향을 준다 ────────────────────────────────────────

async def test_no_evidence_gets_the_card_of_what_the_bot_does_know(monkeypatch, posted):
    body = await _ask(monkeypatch, posted, snippets=[])
    assert "찾지 못했습니다" in body, "원래 문장이 사라지면 안 된다"
    assert "제가 가진 문서 밖입니다" in body
    assert "로그인 정책" in body, "무엇을 물을 수 있는지 알려주는 것이 카드의 전부다"
    assert "Notion 116건" in body


async def test_an_empty_corpus_gets_no_card(monkeypatch, posted):
    """운영자 몫이다. 여기서 '제가 아는 것은…' 은 0건을 자랑하는 카드가 된다."""
    body = await _ask(monkeypatch, posted, snippets=[], docs=0)
    assert "제가 가진 문서 밖입니다" not in body


async def test_a_blind_bot_gets_no_card(monkeypatch, posted):
    """등급 설정 결함 — 질문을 바꿔도 영원히 0건이므로 방향 안내는 거짓 위로다."""
    blind = {**_VIS, "no_visible_documents": True, "documents_visible": 0}
    body = await _ask(monkeypatch, posted, snippets=[], vis=blind)
    assert "제가 가진 문서 밖입니다" not in body


async def test_a_failed_diagnostic_stays_silent(monkeypatch, posted):
    """진단이 죽어도 원래 답은 그대로 나간다 — 진단이 답변을 어지럽히지 않는다."""
    body = await _ask(monkeypatch, posted, snippets=[], visibility_fails=True)
    assert "찾지 못했습니다" in body
    assert "제가 가진 문서 밖입니다" not in body


# ── 근거는 있는데 잘 안 맞을 때: 카드가 아니라 한 줄 ───────────────────────────

async def test_weak_evidence_gets_one_line_not_the_card(monkeypatch, posted):
    body = await _ask(monkeypatch, posted, snippets=[{"doc_title": "t"}], weak=True)
    assert "제가 가진 것은 Notion 116건" in body
    assert "이런 문서들입니다" not in body, "제목은 이미 근거 블록에 있다 — 두 번 말하지 않는다"


async def test_a_good_answer_gets_nothing_extra(monkeypatch, posted):
    """**스위치가 진짜 가르는지** 먼저 확인한다. 늘 붙는 꼬리표는 신호가 아니다."""
    body = await _ask(monkeypatch, posted, snippets=[{"doc_title": "t"}], weak=False)
    assert "제가 가진 것은" not in body
    assert "제가 가진 문서 밖입니다" not in body
