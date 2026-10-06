"""프롬프트 버전이 **잊을 수 없는 방식으로** 남는가 — 그리고 **프롬프트를 쓰는 코드 전부**를 보는가.

`PROMPT_VERSION = 3` 같은 상수는 고치는 사람이 올려야 하고, 그 규율은 반드시 한 번 깨진다 —
깨진 순간 기록은 조용히 거짓이 된다. 그래서 값은 코드에서 파생된다.

⛔ **그런데 파생의 재료가 좁았다 (실측 2026-09-27).** 옛 핑거프린트는 `SYSTEM_PROMPT` ·
`USER_REQUEST_RULE` · `build_user_prompt` 소스 셋만 찍었다. 답변 근거가 약할 때 붙는 규칙(08-18),
근거 묶음을 글로 바꾸는 `format_for_llm`(코드 값 절 · 판정 · 인용 문법 벗기기 · 등급 주석),
근거 묶음을 채우는 `packet_for_answer` 는 전부 밖이었다. 그래서 08-29 ~ 09-23 의 답변 572행이
**한 값**이다 — 그 사이 모델이 받는 글은 여러 번 바뀌었다.

⇒ 재료를 **함수 목록**이 아니라 **모듈 목록**으로 잡고, 그 목록에 빠진 것이 없는지를 이름이
아니라 **실행으로** 확인한다(`test_everything_that_writes_the_prompt_is_covered`).
"""

from __future__ import annotations

import sys

import pytest

from nexus.llm import prompt_version as V


@pytest.fixture(autouse=True)
def _fresh_sources():
    """재료는 프로세스당 한 번 읽는다(캐시). 소스를 바꿔 보는 검사마다 캐시를 비운다."""
    V._assembly_sources.cache_clear()
    yield
    V._assembly_sources.cache_clear()


def test_the_same_code_gives_the_same_value():
    """실행마다 달라지면 구간을 못 가른다."""
    assert V.prompt_version() == V.prompt_version()
    assert V.rewrite_prompt_sha() == V.rewrite_prompt_sha()


def test_the_two_prompts_are_told_apart():
    """턴당 프롬프트가 둘이다. 한 필드에 뭉뚱그리면 어느 쪽이 바뀌었는지 못 본다."""
    assert V.prompt_version() != V.rewrite_prompt_sha()


def test_every_listed_module_is_really_read():
    """목록의 오타는 **조용히** 재료를 줄인다 — 못 읽은 모듈은 빈 문자열이 되고, 빈 문자열은
    언제나 같은 값이라 그 모듈을 고쳐도 버전이 안 바뀐다. 옛 결함과 같은 모양이다."""
    unread = [m for m in V.ASSEMBLY_MODULES if not V._module_source(m)]
    assert not unread, f"소스를 못 읽은 모듈: {unread}"


@pytest.mark.parametrize("module", V.ASSEMBLY_MODULES)
def test_changing_any_assembly_module_changes_the_value(module, monkeypatch):
    """**값이 안 바뀌면 기록은 아무것도 말하지 않는다.** 목록의 모듈마다 확인한다."""
    before = V.prompt_version()
    real = V._module_source

    def edited(name):
        text = real(name)
        return text + "\n# 한 줄 더.\n" if name == module else text

    monkeypatch.setattr(V, "_module_source", edited)
    V._assembly_sources.cache_clear()
    assert V.prompt_version() != before


def test_the_weak_evidence_rule_moves_the_value(monkeypatch):
    """옛 핑거프린트가 놓친 첫 조각 — 08-18 에 붙은 물러남 규칙. 그 문장을 고치면 버전이 바뀌어야 한다."""
    from nexus.llm import prompts as P

    before = V.prompt_version()
    real = V._module_source
    sentence = "짧게 끝내세요."
    assert sentence in P.WEAK_EVIDENCE_RULE, "검사가 겨누는 문장이 규칙에서 사라졌다"

    def edited(name):
        text = real(name)
        return text.replace(sentence, "길게 설명하세요.") if name == "nexus.llm.prompts" else text

    monkeypatch.setattr(V, "_module_source", edited)
    V._assembly_sources.cache_clear()
    assert V.prompt_version() != before


def test_an_unreadable_source_does_not_break_the_answer_path(monkeypatch):
    """진단이 답변을 죽일 수 없다 — 소스를 못 읽는 배포(동결 바이너리 등)도 있다."""
    monkeypatch.setattr(V.inspect, "getsource", lambda _obj: (_ for _ in ()).throw(OSError()))
    V._assembly_sources.cache_clear()
    assert isinstance(V.prompt_version(), str)
    assert len(V.prompt_version()) == 12


def test_the_query_and_evidence_do_not_enter_the_value():
    """질의·답변 근거를 넣으면 모든 행이 서로 달라 아무것도 구분하지 못한다 — 그리고 텍스트가 샌다."""
    assert V.fingerprint("시스템", "템플릿") == V.fingerprint("시스템", "템플릿")
    # 조각 경계가 있어야 이어붙임 모호성이 없다: ("ab","c") 와 ("a","bc") 는 달라야 한다.
    assert V.fingerprint("ab", "c") != V.fingerprint("a", "bc")


# ── 목록이 **실제로 도는 코드**를 덮는가 ─────────────────────────────────────────
#
# ⛔ 옛 결함의 모양은 「있는 줄 알았던 재료가 없었다」 였다. 목록을 사람이 적는 한 같은 일이
# 다시 난다 — 누군가 `format_for_llm` 이 부르는 도우미를 새 모듈에 두는 날. 그래서 목록을
# 읽지 않고, **프롬프트를 실제로 한 벌 쓰게 하고 그동안 실행된 모듈을 센다.**

def _nexus_modules_run_by(fn) -> set[str]:
    """`fn()` 이 도는 동안 **실행된** nexus 모듈 전부. 이름이 아니라 실행을 센다."""
    seen: set[str] = set()

    def tracer(frame, event, _arg):
        if event == "call":
            name = frame.f_globals.get("__name__", "")
            if name == "nexus" or name.startswith("nexus."):
                seen.add(name)

    previous = sys.getprofile()
    sys.setprofile(tracer)
    try:
        fn()
    finally:
        sys.setprofile(previous)
    return seen


def _a_packet_that_takes_every_branch():
    """`format_for_llm` 의 하위 범주를 전부 타는 근거 묶음 — 등급 셋 · 앵커 · 지운 이름 · 인용 문법이
    든 본문 · 코드 값(판정 있음/없음, 불일치) · 그래프(설계·관측)."""
    from nexus.index.anchors import CHANGED, FRESH
    from nexus.repositories.graph import EdgeResult, ObservedEdgeResult, SubGraph
    from nexus.search.anchor_status import AnchorStatus, DeletedMention
    from nexus.search.evidence_packet import (
        CodeValue, EvidencePacket, EvidenceSnippet, Provenance,
    )
    from nexus.search.provenance import AUTHORED, MACHINE_READ, MACHINE_WRITTEN

    def snippet(i, tier, **kw):
        return EvidenceSnippet(
            chunk_rid=f"c{i}", doc_rid=f"d{i}", doc_title=f"문서 {i}", section_path="§1",
            source_uri=f"t:doc{i}.md", text="짧은 본문", score=1.0,
            classification="INTERNAL", doc_type="policy", provenance_tier=tier, **kw)

    return EvidencePacket(
        snippets=[
            snippet(1, AUTHORED,
                    code_anchors=[AnchorStatus("OrderService", FRESH),
                                  AnchorStatus("PartyRoom", CHANGED)],
                    code_deleted=[DeletedMention("OldGuard", "2026-09-01", "abc123", "정리")]),
            snippet(2, MACHINE_READ, full_text="그림에서 읽은 표"),
            snippet(3, MACHINE_WRITTEN, full_text="지난 설명 [출처: 다른 문서, §2] 끝"),
        ],
        graph=SubGraph(
            center_rid="e1", center_name="주문",
            edges=[EdgeResult("r1", "CALLS", "e1", "주문", "e2", "결제", 0.9, "DESIGNED")],
            observed_edges=[ObservedEdgeResult("o1", "CALLS_OBSERVED", "e1", "주문", "e2", "결제",
                                               12, 0.01, 30.0, "2026-09-30", [], "ref")]),
        provenance=[Provenance(doc_rid="d1", source_uri="t:doc1.md", doc_title="문서 1")],
        code_values=[
            CodeValue(statement="정원", value="50", source="Guard.java:10", drifted=True),
            CodeValue(statement="정원", value="50", source="Guard.java:10",
                      ruled_value="50", ruled_by="owner", ruled_on="2026-09-23",
                      ruled_source="코드", ruling_note="문서가 낡았다", ruling_conflict=True),
        ],
    )


def _write_one_prompt():
    """근거 묶음은 **추적 밖에서** 만든다. 안에서 만들면 데이터클래스 생성자(그래프 · 앵커)가
    「프롬프트를 쓰는 코드」로 잡힌다 — 이 검사가 처음 돌았을 때 실제로 그렇게 잘못 걸렸다."""
    from nexus.llm.prompts import build_prompts
    from nexus.search.evidence_packet import format_for_llm

    packet = _a_packet_that_takes_every_branch()

    def write():
        evidence_text = format_for_llm(packet)
        # 재작성이 문장을 바꾼 턴 · 답변 근거가 약한 턴 — 시스템 프롬프트의 하위 범주 둘을 다 탄다.
        build_prompts("재작성된 질의", evidence_text, "사용자가 친 문장", weak_evidence=True)

    return write


def test_everything_that_writes_the_prompt_is_covered():
    """프롬프트를 쓰는 동안 실행된 nexus 모듈이 **전부 재료 목록 안에** 있어야 한다."""
    ran = _nexus_modules_run_by(_write_one_prompt())
    uncovered = sorted(ran - set(V.ASSEMBLY_MODULES))
    assert not uncovered, (
        f"프롬프트를 쓰는 데 돌았는데 판에 안 들어가는 모듈: {uncovered} — "
        "`ASSEMBLY_MODULES` 에 더하라")


def test_the_trace_really_sees_the_prompt_being_written():
    """⛔ **안 도는 계측기는 틀린 값이 아니라 아무 값도 안 낸다.** 추적이 죽어 있으면 위 검사는
    빈 집합을 보고 초록이다. 알려진 모듈이 실제로 잡히는지 먼저 본다."""
    ran = _nexus_modules_run_by(_write_one_prompt())
    for expected in ("nexus.llm.prompts", "nexus.search.evidence_packet",
                     "nexus.search.provenance", "nexus.search.anchor_status",
                     "nexus.llm.citations"):
        assert expected in ran, f"{expected} 가 실행으로 안 잡혔다 — 추적 또는 꾸러미를 의심하라"


def test_the_coverage_check_can_fail():
    """**고친 가드 검사는 일부러 깨 봐라.** 목록에서 하나를 빼면 그 모듈이 걸려야 한다."""
    ran = _nexus_modules_run_by(_write_one_prompt())
    shorter = set(V.ASSEMBLY_MODULES) - {"nexus.search.provenance"}
    assert "nexus.search.provenance" in (ran - shorter)


# ── 기록과 응답에 실제로 남는가 ────────────────────────────────────────────────

from nexus.search import signals as S  # noqa: E402


def _sig(**kw):
    from nexus.search.hybrid import SearchResult

    base = dict(path="search", tenant="t", clearance="INTERNAL", query="q", latency_ms=1)
    return S.extract_signals(SearchResult(), kw.pop("answer", None), **{**base, **kw})


def test_an_answer_row_carries_the_version_the_answer_carried():
    """기록은 **응답이 실은 것과 같은 값**이어야 한다 — 따로 다시 세면 둘이 갈릴 수 있다."""
    from nexus.llm.answer import AnswerResult

    sig = _sig(path="search_answer", answer=AnswerResult(answer="답", prompt_version="a1b2c3d4e5f6"))
    assert sig.prompt_version == "a1b2c3d4e5f6"


def test_the_streaming_row_takes_the_version_it_is_given():
    """스트리밍 경로는 `AnswerResult` 없이 기록한다 — 버전을 **명시로** 넘긴다. 옛 버전은 이 경로의
    버전을 한 번도 안 남겼다(`answer` 가 `None` 이라 빈 문자열이었다)."""
    sig = _sig(path="search_answer_stream", prompt_version="a1b2c3d4e5f6")
    assert sig.prompt_version == "a1b2c3d4e5f6"


def test_a_search_only_row_claims_no_prompt():
    """검색 전용 경로에 답변 프롬프트의 버전을 적으면 그것은 거짓이다."""
    assert _sig().prompt_version == ""


def test_the_rewrite_prompt_is_recorded_only_when_it_ran():
    from nexus.search.rewrite import Rewrite

    assert _sig().rewrite_prompt_sha == ""
    assert _sig(rewrite=Rewrite(query="q", called=False)).rewrite_prompt_sha == ""
    called = _sig(rewrite=Rewrite(query="q2", called=True, changed=True))
    assert called.rewrite_prompt_sha == V.rewrite_prompt_sha()


def test_the_signal_carries_the_fingerprint_not_the_prompt():
    from nexus.llm.answer import AnswerResult
    from nexus.llm.prompts import SYSTEM_PROMPT

    sig = _sig(path="search_answer", answer=AnswerResult(answer="답", prompt_version=V.prompt_version()))
    assert SYSTEM_PROMPT[:40] not in repr(sig), "프롬프트 본문이 신호에 실렸다"
    assert len(sig.prompt_version) == 12


async def test_the_shared_seam_stamps_the_version():
    """답변 경로 넷이 전부 지나는 자리에서 찍는다 — API 표면마다 붙이면 하나가 조용히 빠진다."""
    from nexus.search import reconcile

    class _R:
        hits: list = []
        graph = None
        fill: list = []

    packet = await reconcile.packet_for_answer(
        _R(), "default", "INTERNAL", config={"search": {}}, search=None, question=None, pool=None)
    assert packet.prompt_version == V.prompt_version()


async def test_the_answer_carries_what_the_packet_was_stamped_with():
    """기권(답변 근거 0건)도 조립은 돌았다 — 버전은 **LLM 을 불렀는가**와 무관하게 실린다."""
    from nexus.llm.answer import generate_answer
    from nexus.search.evidence_packet import EvidencePacket

    result = await generate_answer("질문", EvidencePacket(prompt_version="a1b2c3d4e5f6"), llm_svc=None)
    assert result.abstained is True
    assert result.prompt_version == "a1b2c3d4e5f6"
