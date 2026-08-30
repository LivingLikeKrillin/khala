"""보여 준 답변을 남기는가 — 신고를 그 답에 대 보려면 답이 남아 있어야 한다.

⛔ **왜 생겼나 (2026-08-30, 파일럿 첫날).** 사용자가 받은 답이 이상하다고 말했는데 그 답을
꺼낼 수 없었다. 질문 원문은 남고 답변은 안 남았다 — `answer_offered` 가 가진 것은 해시와
채널·타임스탬프뿐이다. 같은 질문을 다시 돌리니 150·653·2,000자가 나왔고, 사용자가 본 것이
그중 무엇인지 알 방법이 없었다. **진단이 거기서 멈췄다.**
"""

from __future__ import annotations

import asyncio

from nexus.feedback import store


class _DB:
    def __init__(self, fail=False):
        self.rows, self.fail = [], fail

    async def execute(self, sql, *args):
        if self.fail:
            raise RuntimeError("DB 죽음")
        if "search_answer_text" in sql:
            self.rows.append(args)


def _run(text, fail=False, monkeypatch=None):
    fake = _DB(fail)
    monkeypatch.setattr(store, "db", fake)
    asyncio.run(store.record_answer_text(tenant="t", answer_key="k", answer_text=text))
    return fake


def test_the_answer_is_kept_with_its_length(monkeypatch):
    text = "자동 폐쇄 조건은 두 가지입니다"
    fake = _run(text, monkeypatch=monkeypatch)
    assert fake.rows == [("t", "k", text, len(text))]


def test_a_write_failure_does_not_kill_the_answer(monkeypatch):
    """⛔ 보존이 답변 경로를 죽이면 안 된다 — 남기려다 못 주는 것이 더 나쁘다."""
    before = store.counters["answer_write_failed"]
    _run("아무 답변", fail=True, monkeypatch=monkeypatch)
    assert store.counters["answer_write_failed"] == before + 1


def test_an_empty_answer_writes_nothing(monkeypatch):
    """옛 클라이언트가 이 필드 없이 부르면 예전과 같이 동작해야 한다.
    거르는 자리는 호출부가 아니라 저장 함수 자신이다 — 호출부는 늘어난다."""
    fake = _run("", monkeypatch=monkeypatch)
    assert fake.rows == []
