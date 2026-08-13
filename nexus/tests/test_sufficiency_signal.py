"""근거 충분성을 **기록**하는 경로 — SPEC-nexus-sufficiency-signal.

여기서 재는 것은 판정의 품질이 아니다(그건 평가 하니스의 일이고 통계적 결과라 테스트가 아니다).
여기서 재는 것은 **기록 기제가 관측 대상을 망가뜨리지 않는가**이다:

    답변 경로가 판정을 기다리지 않는가 · 판정이 터져도 행이 남는가 · 계측기가 고장 나도
    search_log 가 살아남는가 · 슬롯이 새지 않는가 · 원문 텍스트가 기록에 들어가지 않는가

마지막 항목이 가장 중요하다. `search_log` 는 원문 질의를 담은 적이 없고, 그 불변식을 깨는 것은
컬럼 하나가 아니라 신호 객체에 텍스트 필드를 만드는 습관이다.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import fields
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.search import signals as S  # noqa: E402


def _sig(tenant="t", path="search_answer"):
    return S.SearchSignals(
        path=path, tenant=tenant, clearance="INTERNAL", route="hybrid_only",
        query_sha256="x", query_len=1, n_snippets=3, top_score=0.5, n_entities=0,
        graph_requested=False, n_graph_edges=0, no_answer=False, llm_failed=False,
        latency_ms=10,
    )


class _Judge:
    """판정자 대역. 실제 LLM 은 부르지 않는다."""

    model = "test-model"

    def __init__(self, reply="VERDICT: sufficient\nREASON: r", delay=0.0, boom=None):
        self.reply, self.delay, self.boom, self.calls = reply, delay, boom, []
        self.task_seen = None

    async def generate(self, system, user, max_tokens=4096):
        self.calls.append((system, user))
        self.task_seen = asyncio.current_task()
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.boom:
            raise self.boom
        return self.reply


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    """모든 테스트는 판정자가 **꺼진** 상태에서 시작한다 — 기본값이 그것이기 때문이다."""
    for k in ("NEXUS_SUFFICIENCY", "NEXUS_SUFFICIENCY_TENANTS",
              "NEXUS_SUFFICIENCY_CONCURRENCY", "NEXUS_SUFFICIENCY_TIMEOUT"):
        monkeypatch.delenv(k, raising=False)
    S._inflight = 0
    yield
    S._inflight = 0


def _on(monkeypatch, tenants="t", **env):
    monkeypatch.setenv("NEXUS_SUFFICIENCY", "on")
    monkeypatch.setenv("NEXUS_SUFFICIENCY_TENANTS", tenants)
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))


# ── 텍스트가 기록으로 새지 않는가 ───────────────────────────────────────────────

def test_the_signal_object_carries_no_text():
    """`SearchSignals` 에 텍스트 필드가 하나라도 생기면 원문 질의 불변식은 관례로 격하된다.

    질의는 sha256+len 으로만 들어간다(init.sql, 원칙 #3). 판정자가 원문을 필요로 한다고 해서
    신호 객체에 실으면, 다음 사람이 그 자리에 근거 본문을 넣는 것을 막을 근거가 사라진다.
    """
    expected = {
        "path", "tenant", "clearance", "route",          # 식별자·라벨
        "query_sha256", "query_len",                     # 질의가 들어갈 수 있는 **유일한** 형태
        "n_snippets", "top_score", "n_entities", "graph_requested", "n_graph_edges",
        "no_answer", "llm_failed", "latency_ms",
        "n_citations", "unverified_citations",
        "prompt_tokens", "completion_tokens", "cost_usd",
        "n_image_bearing_docs",
        # 2026-08-13, SPEC-nexus-multi-turn-retrieval §4 I6. **정수 하나**다 — 융합에 쓰인
        # 채널 수. 질의 문자열도, 재작성 결과도 담지 않는다(재작성문은 원문보다 더 민감하다:
        # 이력의 사실을 일부러 채워 넣기 때문이다). 여기 필요한 것은 "이 행의 top_score 가
        # 몇 채널로 만들어졌나" 뿐이고, 그것은 세는 것으로 답해진다.
        "fusion_channels",
    }
    actual = {f.name for f in fields(S.SearchSignals)}
    assert actual == expected, (
        "SearchSignals 의 필드 집합이 바뀌었다. 새 필드가 원문 질의나 근거 본문을 담지 않는지 "
        f"확인하고 이 목록을 의도적으로 갱신하라. 추가됨={actual - expected} 사라짐={expected - actual}")


def test_judge_input_is_call_scoped_not_a_signal_field():
    ji = S.JudgeInput(query="원문 질의", evidence="근거 본문")
    assert ji.query and ji.evidence
    assert not any(f.name in ("query", "evidence") for f in fields(S.SearchSignals))


# ── 적격성: 기본 off, tenant 단위 동의 ─────────────────────────────────────────

def test_off_by_default_records_disabled_and_never_calls_the_judge():
    """업그레이드한 배포가 조용히 공급자를 부르기 시작하면 안 된다 — egress 통제가 이 기본값이다."""
    j = _Judge()
    terminal, judge_id, fp = S._eligibility(_sig(), S.JudgeInput("q", "e", None, j))
    assert terminal == "disabled" and judge_id == "off" and fp is None
    assert j.calls == []


def test_a_tenant_not_on_the_allowlist_is_disabled(monkeypatch):
    """전역 플래그 하나가 모든 tenant 를 대신 결정하면 안 된다. `*` 는 없다."""
    _on(monkeypatch, tenants="other")
    terminal, _, _ = S._eligibility(_sig(tenant="t"), S.JudgeInput("q", "e", None, _Judge()))
    assert terminal == "disabled"


def test_search_only_rows_are_not_applicable():
    """답변을 시도하지 않은 행에는 '충분'이라는 말이 성립하지 않는다."""
    terminal, judge_id, fp = S._eligibility(_sig(path="search"), None)
    assert terminal == "not_applicable" and judge_id == "off" and fp is None


def test_an_enabled_tenant_is_eligible_and_gets_an_identity(monkeypatch):
    _on(monkeypatch)
    terminal, judge_id, fp = S._eligibility(_sig(), S.JudgeInput("q", "e", {}, _Judge()))
    assert terminal is None
    assert judge_id.count("/") == 2 and judge_id.endswith(tuple("0123456789abcdef"))
    assert len(fp) == 8


# ── 판정 결과 → 저장값 ─────────────────────────────────────────────────────────

def test_verdicts_map_to_stored_values(monkeypatch):
    _on(monkeypatch)
    for reply, expected in [
        ("VERDICT: sufficient\nREASON: r", "sufficient"),
        ("VERDICT: insufficient\nREASON: r", "insufficient"),
        ("근거가 충분해 보입니다", "unparseable"),
    ]:
        v = asyncio.run(S._judge_with_timeout(S.JudgeInput("q", "e", {}, _Judge(reply))))
        assert v == expected, reply


def test_a_raising_judge_records_error_not_unparseable(monkeypatch):
    """'이상한 답을 냈다' 와 '부르지도 못했다' 는 다른 사실이다. 합치면 공급자 장애가
    근거 부족으로 읽힌다."""
    _on(monkeypatch)
    v = asyncio.run(S._judge_with_timeout(
        S.JudgeInput("q", "e", {}, _Judge(boom=RuntimeError("backend down")))))
    assert v == "error"


def test_a_hanging_judge_records_timeout_and_does_not_hang_forever(monkeypatch):
    _on(monkeypatch, NEXUS_SUFFICIENCY_TIMEOUT=0.05)
    v = asyncio.run(S._judge_with_timeout(S.JudgeInput("q", "e", {}, _Judge(delay=5))))
    assert v == "timeout"


def test_the_judge_never_receives_the_answer(monkeypatch):
    """판정자와 피판정자가 같아지면 안 된다 — 논문이 지목한 실패 구도다."""
    _on(monkeypatch)
    j = _Judge()
    asyncio.run(S._judge_with_timeout(S.JudgeInput("질의", "근거 본문", {}, j)))
    (system, user), = j.calls
    assert "질의" in user and "근거 본문" in user
    assert "답변" not in user.replace("## 근거", "")


# ── 슬롯: 상한·shed·누수 ───────────────────────────────────────────────────────

def test_saturation_sheds_without_queueing(monkeypatch):
    """상한 1 로 고정한다 — 기본값 2 에서는 기제가 고장 나도 두 번째 호출이 성공한다."""
    _on(monkeypatch, NEXUS_SUFFICIENCY_CONCURRENCY=1)
    assert S._try_take_slot() is True
    assert S._try_take_slot() is False       # 대기하지 않는다
    S._release_slot()
    assert S._try_take_slot() is True


def test_the_slot_is_released_even_when_the_judge_raises(monkeypatch):
    """슬롯이 두 번 새면 이후 모든 검색이 영원히 `shed` 로 굳는다 — 건강한 부하 차단과
    구별되지 않는 고장이다."""
    _on(monkeypatch, NEXUS_SUFFICIENCY_CONCURRENCY=1)
    before = S._inflight
    asyncio.run(S._judge_with_timeout(S.JudgeInput("q", "e", {}, _Judge(boom=ValueError()))))
    assert S._inflight == before, "판정 실패가 슬롯을 물고 있으면 안 된다"


def test_a_timeout_above_half_the_stranded_bound_is_refused(monkeypatch):
    """판정이 좌초 문턱보다 오래 살면 정상 완료가 UPDATE 가드에 걸려 버려진다.
    prose 로만 결합해 두면 드리프트한다."""
    _on(monkeypatch, NEXUS_SUFFICIENCY_TIMEOUT=S.STRANDED_SECONDS)
    with pytest.raises(ValueError, match="상한"):
        asyncio.run(S._judge_with_timeout(S.JudgeInput("q", "e", {}, _Judge())))


def test_the_stranded_bound_is_a_fixed_constant_not_derived_from_the_timeout(monkeypatch):
    """timeout 에서 유도하면 운영자가 그것을 바꾸는 순간 과거 행이 전부 재분류된다."""
    _on(monkeypatch, NEXUS_SUFFICIENCY_TIMEOUT=1)
    assert S.STRANDED_SECONDS == 300
    _on(monkeypatch, NEXUS_SUFFICIENCY_TIMEOUT=100)
    assert S.STRANDED_SECONDS == 300


# ── 지문 ───────────────────────────────────────────────────────────────────────

def test_the_fingerprint_moves_with_the_embedding_column(monkeypatch):
    """컷오버를 사이에 둔 창이 서로 다른 두 측정을 한 이름으로 평균내면 안 된다."""
    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", "embedding")
    a = S.evidence_fingerprint({})
    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", "embedding_1024")
    assert S.evidence_fingerprint({}) != a


def test_the_fingerprint_moves_with_the_tokenizer():
    """mecab→nori 교체는 판정자가 보는 근거를 바꾼다. 지문이 그대로면 그 창은 거짓이 된다."""
    from nexus.index import bm25

    base = S.evidence_fingerprint({})

    class _Nori:
        def tokenize(self, text):  # pragma: no cover - 모양만 필요하다
            return text.split()

    with bm25.use_tokenizer(_Nori()):
        assert S.evidence_fingerprint({}) != base


def test_the_fingerprint_moves_with_snippet_length():
    """스니펫 길이는 근거 본문을 바꾼다 — 이 리포는 그 값 하나로 답변 품질이 갈린 적이 있다."""
    a = S.evidence_fingerprint({"search": {"snippet_max_chars": 300}})
    b = S.evidence_fingerprint({"search": {"snippet_max_chars": 1200}})
    assert a != b
