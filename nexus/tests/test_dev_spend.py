"""평가 실행이 기본적으로 **돈을 안 쓰는가**, 그리고 쓴 것을 **말하는가**.

2026-08-13 에 하루치 평가를 유료 API 로 돌렸다. 브리지는 이미 있었고, 실패한 것은 하나다:
**실행기가 자기 백엔드를 한 번도 말하지 않았다.** 그리고 그 지출은 장부에도 안 남았다.
"""

from __future__ import annotations

import pytest

from nexus.llm import dev_spend as D


class _Paid:
    """anthropic 백엔드를 흉내낸다."""

    class _B:
        pass

    def __init__(self):
        self._backend = self._B()
        self.model = "claude-sonnet-4-6"


class _Free:
    class _ClaudeCodeBackend:
        pass

    def __init__(self):
        self._backend = self._ClaudeCodeBackend()
        self.model = "bridge"


# ── 기본은 무료 ────────────────────────────────────────────────────────────────

def test_a_paid_backend_is_refused_by_default(capsys):
    """**이 검사가 이 파일의 이유다.** 잊는 쪽이 비싸다."""
    with pytest.raises(SystemExit) as e:
        D.require_free(_Paid(), what="평가")
    assert "유료" in str(e.value)
    assert "task llm-bridge" in str(e.value), "고치는 법을 안 알려주면 거절이 벽이 된다"


def test_a_paid_backend_runs_when_explicitly_allowed(capsys):
    D.require_free(_Paid(), allow_paid=True)
    out = capsys.readouterr().out
    assert "유료 API 로 나간다" in out, "허락했어도 조용히 나가면 안 된다"


def test_a_free_backend_says_so_and_proceeds(capsys):
    D.require_free(_Free())
    assert "무료 브리지" in capsys.readouterr().out


def test_an_unknown_backend_counts_as_paid():
    """모르는 백엔드를 무료로 가정하면, 새 백엔드가 붙는 날 조용히 과금된다."""
    class _New:
        class _SomeNewBackend:
            pass

        def __init__(self):
            self._backend = self._SomeNewBackend()
            self.model = "x"

    assert D.is_free(_New()) is False
    with pytest.raises(SystemExit):
        D.require_free(_New())


# ── 쓴 만큼 센다 ───────────────────────────────────────────────────────────────

def test_calls_are_counted_even_without_prices():
    """브리지는 토큰을 안 준다. 호출이 0 으로 세어지면 "안 돌았다" 와 구별되지 않는다."""
    s = D.Spend()
    s.add(None, kind="answer")
    s.add(None, kind="rewrite")
    assert s.calls == 2 and s.priced == 0 and s.usd == 0.0
    assert "가격 정보 없음" in s.summary()
    assert s.by_kind == {"answer": 1, "rewrite": 1}


def test_dollars_add_up_when_the_backend_prices_them():
    from nexus.providers.llm import Usage

    s = D.Spend()
    s.add(Usage(100, 50, 0.0125, "m"))
    s.add(Usage(80, 20, 0.0025, "m"), kind="rewrite")
    assert s.priced == 2
    assert s.usd == pytest.approx(0.015)
    assert "$0.0150" in s.summary()


def test_a_dict_usage_is_accepted_too():
    """`AnswerResult.usage` 는 dict 다. 타입이 갈리면 한쪽이 조용히 0 으로 센다."""
    s = D.Spend()
    s.add({"cost_usd": 0.004})
    assert s.priced == 1 and s.usd == pytest.approx(0.004)


def test_the_report_shape_is_stable():
    s = D.Spend()
    s.add({"cost_usd": 0.01})
    assert set(s.as_dict()) == {"calls", "priced_calls", "usd", "by_kind"}
