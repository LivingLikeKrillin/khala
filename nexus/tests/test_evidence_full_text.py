"""LLM 근거와 사람 미리보기를 가른다.

`_truncate_snippet` 은 300자에서 자른다. 화면엔 알맞은 값이고 프롬프트엔 답을 잘라먹는 값이다.
2026-08-08 실측: 846자짜리 역할·권한 표에서 앞 300자만 넘어가, 모델이 "표가 중간에 잘려 있어
대기열잠금 항목이 포함된 행이 제공되지 않았습니다" 라고 **정확히** 말하고 답을 못 했다.

그때 검색은 그 청크를 **1위**로 뽑았고 문서 단위 `Recall@10` 은 **1.000** 이었다. 검색만 측정하는
자에는 안 보이는 구간이 여기다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.search.evidence_packet import assemble_packet, format_for_llm  # noqa: E402
from nexus.search.hybrid import SearchHit, _truncate_snippet  # noqa: E402

TABLE = ("| 역할 | 대기열 잠금 |\n|---|---|\n"
         + "\n".join(f"| 행{i} | 값{i} |" for i in range(80))
         + "\n| Mod | 가능 |\n")


def _hit(**kw):
    base = dict(rid="c1", doc_rid="d1", doc_title="[파티룸] 디제잉 정책",
                section_path="참고", source_uri="u", score=0.9)
    base.update(kw)
    return SearchHit(**base)


async def test_the_prompt_gets_the_whole_chunk():
    """**이것이 빠져 있던 것.** 표의 마지막 행이 프롬프트에 있어야 답을 할 수 있다."""
    packet = await assemble_packet([_hit(snippet=_truncate_snippet(TABLE, 300), chunk_text=TABLE)])
    prompt = format_for_llm(packet)
    assert "| Mod | 가능 |" in prompt, "표의 끝이 프롬프트에 없다 — 잘린 채로 나갔다"


async def test_the_human_preview_stays_short():
    """웹·Slack·API 가 읽는 값은 안 바뀐다 — 화면에 청크 전문을 쏟으면 그건 다른 결함이다."""
    short = _truncate_snippet(TABLE, 300)
    packet = await assemble_packet([_hit(snippet=short, chunk_text=TABLE)])
    s = packet.snippets[0]
    assert s.text == short and len(s.text) <= 320
    assert s.full_text == TABLE


async def test_a_hit_without_a_full_text_falls_back():
    """옛 호출부(테스트 픽스처 포함)가 chunk_text 를 안 채워도 프롬프트가 비면 안 된다."""
    packet = await assemble_packet([_hit(snippet="짧은 조각")])
    assert packet.snippets[0].full_text == "짧은 조각"
    assert "짧은 조각" in format_for_llm(packet)


def test_the_two_are_actually_different_here():
    """둘이 같으면 이 검사는 아무것도 안 본다 — 입력이 상한을 넘는지부터 확인한다."""
    assert len(TABLE) > 300
    assert _truncate_snippet(TABLE, 300) != TABLE
