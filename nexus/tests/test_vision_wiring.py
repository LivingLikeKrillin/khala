"""그림 → 본문 → chunk 배선 (SPEC-nexus-screenshot-text-extraction §4.1, §4.4).

순회는 동기, 추출은 비동기라 2패스로 갈라 뒀다. 여기서 재는 것은 그 이음매가 새지 않는가다:

    URL 을 순회 중에 잡는가 · 자리 표식이 본문에 남지 않는가 · 꺼져 있으면 예전 그대로인가 ·
    같은 바이트를 두 번 안 읽는가 · 격리될 텍스트가 durable 저장에 안 들어가는가

**추출 품질은 여기서 안 잰다.** 판독기는 스텁이다.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.ingest import vision, vision_store  # noqa: E402
from nexus.ingest.chunker import chunk_document  # noqa: E402
from nexus.ingest.sources.notion_convert import blocks_to_markdown, image_slot  # noqa: E402


def _image_block(bid="blk-1", url="https://s3/x.png?X-Amz-Expires=3600", caption=""):
    return {"id": bid, "type": "image",
            "image": {"file": {"url": url},
                      "caption": ([{"plain_text": caption}] if caption else [])}}


def _text_block(t):
    return {"id": "t-" + t[:4], "type": "paragraph",
            "paragraph": {"rich_text": [{"plain_text": t}]}}


# ── 1패스: 순회가 URL 을 챙기는가 ─────────────────────────────────────────────

def test_the_walk_captures_the_url_because_it_expires():
    """Notion 이 주는 것은 한 시간이면 죽는 서명 링크다. 순회 중에 안 챙기면 나중에 다시
    물어야 하고, 그때는 이미 늦다."""
    sink = []
    md, count = blocks_to_markdown([_text_block("앞"), _image_block(url="https://s3/a.png")],
                                   None, image_sink=sink)
    assert count == 1
    assert sink == [{"block_id": "blk-1", "url": "https://s3/a.png", "caption": ""}]
    assert image_slot("blk-1") in md


def test_without_a_sink_the_old_behaviour_is_unchanged():
    """추출이 꺼진 배포와 기존 테스트가 이 경로로 돈다."""
    md, count = blocks_to_markdown([_image_block(caption="그림 3. 환불 흐름")], None)
    assert "![그림 3. 환불 흐름]()" in md and "khala:vision:slot" not in md
    assert count == 1


def test_the_caption_still_survives_into_the_sink():
    """캡션은 그 문서가 쓰는 어휘다 — 예전에 통째로 버렸다가 검색 텍스트 0 인 문서를 만들었다."""
    sink = []
    blocks_to_markdown([_image_block(caption="그림 3")], None, image_sink=sink)
    assert sink[0]["caption"] == "그림 3"


# ── 2패스: 자리 표식이 반드시 사라지는가 ──────────────────────────────────────

class _Reader:
    model = "test-vision"

    def __init__(self, reply="| 아바타 | 해금 |\n|---|---|\n| A | 1200 |"):
        self.reply, self.calls = reply, 0

    async def vision_extract(self, system, image_b64, media_type, max_tokens):
        self.calls += 1
        return self.reply, "end_turn"


def test_no_slot_marker_survives_into_the_body(monkeypatch):
    """표식이 남으면 청커가 거기서 갈리고, 남의 마커를 흉내 낸 것과 구별되지 않는다."""
    async def _fetch(url):
        return b"\x89PNG bytes", "image/png"

    monkeypatch.setattr(vision_store, "_fetch_bytes", _fetch)
    monkeypatch.setattr(vision_store, "load", lambda *a, **k: _none())
    monkeypatch.setattr(vision_store, "save", lambda t, e: _echo(e))

    md = f"앞\n\n{image_slot('blk-1')}\n\n뒤\n"
    out, n = asyncio.run(vision_store.apply(
        md, [{"block_id": "blk-1", "url": "u", "caption": ""}],
        tenant="t", llm_svc=_Reader()))
    assert "khala:vision:slot" not in out and n == 1
    assert vision.VISION_BEGIN in out


def test_a_fetch_failure_leaves_a_bare_placeholder_not_a_slot(monkeypatch):
    async def _boom(url):
        raise TimeoutError("expired")

    monkeypatch.setattr(vision_store, "_fetch_bytes", _boom)
    saved = []
    monkeypatch.setattr(vision_store, "save", lambda t, e: _record(saved, e))

    md = f"앞\n{image_slot('blk-9')}\n"
    out, n = asyncio.run(vision_store.apply(
        md, [{"block_id": "blk-9", "url": "u", "caption": ""}],
        tenant="t", llm_svc=_Reader()))
    assert "khala:vision:slot" not in out and "![]()" in out and n == 0
    assert saved and saved[0].error and not saved[0].fetched, (
        "가져오기 실패가 기록되지 않으면 다음 적재에서 body 가 달라져 content_hash 가 왕복한다")


def test_the_ceiling_clears_the_slots_it_skipped(monkeypatch):
    """상한에 걸려 못 읽은 자리도 본문에서는 지워야 한다."""
    monkeypatch.setenv("NEXUS_VISION_MAX_PER_INGEST", "1")

    async def _fetch(url):
        return b"png", "image/png"

    monkeypatch.setattr(vision_store, "_fetch_bytes", _fetch)
    monkeypatch.setattr(vision_store, "load", lambda *a, **k: _none())
    monkeypatch.setattr(vision_store, "save", lambda t, e: _echo(e))

    images = [{"block_id": f"b{i}", "url": "u", "caption": ""} for i in range(3)]
    md = "\n".join(image_slot(i["block_id"]) for i in images)
    out, n = asyncio.run(vision_store.apply(md, images, tenant="t", llm_svc=_Reader()))
    assert "khala:vision:slot" not in out and n == 1


# ── 저장: 같은 바이트를 두 번 읽지 않는가 ─────────────────────────────────────

def test_a_stored_extraction_is_not_read_again(monkeypatch):
    """[[ADR-0010]] §5 — 재적재는 저장된 결과를 읽는다. 다시 읽으면 비결정적 판독기가
    바뀌지 않은 신원 아래로 드리프트한 텍스트를 넣는다."""
    async def _fetch(url):
        return b"same bytes", "image/png"

    monkeypatch.setattr(vision_store, "_fetch_bytes", _fetch)
    monkeypatch.setattr(vision_store, "load",
                        lambda *a, **k: _value({"text": "저장된 표", "error": None,
                                                "truncated": False}))
    reader = _Reader()
    out, n = asyncio.run(vision_store.apply(
        f"{image_slot('b1')}", [{"block_id": "b1", "url": "u", "caption": ""}],
        tenant="t", llm_svc=reader))
    assert reader.calls == 0, "저장된 결과가 있는데 판독기를 다시 불렀다"
    assert "저장된 표" in out


def test_quarantined_text_never_reaches_the_durable_store(monkeypatch):
    """스캔이 저장보다 **먼저**다. 그림 속 업무 이메일은 추출물이 되어야만 스캐너 눈에 보이고,
    격리될 텍스트를 저장하면 chunk 를 격리해도 그 문자열은 지울 경로 없는 행에 남는다."""
    async def _fetch(url):
        return b"png", "image/png"

    monkeypatch.setattr(vision_store, "_fetch_bytes", _fetch)
    monkeypatch.setattr(vision_store, "load", lambda *a, **k: _none())
    saved = []
    monkeypatch.setattr(vision_store, "save", lambda t, e: _record(saved, e))

    out, n = asyncio.run(vision_store.apply(
        image_slot("b1"), [{"block_id": "b1", "url": "u", "caption": ""}],
        tenant="t", llm_svc=_Reader("연락처: someone@example.com"),
        pii_patterns={"email": r"[\w.]+@[\w.]+\.\w+"}))
    assert n == 0 and "someone@example.com" not in out
    assert saved and saved[0].text == "", "격리 대상 텍스트가 저장 행에 실렸다"
    assert "quarantined" in saved[0].error


# ── 끝에서 끝: 그림이 machine_read chunk 가 되는가 ───────────────────────────

def test_an_image_becomes_a_machine_read_chunk(monkeypatch):
    """이 배선의 전부 — 그림 한 장이 본문을 거쳐 등급이 붙은 chunk 로 나오는가."""
    async def _fetch(url):
        return b"png", "image/png"

    monkeypatch.setattr(vision_store, "_fetch_bytes", _fetch)
    monkeypatch.setattr(vision_store, "load", lambda *a, **k: _none())
    monkeypatch.setattr(vision_store, "save", lambda t, e: _echo(e))

    sink = []
    md, _ = blocks_to_markdown(
        [_text_block("아바타 해금 기준은 아래와 같다."), _image_block(),
         _text_block("문의는 담당자에게.")], None, image_sink=sink)
    body, n = asyncio.run(vision_store.apply(md, sink, tenant="t", llm_svc=_Reader()))
    assert n == 1

    chunks = chunk_document(body, language="ko", trust_vision_markers=True)
    machine = [c for c in chunks if c.provenance_tier == "machine_read"]
    authored = [c for c in chunks if c.provenance_tier == "authored"]
    assert machine and authored
    assert "1200" in " ".join(c.chunk_text for c in machine)
    assert "1200" not in " ".join(c.chunk_text for c in authored)


# ── 테스트용 async 헬퍼 ───────────────────────────────────────────────────────

async def _none():
    return None


async def _value(v):
    return v


async def _echo(e):
    return {"text": e.text, "error": e.error, "truncated": e.truncated}


async def _record(bucket, e):
    bucket.append(e)
    return {"text": e.text, "error": e.error, "truncated": e.truncated}


# ── 가져오는 쪽도 묶여 있는가 (SSRF) ─────────────────────────────────────────

def test_internal_addresses_are_refused():
    """**이 URL 은 신뢰할 수 없다.** Notion 이미지 블록은 `external` 도 되고, 그건 페이지를
    편집할 수 있는 사람이 넣은 임의의 주소다.

    그리고 여기서 SSRF 는 요청 하나로 끝나지 않는다: 가져온 바이트가 판독기로 가고, 판독기는
    그것을 **문서 본문으로 옮겨 적는다.** 메타데이터 엔드포인트를 이미지로 걸면 자격증명이
    검색 가능한 인용 텍스트가 된다. ADR-0010 §6 은 판독기를 묶었는데 가져오는 쪽이 안 묶여
    있었고, 그쪽이 더 이른 관문이다.
    """
    for url in ("https://localhost/x.png",
                "https://127.0.0.1/x.png",
                "https://169.254.169.254/latest/meta-data/",   # 클라우드 메타데이터
                "https://10.0.0.5/x.png",
                "https://192.168.1.1/x.png"):
        with pytest.raises(vision_store.UnsafeImageURL):
            vision_store.check_url(url)


def test_non_https_schemes_are_refused():
    """평문과 파일 스킴은 아예 받지 않는다 — `file://` 은 판독기에 닫아 둔 파일시스템을
    가져오는 쪽으로 다시 여는 길이다."""
    for url in ("http://example.com/x.png", "file:///etc/passwd", "gopher://x/1"):
        with pytest.raises(vision_store.UnsafeImageURL):
            vision_store.check_url(url)


def test_a_public_https_url_passes():
    vision_store.check_url("https://example.com/x.png")


def test_a_refused_url_is_recorded_as_a_failure_not_silently_skipped(monkeypatch):
    """거부도 실패 행으로 남아야 한다 — 안 그러면 다음 적재의 body 가 달라진다."""
    saved = []
    monkeypatch.setattr(vision_store, "save", lambda t, e: _record(saved, e))
    out, n = asyncio.run(vision_store.apply(
        image_slot("b1"), [{"block_id": "b1", "url": "https://127.0.0.1/x.png", "caption": ""}],
        tenant="t", llm_svc=_Reader()))
    assert n == 0 and "khala:vision:slot" not in out
    assert saved and "UnsafeImageURL" in saved[0].error


# ── 플래그가 청커까지 닿는가 (라이브에서 실제로 끊겼던 곳) ────────────────────

def test_the_trust_flag_survives_csf_and_frontmatter():
    """**라이브에서 실제로 끊겼던 이음매.** 2026-08-10 첫 실적재에서 11장이 전부 추출돼
    본문에 들어갔는데 `machine_read` chunk 는 0개였다 — 청커가 마커를 못 믿고 벗겨서 추출
    텍스트가 **저자 텍스트로 세탁**됐다. ADR-0010 §4 가 "추출 안 하느니만 못하다" 고 한 상태다.

    통로는 하나뿐이다: ConvertedDoc → CSF → 임시 파일 frontmatter → CollectedFile → 청커.
    한 칸이라도 빠지면 같은 일이 조용히 다시 일어난다.
    """
    from nexus.a2a.server import _csf_to_markdown_file
    from nexus.ingest.sources.base import ConvertedDoc
    from nexus.ingest.sources.notion_importer import build_csf

    conv = ConvertedDoc(page_id="p1", markdown="본문", frontmatter={"title": "정책"},
                        image_count=1, vision_extracted=True)
    csf = build_csf(conv, "p1")
    assert csf["vision_extracted"] is True, "CSF 가 플래그를 안 나른다"

    md = _csf_to_markdown_file(csf)
    assert "vision_extracted: true" in md, "frontmatter 가 플래그를 안 싣는다"


def test_a_document_without_extraction_does_not_claim_trust():
    """추출을 안 한 문서가 신뢰를 주장하면, 남의 마커를 흉내 낸 본문이 machine_read 로 찍힌다."""
    from nexus.a2a.server import _csf_to_markdown_file
    from nexus.ingest.sources.base import ConvertedDoc
    from nexus.ingest.sources.notion_importer import build_csf

    csf = build_csf(ConvertedDoc(page_id="p2", markdown="본문", frontmatter={"title": "메모"}), "p2")
    assert csf["vision_extracted"] is False
    assert "vision_extracted" not in _csf_to_markdown_file(csf)


def test_the_collector_reads_the_flag_from_frontmatter():
    """collector 가 안 읽으면 frontmatter 에 실어도 소용없다 — 그게 마지막 칸이다."""
    import inspect

    from nexus.ingest import collector

    src = inspect.getsource(collector)
    assert 'fm.get("vision_extracted"' in src, "collector 가 frontmatter 에서 플래그를 안 읽는다"


def test_the_pipeline_passes_the_flag_to_the_chunker():
    import inspect

    from nexus.ingest import pipeline

    src = inspect.getsource(pipeline)
    assert "trust_vision_markers=" in src and "vision_extracted" in src


def test_the_image_count_survives_csf_so_reingest_does_not_zero_the_signal():
    """`documents.n_images` 는 migration 011 의 신호원이다. 컨버터가 세어 놓고도 CSF 로 안
    실리면 **재적재가 그 값을 0 으로 덮는다** — 신호가 조용히 죽는다. 2026-08-10 라이브에서
    11 → 0 으로 떨어지는 것을 실제로 봤다."""
    from nexus.a2a.server import _csf_to_markdown_file
    from nexus.ingest.sources.base import ConvertedDoc
    from nexus.ingest.sources.notion_importer import build_csf

    conv = ConvertedDoc(page_id="p3", markdown="본문",
                        frontmatter={"title": "정책", "image_count": 11}, image_count=11)
    csf = build_csf(conv, "p3")
    assert csf["image_count"] == 11
    assert "image_count: 11" in _csf_to_markdown_file(csf)


def test_a_document_without_images_writes_no_image_count():
    from nexus.a2a.server import _csf_to_markdown_file
    from nexus.ingest.sources.base import ConvertedDoc
    from nexus.ingest.sources.notion_importer import build_csf

    csf = build_csf(ConvertedDoc(page_id="p4", markdown="본문", frontmatter={"title": "메모"}), "p4")
    assert "image_count" not in _csf_to_markdown_file(csf)
