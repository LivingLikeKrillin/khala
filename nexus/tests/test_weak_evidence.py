"""근거 적합도 — **자로는 안 보이고 사람만 알던 결함**의 회귀 검사.

사용자 신고(2026-08-18): "답변 품질이 영 석연치 않아서" 팀이 안 쓴다. 재현해 보니 코퍼스 밖
질문에도 근거 10개가 채워지고 모델이 그걸로 길게 답했다(이름을 물었는데 기술 스택 표). 이건
환각이 아니라서 `grounded`·인용 검증·사실 검사를 **전부 통과한다** — 그래서 평가 하니스가 못 봤다.

여기서 단언하는 것은 점수가 아니라 **계약**이다: 약하면 프롬프트가 바뀌고, 약하지 않으면
프롬프트가 **바이트 단위로 예전과 같다**.
"""

from __future__ import annotations

import pytest

from nexus.llm.prompts import build_prompts, build_system_prompt
from nexus.search.confidence import FAR_DISTANCE, WEAK_BM25, Confidence


def test_both_legs_must_be_weak():
    """한쪽만 약한 것은 흔하다 — 그걸로 판정하면 정상 답변이 '범위 밖' 으로 찍힌다."""
    far, near = FAR_DISTANCE + 0.05, FAR_DISTANCE - 0.05
    lo, hi = WEAK_BM25 - 0.5, WEAK_BM25 + 0.5

    assert Confidence(top_distance=far, top_bm25=lo).weak
    assert not Confidence(top_distance=near, top_bm25=lo).weak   # 벡터가 잡았다
    assert not Confidence(top_distance=far, top_bm25=hi).weak    # 키워드가 잡았다
    assert not Confidence(top_distance=near, top_bm25=hi).weak


def test_a_dead_leg_is_not_evidence_of_weakness():
    """못 잰 것과 재서 낮은 것은 다른 사실이다. 이 혼동이 이 리포의 반복 결함이었다."""
    assert not Confidence(top_distance=None, top_bm25=0.1).weak
    assert not Confidence(top_distance=0.9, top_bm25=None).weak
    assert not Confidence().weak


def test_the_measured_boundary_still_separates():
    """2026-08-18 라이브 실측의 양 끝. 문턱을 옮기면 여기가 빨간불이 된다 —
    옮기는 것 자체는 자유지만 **모르고** 옮히는 것은 막는다."""
    answerable = Confidence(top_distance=0.4552, top_bm25=2.0)      # 답 가능 쪽 최악
    out_of_scope = Confidence(top_distance=0.5071, top_bm25=1.0)    # 밖 질문 쪽 최선
    assert not answerable.weak
    assert out_of_scope.weak


def test_the_prompt_is_unchanged_when_evidence_is_fine():
    """**바이트 단위로 같다.** 이 약속이 깨지면 예전 측정과의 비교가 전부 끊긴다."""
    assert build_system_prompt(False, weak_evidence=False) == build_system_prompt(False)
    assert build_prompts("q", "ev") == build_prompts("q", "ev", weak_evidence=False)


def test_the_prompt_changes_only_the_system_half_when_weak():
    sys_ok, user_ok = build_prompts("q", "ev")
    sys_weak, user_weak = build_prompts("q", "ev", weak_evidence=True)
    assert user_weak == user_ok, "사용자 프롬프트는 건드리지 않는다 — 질문과 근거는 그대로다"
    assert len(sys_weak) > len(sys_ok)
    # 규칙이 요구하는 두 가지가 실제로 프롬프트에 있는가
    assert "범위" in sys_weak or "없는 것으로" in sys_weak
    assert "짧게" in sys_weak


@pytest.mark.asyncio
async def test_weak_evidence_never_blocks_the_answer():
    """**막는 판정은 근거 0건뿐이다.** 적합도는 서술 계약이지 게이트가 아니다 —
    문턱이 틀렸을 때의 피해를 '나쁜 침묵' 이 아니라 '짧은 답' 으로 묶어 둔다."""
    from nexus.llm.answer import generate_answer
    from nexus.search.evidence_packet import EvidencePacket, EvidenceSnippet

    class _Usage:
        input_tokens = output_tokens = 0
        cost_usd = None
        model = "fake"

    class _Res:
        text = "짧은 답"
        usage = _Usage()

    class _LLM:
        def __init__(self): self.seen = ""
        async def generate_full(self, system, user):
            self.seen = system
            return _Res()

    packet = EvidencePacket(snippets=[EvidenceSnippet(
        chunk_rid="c1", doc_rid="d1", doc_title="T", section_path="s",
        source_uri="u", text="본문", score=0.0, classification="INTERNAL")])
    llm = _LLM()
    out = await generate_answer("질문", packet, llm_svc=llm,
                                confidence=Confidence(top_distance=0.9, top_bm25=0.1))
    assert out.abstained is False, "적합도로 기권시키지 않는다"
    assert out.weak_evidence is True
    assert "짧게" in llm.seen, "약한 근거 규칙이 실제로 모델에게 갔다"
