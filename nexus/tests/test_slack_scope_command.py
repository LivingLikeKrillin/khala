"""봇에게 봇 자신을 물었을 때 — 검색이 아니라 시스템 상태로 답하는가.

2026-08-13 에 팀원이 물었다: *"너가 근거로 사용 중인 corpus 범위는 어떻게 돼?"* 봇은 그것을
평범한 질문으로 받아 검색했고, 코퍼스를 논하는 설계 문서 다섯 건을 근거로 "이번 검색에서
Evidence 로 제공된 문서는 5개" 라고 답했다. 그건 코퍼스 범위가 아니라 그 턴의 근거 패킷이다.

**분류는 하지 않는다.** "메타 질문인가?" 를 모델이 판정하는 설계는
SPEC-nexus-multi-turn-narration §3.2 에서 기각됐다(오분류가 양방향으로 안전하지 않다).
여기서는 **완전 일치**만 쓴다 — 그래서 이 파일의 절반은 "명령이 아닌 것" 검사다.
"""

from __future__ import annotations

import httpx
import pytest

from nexus.slack import bot
from nexus.slack.commands import is_scope_command, scope_blocks

_VIS = {
    "tenant": "default", "clearance": "INTERNAL",
    "documents_total": 116, "documents_visible": 116,
    "newest_document_at": "2026-08-11T14:31:50.682749+00:00",
    "sources": {"notion": 116},
    "sample_titles": ["로그인 정책", "파티 목록/개설 정책", "플레이리스트 정책"],
    "no_visible_documents": False,
}


# ── 무엇이 명령인가 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", ["코퍼스", "corpus", "범위", "Corpus", " 코퍼스 ", "코퍼스?", "scope"])
def test_the_short_forms_are_commands(text):
    assert is_scope_command(text) is True


@pytest.mark.parametrize("text", [
    "corpus 설계가 어떻게 돼?",          # 진짜 질문 — 가로채면 고치기 전보다 나빠진다
    "범위 밖의 문서는 어떻게 추가해?",
    "코퍼스에 노션 페이지 더 넣어줘",
    "우리 팀 스코프가 어디까지야",
    "",
])
def test_a_real_question_is_not_a_command(text):
    """**부분 문자열이 아니라 완전 일치다.** 이 검사가 없으면 명령어가 질문을 잡아먹는다."""
    assert is_scope_command(text) is False


# ── 카드가 묻는 사람의 질문에 답하는가 ─────────────────────────────────────────

def test_the_card_leads_with_where_the_documents_came_from():
    """팀원이 알고 싶은 것은 개수가 아니라 *"내가 뭘 물어봐도 되냐"* 다."""
    text = scope_blocks(_VIS)[0]["text"]["text"]
    assert "Notion" in text
    assert "로그인 정책" in text, "무엇에 대한 코퍼스인지 예시가 없다"
    assert "2026-08-11" in text, "언제 것인지가 없으면 신뢰 판단을 못 한다"


def test_the_card_does_not_lead_with_internal_vocabulary():
    """`default`·`INTERNAL` 은 시스템의 어휘다 — 묻는 사람에게 아무 뜻이 없다.

    첫 판이 그 둘을 앞세웠고, 그건 운영자의 질문에 답한 것이었다.
    """
    first_line = scope_blocks(_VIS)[0]["text"]["text"].splitlines()[0]
    assert "default" not in first_line and "INTERNAL" not in first_line


def test_the_card_says_what_it_does_not_know():
    """신뢰를 가르는 것은 무엇을 아는지가 아니라 **무엇을 모르는지**다."""
    assert "모릅니다" in scope_blocks(_VIS)[0]["text"]["text"]


def test_the_card_never_claims_to_be_a_search_result():
    assert "검색 결과가 아니라" in scope_blocks(_VIS)[0]["text"]["text"]


def test_a_clearance_gap_is_named_because_hidden_is_not_absent():
    """차이를 모르면 "코퍼스에 없다" 로 오해한다. 없는 게 아니라 안 보이는 것이다."""
    text = scope_blocks({**_VIS, "documents_total": 116, "documents_visible": 108})[0]["text"]["text"]
    assert "8건" in text and "보이지 않습니다" in text


def test_no_visible_documents_is_an_operator_message():
    text = scope_blocks({**_VIS, "documents_visible": 0, "no_visible_documents": True})[0]["text"]["text"]
    assert "운영자" in text
    assert "로그인 정책" not in text, "볼 수 없는데 예시를 보여주면 거짓이다"


def test_a_failed_probe_still_produces_a_card():
    """`/visibility` 가 죽어도 봇이 죽으면 안 된다 — 빈 dict 로 온다."""
    assert scope_blocks({})[0]["text"]["type"] == "mrkdwn"


# ── 배선: 봇이 실제로 그 카드를 보내는가 ───────────────────────────────────────

async def test_the_bot_answers_the_command_without_searching(monkeypatch):
    """검색을 타면 안 된다 — 그게 이 기능이 존재하는 이유다."""
    searched = []

    def handler(request):
        searched.append(str(request.url))
        if request.url.path == "/visibility":
            return httpx.Response(200, json={"success": True, "data": _VIS})
        return httpx.Response(200, json={"success": True, "data": {
            "answer": "검색이 돌았다", "evidence_snippets": [{"doc_title": "t"}]}})

    monkeypatch.setattr(bot, "_transport", lambda: httpx.MockTransport(handler))
    monkeypatch.setattr(bot, "NEXUS_SLACK_TOKEN", "tok")

    said = []

    async def say(**kw):
        said.append(kw)

    await bot.handle_mention({"text": "<@U1> 코퍼스", "channel": "C1", "ts": "1"}, say)

    assert said, "아무 답도 안 보냈다"
    text = said[0]["blocks"][0]["text"]["text"]
    assert "Notion" in text
    assert all("/search" not in u for u in searched), f"검색을 탔다: {searched}"


async def test_a_normal_question_still_goes_to_search(monkeypatch):
    """명령어 경로가 평범한 질문을 삼키면, 고치기 전보다 나빠진다."""
    searched = []

    def handler(request):
        searched.append(request.url.path)
        return httpx.Response(200, json={"success": True, "data": {
            "answer": "답", "evidence_snippets": [{"doc_title": "t"}]}})

    monkeypatch.setattr(bot, "_transport", lambda: httpx.MockTransport(handler))
    monkeypatch.setattr(bot, "NEXUS_SLACK_TOKEN", "tok")

    async def say(**kw):
        pass

    await bot.handle_mention({"text": "<@U1> 로그인 정책 알려줘", "channel": "C1", "ts": "1"}, say)
    assert "/search/answer" in searched
