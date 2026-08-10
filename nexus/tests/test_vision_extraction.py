"""그림에서 읽은 텍스트 — 판독기와 경계 (SPEC-nexus-screenshot-text-extraction, ADR-0010).

여기서 재는 것은 추출 **품질**이 아니다. 판독기를 스텁하므로 이 파일이 증명할 수 있는 것은
"판독기가 돌려준 것과 chunk 사이에서 아무것도 더해지거나 빠지지 않는다" 뿐이고, **무발명은
증명하지 못한다** — 그건 SPEC §7.1 의 사람이 읽는 8장 표본이 실제 전송 경로에 대고 하는 일이다.
테스트 이름이 그 이상을 암시하면 못 주는 보증을 주는 것처럼 읽힌다.

여기서 재는 것은 **경계**다:

    툴 정의가 요청에 없는가 · 이미지가 한 장인가 · 마커가 양방향으로 제거되는가 ·
    한 chunk 가 두 종류를 담지 않는가 · 같은 바이트가 body 를 바꾸지 않는가
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.ingest import vision  # noqa: E402
from nexus.ingest.chunker import chunk_document  # noqa: E402


class _Reader:
    """판독기 대역. 나가는 요청을 그대로 붙잡아 둔다 — 통제는 요청의 **모양**이기 때문이다."""

    model = "test-vision"

    def __init__(self, reply="포인트 표\n\n| 아바타 | 해금 |\n|---|---|\n| A | 1200 |"):
        self.reply, self.calls = reply, []

    async def vision_extract(self, system, image_b64, media_type, max_tokens):
        self.calls.append({"system": system, "image_b64": image_b64,
                           "media_type": media_type, "max_tokens": max_tokens})
        return self.reply


PNG = b"\x89PNG\r\n\x1a\n" + b"fake bytes"


# ── 판독기가 구조적으로 묶여 있는가 ───────────────────────────────────────────

def test_the_request_carries_no_tool_definitions():
    """이것이 이 경로의 통제다. 초안은 `--allowed-tools Read` 를 열었고, 그 통제는 시험조차
    불가능했다 — 겨냥한 공격 자체가 Read 호출이라 "Read 외 호출 없음" 은 통과한 채 유출이
    성공한다. 부를 tool 이 없으면 tool 호출도 없다."""
    r = _Reader()
    asyncio.run(vision.read_image(PNG, "image/png", r))
    (call,) = r.calls
    assert "tools" not in call
    assert not any(k in call for k in ("allowed_tools", "tool_choice"))


def test_the_request_carries_exactly_one_image_and_no_path():
    """추출은 quarantine 게이트 **앞**에서 돈다. 판독기가 경로를 받으면 그 순서가 위험해진다."""
    r = _Reader()
    asyncio.run(vision.read_image(PNG, "image/png", r))
    (call,) = r.calls
    assert call["image_b64"] and isinstance(call["image_b64"], str)
    blob = repr(call)
    for leak in ("/", "\\", "http", "file:"):
        assert leak not in call["system"], f"시스템 프롬프트에 {leak} 가 있다"
    assert "b64" in blob or call["image_b64"]


def test_output_is_capped_and_the_truncation_is_recorded():
    """조용히 짧아지지 않는다 — 잘렸다는 사실이 남아야 읽는 사람이 안다."""
    r = _Reader("가" * (vision.MAX_EXTRACTED_CHARS + 500))
    e = asyncio.run(vision.read_image(PNG, "image/png", r))
    assert len(e.text) == vision.MAX_EXTRACTED_CHARS and e.truncated is True


def test_a_reader_failure_degrades_and_is_recorded_not_raised():
    """한 장의 실패가 문서 전체를 막으면 안 된다. 그리고 실패는 **기록**돼야 한다 — 안 그러면
    실패한 적재와 나중의 성공 적재가 서로 다른 body 를 만들어 content_hash 가 왕복한다."""
    class _Boom:
        model = "x"
        async def vision_extract(self, *a, **k):
            raise RuntimeError("provider down")

    e = asyncio.run(vision.read_image(PNG, "image/png", _Boom()))
    assert e.ok is False and "provider down" in e.error and e.text == ""


# ── 경계 마커 — 양방향 ────────────────────────────────────────────────────────

def test_markers_are_stripped_from_extracted_text():
    """추출 텍스트에 종료 마커가 있으면 블록이 일찍 닫히고 나머지 출력이 **authored** chunk 가
    된다 — 기계 텍스트를 위로 세탁하는 경계 주입이다."""
    r = _Reader(f"앞{vision.VISION_END}뒤")
    e = asyncio.run(vision.read_image(PNG, "image/png", r))
    assert vision.VISION_END not in e.text and "앞" in e.text and "뒤" in e.text


def test_markers_are_stripped_from_authored_text_too():
    """반대 방향의 같은 사고: 저자 문서에 시작 마커가 있으면 컨버터가 열지도 않은 블록이 열려
    저자의 산문이 machine_read 로 찍힌다."""
    authored = f"사람이 쓴 문단 {vision.VISION_BEGIN} 이어지는 문단"
    assert vision.VISION_BEGIN not in vision.strip_markers(authored)


def test_the_block_carries_no_timestamp():
    """블록은 content_hash 가 계산되는 body 안에 들어간다. 마커에 시각을 넣으면 추출할 때마다
    해시가 바뀌고, 그림을 이고 있는 문서가 매 적재마다 수정된 것처럼 보인다 — ADR-0010 §5 가
    막으려던 churn 을 그것을 기록하려던 필드가 만든다."""
    e = vision.Extraction("표 내용", "m/abc12345", "s" * 64)
    block = vision.build_block(e)
    assert "at=" not in block and "20" not in block.split("extractor=")[1].split("}")[0]


def test_the_same_bytes_produce_the_same_block():
    e1 = vision.Extraction("같은 텍스트", "m/abc12345", "s" * 64)
    e2 = vision.Extraction("같은 텍스트", "m/abc12345", "s" * 64)
    assert vision.build_block(e1) == vision.build_block(e2)


# ── 추출기 신원 ───────────────────────────────────────────────────────────────

def test_the_identity_moves_with_the_prompt(monkeypatch):
    """ADR-0010 §5 가 추출기 교체를 마이그레이션이라 부르는데, 마이그레이션은 무엇을 무효화할지
    셀 수 있어야 성립한다."""
    before = vision.extractor_identity()
    monkeypatch.setattr(vision, "SYSTEM", vision.SYSTEM + " 추가 지시")
    assert vision.extractor_identity() != before


def test_bumping_the_answer_model_does_not_move_the_extractor_identity(monkeypatch):
    """**행동으로 단언한다.** 앞선 판은 소스에서 문자열을 grep 했는데, 그러면 안 된다고 설명하는
    주석에 걸린다 — 표현이 아니라 행동을 재야 한다.

    공유 상수였다면 답변 모델의 EOL 교체가 추출기 신원을 조용히 바꾸고, 저장된 추출을 전부
    무효화하며, 무관한 변경의 부작용으로 44장을 다시 읽게 만든다.
    """
    from nexus.providers.llm import LLMService

    monkeypatch.delenv("NEXUS_VISION_MODEL", raising=False)
    before = vision.extractor_identity()
    monkeypatch.setattr(LLMService, "DEFAULT_MODEL", "some-newer-answer-model")
    assert vision.extractor_identity() == before


def test_the_vision_model_is_overridable_on_its_own(monkeypatch):
    """두 수명주기가 별개라는 것의 나머지 반쪽: 비전 모델은 자기 손잡이로 움직인다."""
    before = vision.extractor_identity()
    monkeypatch.setenv("NEXUS_VISION_MODEL", "some-newer-vision-model")
    assert vision.extractor_identity() != before


# ── chunker 경계: 한 chunk 는 한 종류만 ───────────────────────────────────────

def _doc_with_vision():
    e = vision.Extraction("| 아바타 | 해금 |\n|---|---|\n| A | 1200 |", "m/abc12345", "s" * 64)
    return (
        "# 정책\n\n"
        "아바타 해금 기준은 아래 표와 같다.\n\n"
        + vision.build_block(e) + "\n\n"
        "문의는 담당자에게.\n"
    )


def test_no_chunk_carries_both_kinds():
    """ADR-0010 §3 의 규칙이고, 초안의 인라인 배치가 조용히 깨뜨렸을 바로 그 불변식이다.
    혼합 chunk 는 정직한 값을 가질 수 없다."""
    chunks = chunk_document(_doc_with_vision(), language="ko")
    assert len(chunks) >= 2
    for c in chunks:
        has_vision = "(그림에서 읽은 내용)" in c.chunk_text
        assert (c.provenance_tier == "machine_read") == has_vision, c.chunk_text[:60]


def test_the_authored_text_around_an_image_stays_authored():
    chunks = chunk_document(_doc_with_vision(), language="ko")
    authored = [c for c in chunks if c.provenance_tier == "authored"]
    joined = " ".join(c.chunk_text for c in authored)
    assert "아바타 해금 기준은" in joined and "문의는 담당자에게" in joined
    assert "1200" not in joined, "기계가 읽은 표가 authored chunk 에 섞였다"


def test_a_document_with_no_images_is_entirely_authored():
    chunks = chunk_document("# 제목\n\n본문입니다.\n", language="ko")
    assert chunks and all(c.provenance_tier == "authored" for c in chunks)


def test_an_unbalanced_marker_does_not_tier_authored_prose_as_machine_read():
    """잘린 문서나 손으로 편집된 body 로 저자 산문이 기계 텍스트로 찍히면 안 된다."""
    doc = f"# 제목\n\n사람이 쓴 문단\n{vision.VISION_BEGIN}\n짝 없는 꼬리\n"
    chunks = chunk_document(doc, language="ko")
    assert chunks and all(c.provenance_tier == "authored" for c in chunks)


def test_a_large_vision_block_splits_into_machine_read_chunks_only():
    """큰 블록이 여러 chunk 로 갈려도 authored 이웃과 합쳐지지 않는다."""
    big = vision.Extraction("문장. " * 4000, "m/abc12345", "s" * 64)
    doc = "# 제목\n\n앞 문단\n\n" + vision.build_block(big) + "\n\n뒤 문단\n"
    chunks = chunk_document(doc, language="ko", config={"chunking": {"korean_tokens": 200}})
    vision_chunks = [c for c in chunks if c.provenance_tier == "machine_read"]
    assert len(vision_chunks) > 1, "큰 블록이 갈리지 않았다"
    for c in vision_chunks:
        assert "앞 문단" not in c.chunk_text and "뒤 문단" not in c.chunk_text
