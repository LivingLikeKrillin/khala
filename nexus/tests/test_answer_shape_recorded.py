"""답변의 **모양**이 라이브 기록에 남는가 (감사 B2 — FP5 계측기를 꽂는다).

⛔ **왜 준수가 아니라 모양인가.** `search/format_compliance.py` 의 `check` 는 (요청 유형,
답변) 둘을 받는다. 평가에서는 라벨이 유형을 주지만 **라이브에는 그 유형을 아는 것이 없다** —
질의에서 형식 요청을 알아내는 부품이 이 리포에 없다. 그것을 지금 지어내면 오탐이 새 실패
유형으로 들어오고, 그것은 "측정 없이도 옳은 변경" 이 아니라 사전 등록이 필요한 기법 추가다.

그래서 판정하지 않고 **남긴다.** 모양은 요청과 무관하게 결정론이고 LLM 을 안 부른다. 지금
남겨 두면 나중에 요청을 알게 됐을 때(실제 질의 채굴) 과거까지 되짚을 수 있고, 안 남기면
그때 가서도 없다.

⚠ **키를 빼지 않는다.** 못 잰 자리는 같은 키를 `None` 으로 남긴다 — 안 그러면 다음 사람이
"안 쟀다" 와 "유실됐다" 를 못 가른다. 이 리포는 그 구분이 없어서 이미 한 번 데었다.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.llm.answer import generate_answer  # noqa: E402
from nexus.search.format_compliance import (  # noqa: E402
    SHAPE_KEYS, shape, shape_if_measured, shape_unmeasured,
)
from nexus.search.spans import SpanSet  # noqa: E402


# ── 순수 판정 ────────────────────────────────────────────────────────────────

def test_shape_counts_what_the_scorer_counts():
    """모양은 채점기와 **같은 함수**로 센다 — 여기서 새 규칙을 만들면 둘이 갈린다."""
    s = shape("첫 문장이다. 둘째다.")
    assert s["n_sentences"] == 2
    assert s["has_table"] is False
    assert s["n_list_items"] == 0
    assert s["n_chars"] == len("첫 문장이다. 둘째다.")


def test_shape_sees_a_table_and_a_list():
    s = shape("머리말\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n- 항목 하나\n- 항목 둘")
    assert s["has_table"] is True
    assert s["n_list_items"] == 2


def test_shape_of_nothing_is_zero_not_a_crash():
    assert shape(None)["n_chars"] == 0
    assert shape("")["n_sentences"] == 0


def test_unmeasured_keeps_every_key():
    assert set(shape_unmeasured()) == set(SHAPE_KEYS)
    assert all(v is None for v in shape_unmeasured().values())
    assert set(shape("아무 문장.")) == set(SHAPE_KEYS)


def test_every_shape_value_is_a_scalar_the_span_will_accept():
    """`detail` 은 스칼라만 받는다(마이그레이션 040 의 CHECK). 여기서 걸러야 라이브에서 안 깨진다."""
    spans = SpanSet(max_candidates=100)
    spans.add_answer(n_in=1, **shape("문장 하나."))
    spans.add_answer(n_in=1, **shape_unmeasured())      # `None` 도 스칼라다
    assert len(spans.spans) == 2


# ── 배선 ─────────────────────────────────────────────────────────────────────

@dataclass
class _Snip:
    doc_title: str = "문서"
    section_path: str = "절"
    text: str = "본문"
    chunk_rid: str = "c"
    source_uri: str = "u"
    score: float = 0.9
    doc_type: str = "DESIGN_DOC"
    classification: str = "INTERNAL"
    updated_at: object = None


@dataclass
class _Packet:
    snippets: list = field(default_factory=list)
    graph: object = None
    provenance: list = field(default_factory=list)


class _FakeLLM:
    def __init__(self, answer):
        self._answer, self.configured = answer, True

    async def generate_full(self, system, user, max_tokens=4096):
        from nexus.providers.llm import LLMResult, Usage
        return LLMResult(text=self._answer, usage=Usage(None, None, None, "fake"))


class _BrokenLLM:
    configured = True

    async def generate_full(self, *a, **k):
        raise RuntimeError("모델이 죽었다")


def _answer_span(spans: SpanSet):
    return next(s for s in spans.spans if s.stage == "answer")


@pytest.mark.asyncio
async def test_a_real_answer_records_its_shape():
    spans = SpanSet(max_candidates=100)
    await generate_answer("질의", _Packet([_Snip()]),
                          _FakeLLM("한 문장이다. 두 문장이다. 세 문장이다."),
                          spans=spans)                      # type: ignore[arg-type]
    d = _answer_span(spans).detail
    assert d["n_sentences"] == 3
    assert d["n_chars"] > 0
    assert d["has_table"] is False


@pytest.mark.asyncio
async def test_abstention_leaves_the_keys_but_measures_nothing():
    """⛔ 기권 안내문은 **고정 문자열**이다. 그 문장 수를 세면 측정이 아니라 상수를 센 것이다."""
    spans = SpanSet(max_candidates=100)
    await generate_answer("질의", _Packet([]), llm_svc=None, spans=spans)
    d = _answer_span(spans).detail
    assert d["abstained"] is True
    assert all(d[k] is None for k in SHAPE_KEYS), d


@pytest.mark.asyncio
async def test_a_failed_generation_measures_nothing_either():
    """생성 실패 시 답변 자리에는 안내문 + 근거 원문이 들어간다 — 그 모양은 답변의 모양이 아니다."""
    spans = SpanSet(max_candidates=100)
    await generate_answer("질의", _Packet([_Snip()]), _BrokenLLM(),  # type: ignore[arg-type]
                          spans=spans)
    d = _answer_span(spans).detail
    assert d["llm_failed"] is True
    assert all(d[k] is None for k in SHAPE_KEYS), d


@pytest.mark.asyncio
async def test_capture_off_still_records_nothing_at_all():
    """대조군 — `spans=None` 이면 이 변경이 오늘 경로를 한 바이트도 안 건드린다."""
    res = await generate_answer("질의", _Packet([_Snip()]),
                                _FakeLLM("문장."), spans=None)  # type: ignore[arg-type]
    assert res.answer == "문장."


# ── 갈래는 하나여야 한다 ─────────────────────────────────────────────────────

def test_one_branch_serves_every_surface():
    """⛔ 표면마다 분기를 따로 쓰면 한 곳만 고쳐지고 나머지가 조용히 다른 규칙을 쓴다."""
    assert shape_if_measured("문장 하나.", measured=True) == shape("문장 하나.")
    assert shape_if_measured("문장 하나.", measured=False) == shape_unmeasured()


def test_the_streaming_surface_goes_through_that_branch():
    """⚠ **구조 검사다.** `/search/answer/stream` 은 `generate_answer` 를 안 거치고
    `llm_svc.stream` 을 직접 부르므로, 위의 배선 검사들이 그 표면을 하나도 안 지난다 —
    답변 span 자체가 그래서 한 번 빠져 있었다(#440).

    이 검사가 다는 것은 *호출이 있는가* 까지다. 그 호출이 실제로 무엇을 남기는지는 DB 를
    태워야 알고, 그 짝은 아직 없다. 짝 없이 이것만 믿지 마라 —
    `test_answer_surfaces_share_the_seam.py` 머리말이 같은 말을 한다.
    """
    import ast
    import inspect

    import nexus.api as api

    src = inspect.getsource(api)
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and "answer_stream" in n.name)
    called = {n.func.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    called |= {n.func.attr for n in ast.walk(fn)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "add_answer" in called, "스트리밍 표면이 answer span 을 안 남긴다"
    assert "shape_if_measured" in called, "스트리밍 표면이 답변 모양을 안 남긴다"
