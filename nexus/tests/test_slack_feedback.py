"""슬랙 피드백 표면 (SPEC-nexus-answer-feedback U2, approved 2026-08-14, 안 B).

버튼 둘, 👎 면 사유 넷, 그리고 **운영자에게만** DM. 공개 표시는 하지 않는다 — 봇은
`thread_ts` 로 채널 스레드에 답하므로 깃발을 꽂으면 5명 팀에서 질문자가 지목되고, 그것은
스키마에서 지운 연결을 **슬랙 UI 가 공개로 복원**하는 것이다.

지키는 것 (SPEC §4):

  I4   슬랙 사용자 id 는 **어디에도** 기록되지 않는다 — 로그 포함
  I6   피드백 실패가 답변을 죽이지 않는다
  I8   블록 예산: 메시지당 50 · actions 당 요소 25 · 텍스트 객체 3000자
  I11  운영자 DM 에 질의·답변 본문이 없다 (퍼머링크와 사유 코드만)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.slack import feedback as FB  # noqa: E402

_KEY, _VOTE = "kEy123abcKEY123abcKE", "vOte456defVOTE456def"
_CH, _TS, _USER = "C123", "1700000000.000100", "U_SECRET_USER"


def _payload(action_id: str, value: str) -> dict:
    """실제 `block_actions` 페이로드 모양 — **user id 가 같은 객체에 들어 있다.**"""
    return {
        "user": {"id": _USER},
        "channel": {"id": _CH},
        "message": {"ts": _TS},
        "actions": [{"action_id": action_id, "value": value}],
    }


class _Client:
    def __init__(self):
        self.ephemeral, self.dms, self.opened = [], [], []

    async def chat_postEphemeral(self, **kw):
        self.ephemeral.append(kw)

    async def chat_postMessage(self, **kw):
        self.dms.append(kw)

    async def chat_getPermalink(self, **kw):
        self.opened.append(kw)
        return {"permalink": "https://example.slack.com/archives/C123/p1700000000000100"}


# ── 블록 예산 (I8) ────────────────────────────────────────────────────────────

def test_the_feedback_blocks_fit_every_named_slack_limit():
    """**어느 상한에 걸리는지는 선언하지 않고 잰다.** 이 리포는 3000자 상한으로 첫 실사용
    질문이 `invalid_blocks` 로 죽은 전례가 있고, 이번에 붙는 블록이 걸릴 상한은 그것이 아니라
    블록 수·요소 수 쪽이다 — 그래서 셋을 전부 단언한다."""
    blocks = FB.feedback_blocks(_KEY)

    assert len(blocks) <= 50
    for b in blocks:
        if b["type"] == "actions":
            assert len(b["elements"]) <= 25
        for text in FB._texts(b):
            assert len(text) <= 3000


def test_the_answer_plus_feedback_still_fits_at_the_evidence_ceiling():
    """근거가 상한(`top_k`)만큼 붙은 답변에 버튼을 얹어도 메시지가 산다.

    `formatter` 의 블록 수는 근거 건수에 따라 변하므로 임의 표본으로는 보증이 안 된다.
    """
    from nexus.slack.formatter import format_answer

    data = {"answer": "답" * 2000,
            "evidence_snippets": [{"doc_title": "문서" * 50, "section_path": "절",
                                   "text": "본문" * 100, "score": 0.9}
                                  for _ in range(FB.EVIDENCE_CEILING)]}
    blocks = format_answer(data) + FB.feedback_blocks(_KEY)

    assert len(blocks) <= 50, f"블록 {len(blocks)}개 — 메시지 상한 초과"
    for b in blocks:
        for text in FB._texts(b):
            assert len(text) <= 3000


def test_the_reason_prompt_offers_exactly_the_four_codes():
    from nexus.feedback.store import REASONS

    blocks = FB.reason_blocks(_VOTE)
    values = [e["value"] for b in blocks if b["type"] == "actions" for e in b["elements"]]
    assert values == [f"{_VOTE}:{r}" for r in REASONS]
    assert len(values) <= 25


def test_the_notice_is_shown_next_to_the_buttons():
    """§3.6 — 버튼 옆 한 줄이 고지다. 그 문구가 없으면 동의를 가리킬 수 없다."""
    blob = repr(FB.feedback_blocks(_KEY))
    assert "품질" in blob and "개선" in blob


# ── I4 — 사용자 id 가 로그에 안 남는다 ────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_handler_never_logs_the_slack_user_id(monkeypatch):
    """**스키마만 깨끗한 것으로는 부족하다.** 페이로드는 `answer_key` 와 사용자 id 를 같은
    객체에 담아 오므로, 핸들러의 로그 한 줄이면 §3.4 가 지운 연결이 로그에 복원된다."""
    logged: list = []

    for level in ("info", "warning", "error"):
        monkeypatch.setattr(FB.logger, level,
                            lambda *a, **k: logged.append((a, k)))

    async def fake_vote(**kw):
        return _VOTE
    monkeypatch.setattr(FB.store, "record_vote", fake_vote)

    client = _Client()
    await FB.on_vote(_payload("fb_down", _KEY), client)

    # **수신자 지정과 기록은 다르다.** ephemeral 은 그 사람에게 보이게 하려면 id 가
    # 필요하므로 API 호출 인자에는 들어간다 — 그것은 전달이지 기록이 아니다. 금지 대상은
    # 남는 것: 로그, 그리고 운영자에게 나가는 DM.
    blob = repr(logged) + repr(client.dms)
    assert _USER not in blob, "사용자 id 가 로그·운영자 DM 에 실렸다"
    assert _USER not in repr(FB.store.counters), "카운터에 신원이 섞였다"
    # I13 — **키도 안 남는다.** 재연결에 필요한 것은 신원이나 스키마 하나가 아니라 **동거**다.
    # 봇은 같은 요청에서 질의와 principal 을 다루므로, 키를 찍는 로그 한 줄이 그 둘 옆에
    # 놓이면 투표↔질의 연결이 DB 밖에서 복원된다.
    assert _KEY not in blob, "answer_key 가 로그에 실렸다"


# ── 투표 → 사유 되묻기 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_down_vote_asks_for_a_reason_in_an_ephemeral(monkeypatch):
    """원 답변 메시지는 고치지 않는다 — 채널의 다른 사람에게 남의 투표가 보이면 그 자체가
    신원 노출이다 (§3.1.1)."""
    seen: dict = {}

    async def fake_vote(**kw):
        seen.update(kw)
        return _VOTE
    monkeypatch.setattr(FB.store, "record_vote", fake_vote)

    client = _Client()
    await FB.on_vote(_payload("fb_down", _KEY), client)

    assert seen["answer_key"] == _KEY and seen["verdict"] == "down"
    assert seen["channel_id"] == _CH and seen["message_ts"] == _TS, (
        "결속 검사에 쓸 값이 페이로드에서 안 왔다")
    assert len(client.ephemeral) == 1
    assert _VOTE in repr(client.ephemeral[0]), "사유 버튼이 투표 행 id 를 안 들고 간다"


@pytest.mark.asyncio
async def test_an_up_vote_says_thanks_and_asks_nothing(monkeypatch):
    async def fake_vote(**kw):
        return _VOTE
    monkeypatch.setattr(FB.store, "record_vote", fake_vote)

    client = _Client()
    await FB.on_vote(_payload("fb_up", _KEY), client)

    assert len(client.ephemeral) == 1
    assert "wrong_evidence" not in repr(client.ephemeral[0])


@pytest.mark.asyncio
async def test_a_refused_vote_tells_the_user(monkeypatch):
    """조용한 무시는 이 리포가 반복 지적한 '초록인데 동작 안 함' 을 사용자 쪽에서 재생산한다."""
    async def refuse(**kw):
        raise FB.store.VoteRefused("만료된 키")
    monkeypatch.setattr(FB.store, "record_vote", refuse)

    client = _Client()
    await FB.on_vote(_payload("fb_down", _KEY), client)

    assert len(client.ephemeral) == 1
    assert "wrong_evidence" not in repr(client.ephemeral[0])


# ── I6 — 피드백이 답변을 죽이지 않는다 ───────────────────────────────────────

@pytest.mark.asyncio
async def test_a_storage_failure_does_not_escape_the_handler(monkeypatch):
    async def boom(**kw):
        raise RuntimeError("DB 없음")
    monkeypatch.setattr(FB.store, "record_vote", boom)

    await FB.on_vote(_payload("fb_up", _KEY), _Client())   # 예외가 안 나가야 한다


# ── §3.7 개정: 아무 데도 안 알린다 ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_down_vote_notifies_nobody(monkeypatch):
    """**푸시를 지웠다** (2026-08-14 개정). 자료는 쌓이고 `nexus feedback` 이 주기적으로 뽑는다.

    이 검사가 있는 이유: 지운 경로는 조용히 되살아난다. 알림이 다시 필요해지면 §5.3 평가일에
    실제 비율을 쥐고 **모양부터** 정하는 것이 순서다.
    """
    async def fake_vote(**kw):
        return _VOTE
    monkeypatch.setattr(FB.store, "record_vote", fake_vote)

    client = _Client()
    await FB.on_vote(_payload("fb_down", _KEY), client)

    assert client.dms == [], "👎 가 어딘가로 밀려 나갔다"
    assert client.opened == [], "퍼머링크를 뽑았다 — 알릴 곳이 없는데 왜"
    assert not hasattr(FB, "OPERATOR"), "운영자 설정이 남아 있다"


# ── 사유 클릭 ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_reason_click_updates_that_vote(monkeypatch):
    seen: dict = {}

    async def fake_set(**kw):
        seen.update(kw)
        return True
    monkeypatch.setattr(FB.store, "set_reason", fake_set)

    client = _Client()
    await FB.on_reason(_payload("fb_reason", f"{_VOTE}:ignored_format"), client)

    assert seen == {"vote_id": _VOTE, "reason": "ignored_format"}
    assert len(client.ephemeral) == 1


@pytest.mark.asyncio
async def test_a_rejected_reason_tells_the_user_instead_of_going_quiet(monkeypatch):
    async def fake_set(**kw):
        return False
    monkeypatch.setattr(FB.store, "set_reason", fake_set)

    client = _Client()
    await FB.on_reason(_payload("fb_reason", f"{_VOTE}:not_found"), client)

    assert len(client.ephemeral) == 1
    assert "이미" in repr(client.ephemeral[0]) or "지났" in repr(client.ephemeral[0])


# ── 배선 (이 리포가 반복한 '초록인데 동작 안 함') ─────────────────────────────

@pytest.mark.asyncio
async def test_the_bot_attaches_the_buttons_and_records_the_offer(monkeypatch):
    """**모듈이 있는 것과 배선된 것은 다르다.** 여기서 확인하는 것은 답변 경로가 실제로
    버튼을 붙이고, 게시된 메시지에 결속해 제안 행을 남기느냐다."""
    from nexus.slack import bot

    async def fake_api(query, history=None):
        return {"answer": "답", "evidence_snippets": []}
    monkeypatch.setattr(bot, "_call_nexus_api", fake_api)

    async def no_history(*a, **k):
        return []
    monkeypatch.setattr(bot, "read_history", no_history)

    offers: list = []

    async def fake_offer(**kw):
        offers.append(kw)
    monkeypatch.setattr(FB.store, "record_offer", fake_offer)

    said: dict = {}

    async def say(**kw):
        said.update(kw)
        return {"ts": _TS, "channel": _CH}

    await bot._answer("질문", say, {"ts": "1", "channel": _CH}, client=None)

    ids = [e["action_id"] for b in said["blocks"] if b["type"] == "actions"
           for e in b["elements"]]
    assert FB.ACTION_UP in ids and FB.ACTION_DOWN in ids, "답변에 버튼이 안 붙었다"
    assert len(offers) == 1, "제안 행(분모)이 안 남았다"
    assert offers[0]["channel_id"] == _CH and offers[0]["message_ts"] == _TS, (
        "게시된 메시지에 결속되지 않았다 — 그러면 키가 무기명 자격증명이 된다")
    assert offers[0]["answer_key"] == [e["value"] for b in said["blocks"]
                                       if b["type"] == "actions"
                                       for e in b["elements"]][0], (
        "버튼이 들고 나간 키와 저장된 키가 다르다")


@pytest.mark.asyncio
async def test_no_offer_row_without_a_message_handle(monkeypatch):
    """결속할 (채널, ts) 가 없으면 제안 행을 만들지 않는다 — 결속 없는 행은 I10 이 막으려는
    것을 되살린다. 투표가 오면 orphan 으로 받아 표시한다."""
    from nexus.slack import bot

    async def fake_api(query, history=None):
        return {"answer": "답", "evidence_snippets": []}
    monkeypatch.setattr(bot, "_call_nexus_api", fake_api)

    async def no_history(*a, **k):
        return []
    monkeypatch.setattr(bot, "read_history", no_history)

    offers: list = []

    async def fake_offer(**kw):
        offers.append(kw)
    monkeypatch.setattr(FB.store, "record_offer", fake_offer)

    async def say(**kw):
        return None          # 응답을 안 주는 표면

    await bot._answer("질문", say, {"ts": "1"}, client=None)
    assert offers == []


@pytest.mark.asyncio
async def test_the_key_is_not_logged_even_when_storage_fails(monkeypatch):
    """실패 경로가 진단을 위해 키를 찍기 쉽다 — 거기가 I13 이 깨지는 자리다."""
    logged: list = []
    for level in ("info", "warning", "error"):
        monkeypatch.setattr(FB.logger, level, lambda *a, **k: logged.append((a, k)))

    async def boom(**kw):
        raise RuntimeError(f"DB 없음 (key={_KEY})")   # 예외 문구에 키가 들어와도
    monkeypatch.setattr(FB.store, "record_vote", boom)

    await FB.on_vote(_payload("fb_down", _KEY), _Client())
    assert _KEY not in repr(logged), "실패 로그가 키를 흘렸다"
