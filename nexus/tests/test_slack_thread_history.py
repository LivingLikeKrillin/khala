"""슬랙 스레드 이력 읽기 (SPEC-nexus-multi-turn-retrieval §1.3).

라이브 슬랙 없이 검사한다: `client` 는 우리가 만든 가짜이고, 그 가짜는 **입력에 반응한다** —
상수를 돌려주는 가짜는 정렬 어긋남을 원리적으로 통과시킨다(memory: suspect-the-instrument-first).
"""

from __future__ import annotations

import pytest

from nexus.search.history import MAX_BYTES, MAX_TURNS
from nexus.slack import thread as T


class _FakeSlack:
    """`conversations_replies` / `conversations_history` 만 흉내낸다."""

    def __init__(self, messages=None, error: Exception | None = None):
        self._messages = messages or []
        self._error = error
        self.calls: list[tuple[str, dict]] = []

    async def conversations_replies(self, **kw):
        return self._respond("replies", kw)

    async def conversations_history(self, **kw):
        return self._respond("history", kw)

    def _respond(self, name, kw):
        self.calls.append((name, kw))
        if self._error:
            raise self._error
        return {"messages": list(self._messages)}


def _msg(text, ts, *, bot=False, subtype=None):
    m = {"text": text, "ts": ts}
    if bot:
        m["bot_id"] = "B1"
    if subtype:
        m["subtype"] = subtype
    return m


# ── 어느 대화를 읽는가 ─────────────────────────────────────────────────────────

async def test_a_thread_reply_reads_the_thread():
    c = _FakeSlack([_msg("<@U1> 앞 질문", "1"), _msg("앞 답변", "2", bot=True)])
    turns = await T.read_history(c, {"channel": "C1", "ts": "3", "thread_ts": "1"})
    assert [t["content"] for t in turns] == ["앞 질문", "앞 답변"]
    assert c.calls[0][0] == "replies" and c.calls[0][1]["ts"] == "1"


async def test_a_dm_reads_the_channel_because_dms_have_no_threads():
    """DM 을 빼면 DM 사용자는 영원히 단발 질의만 한다 — 그리고 DM 이 가장 흔한 사용 방식이다."""
    c = _FakeSlack([_msg("이번 질문", "3"), _msg("앞 답변", "2", bot=True), _msg("앞 질문", "1")])
    turns = await T.read_history(c, {"channel": "D1", "ts": "3", "channel_type": "im"})
    assert c.calls[0][0] == "history"
    # conversations.history 는 최신순으로 준다 — 뒤집지 않으면 대화가 거꾸로 흐른다.
    assert [t["content"] for t in turns] == ["앞 질문", "앞 답변"]


async def test_a_first_mention_in_a_channel_has_no_history():
    c = _FakeSlack([_msg("무언가", "9")])
    assert await T.read_history(c, {"channel": "C1", "ts": "1"}) == []
    assert c.calls == [], "앞선 턴이 없는데 슬랙을 호출했다"


async def test_the_thread_root_itself_is_not_a_reply():
    """`thread_ts == ts` 는 스레드의 뿌리다 — 그 위에 앞선 턴은 없다."""
    c = _FakeSlack([_msg("x", "1")])
    assert await T.read_history(c, {"channel": "C1", "ts": "1", "thread_ts": "1"}) == []
    assert c.calls == []


# ── 무엇을 이력으로 세는가 ─────────────────────────────────────────────────────

async def test_this_question_is_not_its_own_history():
    """이번 메시지를 빼지 않으면 재작성기는 자기 자신을 맥락으로 읽는다."""
    c = _FakeSlack([_msg("앞 질문", "1"), _msg("<@U1> 이번 질문", "3")])
    turns = await T.read_history(c, {"channel": "C1", "ts": "3", "thread_ts": "1"})
    assert [t["content"] for t in turns] == ["앞 질문"]


def test_roles_follow_who_wrote_it():
    turns = T.to_turns([_msg("사람", "1"), _msg("봇", "2", bot=True)])
    assert [t["role"] for t in turns] == ["user", "assistant"]


def test_mentions_are_stripped_from_the_text():
    assert T.to_turns([_msg("<@U123> 결제 서비스 토픽", "1")])[0]["content"] == "결제 서비스 토픽"


def test_joins_and_uploads_are_not_conversation():
    turns = T.to_turns([_msg("왔습니다", "1", subtype="channel_join"),
                        _msg("", "2"), _msg("진짜 질문", "3")])
    assert [t["content"] for t in turns] == ["진짜 질문"]


# ── 상한 ──────────────────────────────────────────────────────────────────────

def test_the_caps_come_from_the_server_not_a_copy():
    """봇은 서버와 같은 파이썬이다 — 값을 옮겨 적을 이유가 없고, 옮겨 적으면 갈라진다."""
    from nexus.search import history as H

    # **바이트 상한이 이 검사의 하중을 진다.** 8192 는 인터닝되지 않으므로, 두 모듈이 각자
    # 계산했다면 `is` 가 거짓이다. 반면 MAX_TURNS(=8)는 작은 정수라 인터닝돼서 사본이어도
    # `is` 를 통과한다 — 그 자리에 identity 를 쓰면 아무것도 재지 않는 검사가 된다.
    assert T.MAX_BYTES is H.MAX_BYTES
    assert T.MAX_TURNS == H.MAX_TURNS


def test_only_the_most_recent_turns_survive_the_cap():
    msgs = [_msg(f"t{i}", str(i)) for i in range(20)]
    turns = T.to_turns(msgs)
    assert len(turns) == MAX_TURNS
    assert turns[-1]["content"] == "t19"      # 최근 맥락이 이번 질문을 푼다


def test_bytes_are_counted_so_one_long_answer_cannot_blow_the_cap():
    """답변은 길다. 턴 수만 세면 서버가 413 을 주고, 그러면 사용자는 답을 아예 못 받는다."""
    long = "가" * 4000                      # 12000 바이트
    turns = T.to_turns([_msg(long, "1"), _msg(long, "2", bot=True), _msg("짧은 질문", "3")])
    total = sum(len(t["content"].encode("utf-8")) for t in turns)
    assert total <= MAX_BYTES


# ── 읽을 수 없을 때 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("err", [
    RuntimeError("missing_scope"),          # 스코프 추가 후 재설치를 안 했다
    RuntimeError("ratelimited"),            # 후속 턴마다 호출이라 실제로 걸린다
])
async def test_history_failures_never_block_the_answer(err):
    """이력을 못 읽는 것은 **답변 실패가 아니다** — 이력 없이 답하면 오늘과 같은 동작이다."""
    c = _FakeSlack(error=err)
    assert await T.read_history(c, {"channel": "C1", "ts": "3", "thread_ts": "1"}) == []


# ── 배선: 읽은 이력이 실제로 서버까지 가는가 ────────────────────────────────────
#
# "함수는 맞는데 아무도 안 부른다" 가 이 리포의 최근 결함 넷 중 셋이었다. 그래서 여기서는
# 핸들러부터 HTTP 바디까지 **경로 전체**를 태운다.

import httpx  # noqa: E402

from nexus.slack import bot  # noqa: E402


def _capture(monkeypatch):
    seen = {}

    def handler(request):
        import json as _json
        seen["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"success": True, "data": {
            "answer": "답", "evidence_snippets": [{"doc_title": "t"}]}})

    monkeypatch.setattr(bot, "_transport", lambda: httpx.MockTransport(handler))
    monkeypatch.setattr(bot, "NEXUS_SLACK_TOKEN", "tok")
    return seen


async def test_a_thread_reply_sends_the_thread_as_history(monkeypatch):
    seen = _capture(monkeypatch)
    said = []

    async def say(**kw):
        said.append(kw)

    client = _FakeSlack([_msg("<@U1> 앞 질문", "1"), _msg("앞 답변", "2", bot=True)])
    await bot.handle_mention(
        {"text": "<@U1> 그럼 그건 어떻게 해?", "channel": "C1", "ts": "3", "thread_ts": "1"},
        say, client)

    assert seen["body"]["query"] == "그럼 그건 어떻게 해?"
    assert seen["body"]["history"] == [
        {"role": "user", "content": "앞 질문"},
        {"role": "assistant", "content": "앞 답변"},
    ]
    assert said, "답을 안 보냈다"


async def test_a_first_question_sends_an_empty_history(monkeypatch):
    """첫 턴은 이력이 없다 — 그리고 **오늘과 같은 요청**이어야 한다."""
    seen = _capture(monkeypatch)

    async def say(**kw):
        pass

    await bot.handle_mention({"text": "<@U1> 첫 질문", "channel": "C1", "ts": "1"},
                             say, _FakeSlack([]))
    assert seen["body"]["history"] == []


async def test_the_answer_still_goes_out_when_history_cannot_be_read(monkeypatch):
    """스코프가 없거나(재설치 안 함) 레이트리밋이면 이력 없이 답한다 — 답을 막지 않는다."""
    seen = _capture(monkeypatch)
    said = []

    async def say(**kw):
        said.append(kw)

    client = _FakeSlack(error=RuntimeError("missing_scope"))
    await bot.handle_mention({"text": "<@U1> 질문", "channel": "C1", "ts": "3", "thread_ts": "1"},
                             say, client)
    assert seen["body"]["history"] == []
    assert said, "이력을 못 읽었다고 답을 안 보냈다"


async def test_without_a_client_the_bot_behaves_exactly_as_before(monkeypatch):
    """`client` 없이 부르는 경로(옛 호출자·테스트)가 남아 있어도 깨지지 않는다."""
    seen = _capture(monkeypatch)

    async def say(**kw):
        pass

    await bot.handle_dm({"text": "질문", "channel": "D1", "ts": "1", "channel_type": "im"}, say)
    assert seen["body"]["history"] == []
