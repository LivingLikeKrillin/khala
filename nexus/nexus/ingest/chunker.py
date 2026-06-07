"""doc_type별 Hierarchical Chunking.

Markdown 문서를 H1/H2 기반으로 섹션 분할 후,
토큰 수에 따라 chunk를 생성한다.
코드 블록과 테이블은 쪼개지 않고 통째로 유지한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ChunkData:
    """청킹 결과."""
    chunk_text: str
    section_path: str  # "H1 > H2"
    chunk_index: int
    token_count: int


def _estimate_tokens(text: str, language: str) -> int:
    """간단한 토큰 수 추정.

    한국어: 공백 기준 단어 수 × 2.3 (한국어 보정 계수)
    영어: 공백 기준 단어 수 × 1.3
    """
    words = text.split()
    if not words:
        return 0
    if language == "ko":
        return int(len(words) * 2.3)
    return int(len(words) * 1.3)


def _split_into_sections(content: str) -> list[tuple[str, str]]:
    """Markdown을 H1/H2 기반 섹션으로 분할.

    Returns:
        list of (section_path, section_text)
    """
    lines = content.split("\n")
    sections: list[tuple[str, str]] = []
    current_h1 = ""
    current_h2 = ""
    current_lines: list[str] = []

    def flush() -> None:
        if current_lines:
            path = current_h1
            if current_h2:
                path = f"{current_h1} > {current_h2}" if current_h1 else current_h2
            text = "\n".join(current_lines).strip()
            if text:
                sections.append((path or "root", text))

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            flush()
            current_h1 = stripped[2:].strip()
            current_h2 = ""
            current_lines = [line]
        elif stripped.startswith("## "):
            flush()
            current_h2 = stripped[3:].strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    flush()

    # 섹션이 없으면 전체를 하나로
    if not sections:
        sections = [("root", content.strip())]

    return sections


def _split_text_with_overlap(
    text: str,
    target_tokens: int,
    overlap_tokens: int,
    language: str,
) -> list[str]:
    """텍스트를 토큰 제한에 맞게 분할. 코드 블록/테이블 보존."""
    # 코드 블록/테이블을 보존하며 문단 단위로 분할
    paragraphs: list[str] = []
    current_block: list[str] = []
    in_code_block = False

    for line in text.split("\n"):
        if line.strip().startswith("```"):
            if in_code_block:
                current_block.append(line)
                paragraphs.append("\n".join(current_block))
                current_block = []
                in_code_block = False
            else:
                if current_block:
                    paragraphs.append("\n".join(current_block))
                    current_block = []
                current_block.append(line)
                in_code_block = True
        elif in_code_block:
            current_block.append(line)
        elif line.strip() == "":
            if current_block:
                paragraphs.append("\n".join(current_block))
                current_block = []
        else:
            current_block.append(line)

    if current_block:
        paragraphs.append("\n".join(current_block))

    if not paragraphs:
        return []

    # 문단 단위로 청크 병합
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = _estimate_tokens(para, language)

        # 단일 문단이 target보다 크면 그 자체로 청크
        if para_tokens > target_tokens and not current_chunk:
            chunks.append(para)
            continue

        if current_tokens + para_tokens > target_tokens and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            # 오버랩: 마지막 문단들을 다음 청크로 이월
            overlap_paras: list[str] = []
            overlap_count = 0
            for p in reversed(current_chunk):
                p_tokens = _estimate_tokens(p, language)
                if overlap_count + p_tokens > overlap_tokens:
                    break
                overlap_paras.insert(0, p)
                overlap_count += p_tokens
            current_chunk = overlap_paras
            current_tokens = overlap_count

        current_chunk.append(para)
        current_tokens += para_tokens

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


def chunk_document(
    content: str,
    language: str = "ko",
    config: dict | None = None,
) -> list[ChunkData]:
    """문서를 청크로 분할.

    Args:
        content: 문서 본문 (frontmatter 제거 후)
        language: ko | en | mixed
        config: config.yaml의 chunking 설정

    Returns:
        ChunkData 리스트
    """
    if not content.strip():
        return []

    cfg = config or {}
    chunking_cfg = cfg.get("chunking", {})
    target_tokens = chunking_cfg.get("korean_tokens", 1100) if language == "ko" else chunking_cfg.get("english_tokens", 700)
    overlap_ratio = chunking_cfg.get("overlap_ratio", 0.15)
    overlap_tokens = int(target_tokens * overlap_ratio)

    sections = _split_into_sections(content)
    chunks: list[ChunkData] = []
    global_index = 0

    for section_path, section_text in sections:
        section_tokens = _estimate_tokens(section_text, language)

        if section_tokens <= target_tokens:
            chunks.append(ChunkData(
                chunk_text=section_text,
                section_path=section_path,
                chunk_index=global_index,
                token_count=section_tokens,
            ))
            global_index += 1
        else:
            sub_chunks = _split_text_with_overlap(section_text, target_tokens, overlap_tokens, language)
            for sub in sub_chunks:
                chunks.append(ChunkData(
                    chunk_text=sub,
                    section_path=section_path,
                    chunk_index=global_index,
                    token_count=_estimate_tokens(sub, language),
                ))
                global_index += 1

    logger.info("document_chunked", chunks=len(chunks))
    return chunks
