"""Slack 봇 — SPEC-nexus-slack-bot §4.2·§4.3·§6.

핸들러와 API 클라이언트는 라이브 Slack 없이(event dict + say 콜러블) 그리고 라이브 Nexus
없이(httpx transport 주입) 단위 테스트한다. Socket Mode 배선은 프레임워크 몫 — go-live 게이트에서.

여기서 고정하는 불변식:
  · _call_nexus_api 는 Authorization: Bearer 를 보낸다 (봇 존재 내내 실패해온 단언).
  · 결과→메시지 매핑은 순수 함수. 401=운영자용, 503/빈=사용자용, 그 외=일반+로그.
  · 토큰은 어떤 블록에도 로그에도 안 나온다.

읽기 전용의 서버 강제(SPEC §6, I-005)는 여기서 복제하지 않는다: 봇의 principal 은 capability 0
principal 일 뿐이고, 그 벽은 documents 엔드포인트가 세운다 —
test_documents_api.py::test_destructive_paths_require_manage_documents_including_supersede 가
capability 0 → hide/restore/unsupersede/supersede 전부 403 을 실제 auth 경로로 이미 증명한다.
slack 이름으로 다시 쓰면 같은 엔드포인트·같은 검사를 재검증할 뿐이다(파편화).
"""

from __future__ import annotations

import httpx
import pytest

from nexus.slack import bot
from nexus.slack.messages import Outcome, message_for


# ── §4.3 결과 → 메시지 (순수) ─────────────────────────────────────────────────

def test_each_outcome_maps_to_its_own_message():
    assert "운영자" in message_for(Outcome.BAD_TOKEN)          # 401: 운영자용
    assert "지금 답변할 수 없습니다" in message_for(Outcome.UNAVAILABLE)  # 503
    assert "찾지 못했습니다" in message_for(Outcome.EMPTY_GROUNDING)
    assert "아직 인덱싱된 문서가 없습니다" in message_for(Outcome.EMPTY_CORPUS)
    assert "오류" in message_for(Outcome.OTHER)


def test_empty_grounding_and_empty_corpus_are_distinct():
    """근거 없음(코퍼스는 있음)과 코퍼스 없음은 다른 사실, 다른 문장."""
    assert message_for(Outcome.EMPTY_GROUNDING) != message_for(Outcome.EMPTY_CORPUS)


def test_a_message_never_contains_a_token():
    """어떤 결과 메시지도 자격증명을 담지 않는다 — 문자열이 토큰을 보간하지 않는다."""
    for o in Outcome:
        m = message_for(o)
        assert "Bearer" not in m and "xoxb" not in m and "ntn_" not in m


# ── §4.2 auth 헤더 (봇 존재 내내 없던 것) ─────────────────────────────────────

@pytest.fixture
def captured(monkeypatch):
    """httpx 요청을 가로채 헤더/바디를 본다. 응답은 테스트가 정한다."""
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"success": True, "data": {
            "answer": "답", "evidence_snippets": [{"doc_title": "t"}]}})

    monkeypatch.setattr(bot, "_transport", lambda: httpx.MockTransport(handler))
    monkeypatch.setattr(bot, "NEXUS_SLACK_TOKEN", "bot-secret-token-xyz")
    return seen


async def test_call_sends_the_authorization_header(captured):
    await bot._call_nexus_api("결제 서비스 토픽")
    assert captured["auth"] == "Bearer bot-secret-token-xyz"
    assert "/search/answer" in captured["url"]


# ── §4.3 상태 분류 ────────────────────────────────────────────────────────────

def _bot_with(monkeypatch, handler, token="tok"):
    monkeypatch.setattr(bot, "_transport", lambda: httpx.MockTransport(handler))
    monkeypatch.setattr(bot, "NEXUS_SLACK_TOKEN", token)


async def test_401_classifies_as_bad_token(monkeypatch):
    _bot_with(monkeypatch, lambda r: httpx.Response(401, json={"detail": "unauthorized"}))
    with pytest.raises(bot.NexusCallError) as e:
        await bot._call_nexus_api("q")
    assert e.value.outcome is Outcome.BAD_TOKEN


async def test_503_classifies_as_unavailable(monkeypatch):
    _bot_with(monkeypatch, lambda r: httpx.Response(503, json={"detail": "db"}))
    with pytest.raises(bot.NexusCallError) as e:
        await bot._call_nexus_api("q")
    assert e.value.outcome is Outcome.UNAVAILABLE


async def test_500_and_429_classify_as_other(monkeypatch):
    for code in (500, 429):
        _bot_with(monkeypatch, lambda r, c=code: httpx.Response(c, json={"detail": "x"}))
        with pytest.raises(bot.NexusCallError) as e:
            await bot._call_nexus_api("q")
        assert e.value.outcome is Outcome.OTHER


async def test_empty_grounding_when_no_snippets_but_corpus_exists(monkeypatch):
    _bot_with(monkeypatch, lambda r: httpx.Response(200, json={
        "success": True, "data": {"answer": "", "evidence_snippets": []}}))
    monkeypatch.setattr(bot, "_documents_count", lambda *_: 20)   # 코퍼스는 있다
    # **`_blind` 를 가로채지 않는다.** 스텁으로 바꾸면 진짜 판정이 이 검사 밖으로 나간다 —
    # 대신 그 판정이 읽는 것(`/visibility` 응답)을 준다.
    monkeypatch.setattr(bot, "_visibility", lambda *_: {"no_visible_documents": False,
                                                        "documents_visible": 20})
    with pytest.raises(bot.NexusCallError) as e:
        await bot._call_nexus_api("q")
    assert e.value.outcome is Outcome.EMPTY_GROUNDING


async def test_empty_corpus_when_no_documents(monkeypatch):
    _bot_with(monkeypatch, lambda r: httpx.Response(200, json={
        "success": True, "data": {"answer": "", "evidence_snippets": []}}))
    monkeypatch.setattr(bot, "_documents_count", lambda *_: 0)    # 코퍼스가 없다
    with pytest.raises(bot.NexusCallError) as e:
        await bot._call_nexus_api("q")
    assert e.value.outcome is Outcome.EMPTY_CORPUS


# ── §4.2 시동 거부 ────────────────────────────────────────────────────────────

def test_main_refuses_to_start_without_the_nexus_token(monkeypatch):
    from nexus.slack import app as slack_app

    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-x")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-x")
    monkeypatch.delenv("NEXUS_SLACK_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        slack_app.main()


# ── §6 핸들러 (멘션 제거) ─────────────────────────────────────────────────────

def test_mention_is_stripped():
    assert bot._extract_query("<@U12345> 결제 서비스 토픽") == "결제 서비스 토픽"


# ── 실패를 답변인 척 내보내지 않는다 (2026-08-13 라이브 파일럿에서 전부 관측) ──────
#
# 이 절의 세 불변식은 전부 **실제로 슬랙에서 깨진 것**이다. 봇은 그날까지 한 번도 실행된 적이
# 없었고(의존성 누락으로 기동조차 못 했다), 뜨자마자 셋이 연달아 나왔다.

async def test_generation_failure_is_not_presented_as_an_answer(monkeypatch):
    """LLM 이 죽으면 `answer` 자리에는 근거 원문 덤프가 들어온다(llm/answer.py).

    그것을 그대로 올리면 사용자는 **실패를 답변으로 읽는다.** 2026-08-13 크레딧이 소진됐을 때
    실제로 그 덤프가 슬랙으로 나갔다(그리고 길이 상한에 걸려 터졌다).
    """
    _bot_with(monkeypatch, lambda r: httpx.Response(200, json={
        "success": True, "data": {
            "answer": "답변을 생성할 수 없습니다. 아래 근거를 직접 확인해주세요.\n\n" + "근거" * 2000,
            "evidence_snippets": [{"doc_title": "t"}],
            "llm_failed": True}}))
    with pytest.raises(bot.NexusCallError) as e:
        await bot._call_nexus_api("q")
    assert e.value.outcome is Outcome.GENERATION_FAILED


async def test_no_visible_documents_is_not_the_same_as_not_found(monkeypatch):
    """등급 때문에 **아무 문서도 안 보이는 것**은 검색 실패가 아니라 설정 결함이다.

    2026-08-13: 봇 principal 은 PUBLIC 인데 코퍼스 116건이 전부 INTERNAL 이라 어떤 질문에도
    0건이었다. 그런데 봇은 "인덱싱된 문서에서 답을 찾지 못했습니다" 라고 답했다 — 문서를 뒤졌다는
    단언이고, 거짓이었다. 뒤진 문서가 0건이었다.
    """
    _bot_with(monkeypatch, lambda r: httpx.Response(200, json={
        "success": True, "data": {"answer": "", "evidence_snippets": []}}))
    monkeypatch.setattr(bot, "_documents_count", lambda *_: 116)   # 코퍼스는 있다
    monkeypatch.setattr(bot, "_blind", lambda *_: True)            # 그런데 하나도 안 보인다
    with pytest.raises(bot.NexusCallError) as e:
        await bot._call_nexus_api("q")
    assert e.value.outcome is Outcome.NO_VISIBLE_DOCS
    assert message_for(Outcome.NO_VISIBLE_DOCS) != message_for(Outcome.EMPTY_GROUNDING)
