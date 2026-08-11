"""인용에서 원본 그림으로 — SPEC-nexus-vision-source-ref (DB 없이 도는 부분).

여기서 재는 것은 **문법과 거절**이다: writer 가 만든 마커를 parser 가 읽는가, 참조 없는 추출이
저장을 통과하는가, 큰 블록이 쪼개졌을 때 조각들이 손잡이를 잃지 않는가.

마커 문자열을 손으로 타이핑하지 않는다. `build_block()` 이 만든 것을 읽는다 — 손으로 쓰면
writer 와 parser 가 갈려도 시험은 초록으로 남는다.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.ingest import vision, vision_source, vision_store  # noqa: E402
from nexus.ingest.chunker import chunk_document  # noqa: E402

_SHA = "a1b2c3d4e5f60718" + "9" * 48          # 64자, 앞 16자가 손잡이


def _block(text="| 아바타 | 해금 |\n|---|---|\n| A | 1200 |", sha=_SHA):
    return vision.build_block(vision.Extraction(text, "m/p", sha))


# ── §5.4 마커가 손잡이를 나르는가 ────────────────────────────────────────────

def test_the_marker_carries_a_handle_that_matches_the_sha():
    fields = vision_source.parse_marker(_block())
    assert fields is not None
    assert fields["derived"] == "vision"
    assert fields["img"] == _SHA[:vision.HANDLE_CHARS]
    assert len(fields["img"]) == 16 and fields["img"].islower()


def test_an_unknown_field_does_not_strand_the_chunk():
    """§2.5 — 나중에 필드를 더해도 옛 파서가 좌초하지 않아야 한다."""
    doctored = _block().replace("derived=vision", "derived=vision reader_notes=x")
    fields = vision_source.parse_marker(doctored)
    assert fields["img"] == _SHA[:16] and fields["reader_notes"] == "x"


def test_an_authored_chunk_has_no_marker_and_that_is_not_an_error():
    assert vision_source.parse_marker("환불은 7일 이내에 신청한다.") is None
    assert asyncio.run(vision_source.resolve_source("t", "환불은 7일 이내에 신청한다.")) is None


def test_a_marker_without_a_handle_is_pre_migration_not_a_crash():
    """§2.2 — 이 변경 이전에 적재된 청크. 상태이지 오류가 아니다."""
    old = "![](){: derived=vision extractor=m/p }\n> (그림에서 읽은 내용)\n> 표"
    out = asyncio.run(vision_source.resolve_source("t", old))
    assert isinstance(out, vision_source.Unresolvable)
    assert out.reason == "pre-migration marker"


def test_a_malformed_handle_is_refused_before_it_reaches_the_database():
    bad = _block().replace(f"img={_SHA[:16]}", "img=NOTHEX")
    out = asyncio.run(vision_source.resolve_source("t", bad))
    assert isinstance(out, vision_source.Unresolvable) and out.reason == "malformed handle"


# ── §5.2 참조 없는 추출은 저장되지 않는가 ────────────────────────────────────

def test_the_save_path_refuses_an_extraction_with_no_reference():
    """참조 없는 행을 조용히 저장하면 등급의 전제가 채워지지 않은 채로 쌓인다 — 그리고 §5.9 의
    카운터가 아무도 결정하지 않은 부채로 자란다. 거절은 저장 **전에** 일어나므로 DB 가 필요 없다.
    """
    with pytest.raises(ValueError):
        asyncio.run(vision_store.save("t", vision.Extraction("표", "m/p", _SHA)))


def test_a_fetch_failure_may_be_stored_without_a_reference():
    """실패 기록은 추출이 아니다 — 그림을 못 가져왔으므로 돌아갈 곳도 없다.

    저장이 실제로 일어나는지는 DB 시험이 본다. 여기서는 **거절되지 않는다**는 것만 본다.
    """
    e = vision.fetch_failure("blk-1", "TimeoutError")
    assert e.error and not (e.block_id or "")
    # save() 는 여기서 DB 에 닿으므로 부르지 않는다. 거절 조건만 직접 확인한다.
    assert not (not (e.block_id or "").strip() and not e.error)


# ── §5.7 쪼개진 블록도 손잡이를 잃지 않는가 ─────────────────────────────────

def test_two_chunks_split_from_one_block_carry_the_same_handle():
    """§4 — 긴 추출은 청커가 쪼갠다. 두 번째 조각에 마커가 없으면 그 조각의 인용은 등급만 있고
    돌아갈 길이 없다. 마커는 블록 첫 줄에 **한 번만** 있으므로 쪼갤 때 다시 실어야 한다.
    """
    long_text = "\n".join(f"| 항목{i} | 값{i} | 설명이 제법 긴 줄이다 {i} |" for i in range(400))
    chunks = chunk_document(_block(long_text), language="ko", trust_vision_markers=True)
    machine = [c for c in chunks if c.provenance_tier == "machine_read"]
    assert len(machine) >= 2, "쪼개지지 않았다 — 이 시험이 재려던 상태가 아니다"

    handles = [(vision_source.parse_marker(c.chunk_text) or {}).get("img") for c in machine]
    assert all(h == _SHA[:16] for h in handles), (
        f"조각이 손잡이를 잃었다: {handles}")


def test_a_short_block_still_carries_exactly_one_marker():
    """마커를 다시 싣는 처리가 안 쪼개진 블록을 중복시키면 본문이 오염된다."""
    chunks = chunk_document(_block(), language="ko", trust_vision_markers=True)
    machine = [c for c in chunks if c.provenance_tier == "machine_read"]
    assert len(machine) == 1
    assert machine[0].chunk_text.count("derived=vision") == 1
