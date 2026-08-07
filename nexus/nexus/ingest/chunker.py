"""doc_type별 Hierarchical Chunking.

Markdown 문서를 H1/H2 기반으로 섹션 분할 후,
토큰 수에 따라 chunk를 생성한다.
코드 블록과 테이블은 쪼개지 않고 통째로 유지한다.
"""

from __future__ import annotations

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


def _split_oversize(para: str, target_tokens: int, language: str) -> list[str]:
    """`target_tokens` 를 넘는 **단일 문단**을 쪼갠다 — 새 상수를 만들지 않는다.

    상한은 이미 설정에 있는 `target_tokens` 다. 결함은 문턱이 없어서가 아니라 이 경로가 문턱을
    **건너뛰었기** 때문이다.

    세 가지를 순서대로 한다.

    1. **마크다운 표면 헤더와 구분행을 조각마다 되붙인다.** 표를 그냥 자르면 두 번째 조각부터
       열의 뜻이 사라진다. 실제로 터진 것이 정책 표였다.
    2. 줄 단위로 모은다 — 줄 중간을 자르면 표 행이나 코드 문장이 깨진다.
    3. **한 줄이 그 자체로 target 을 넘으면 문자로 자른다.** 단어를 깨는 것이 맞다 — 안 자르면
       상한이 상한이 아니고, 넘치는 청크는 벡터 다리에서 통째로 안 보인다. 잘린 것이 안 보이는
       것보다 낫다.
    """
    lines = para.split("\n")

    header: list[str] = []
    if (len(lines) >= 2 and lines[0].lstrip().startswith("|")
            and set(lines[1].strip()) <= set("|-: ")):
        header, lines = lines[:2], lines[2:]

    def _hard_cut(line: str) -> list[str]:
        """줄 하나가 그 자체로 target 을 넘을 때. 단어를 깨더라도 자른다."""
        t = _estimate_tokens(line, language)
        if t <= target_tokens or not line:
            return [line]
        pieces = -(-t // target_tokens)                 # 올림
        width = max(1, -(-len(line) // pieces))
        return [line[i:i + width] for i in range(0, len(line), width)]

    # **내보낼 텍스트를 잰다.** 줄별 추정을 더하면 실제와 어긋난다 — `_estimate_tokens` 가 매번
    # 내림하므로 합이 이어붙인 텍스트보다 작게 나오고(3줄에 18 vs 20), 그 차이만큼 상한을 넘긴
    # 조각이 통과한다. 실제로 통과했고 테스트가 잡았다.
    out: list[str] = []
    cur: list[str] = list(header)
    for raw in lines:
        for line in _hard_cut(raw):
            trial = cur + [line]
            if (_estimate_tokens("\n".join(trial), language) > target_tokens
                    and len(cur) > len(header)):
                out.append("\n".join(cur))
                cur = list(header) + [line]
                # 헤더를 되붙였는데도 넘치면 헤더를 버린다 — 장식보다 내용이다.
                if _estimate_tokens("\n".join(cur), language) > target_tokens and header:
                    cur = [line]
            else:
                cur = trial
    if len(cur) > len(header) or (not header and cur):
        out.append("\n".join(cur))
    return out or [para]


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

        # 단일 문단이 target 보다 크면 **쪼갠다.** 예전에는 그대로 통과시켰고, 그것이 청크 길이를
        # 아무것도 안 막는 유일한 경로였다 (KOREAN_SEARCH_QUALITY.md §3.2).
        #
        # 2026-08-07 에 실물에서 터졌다: 빈 줄이 없는 정책 표는 문단 하나로 잡혀 18,751자 청크가
        # 됐고, 임베딩 사이드카가 `413 max_seq_length(8192)` 로 거부해 그 청크는 벡터 다리에서
        # 영구히 사라졌다. 통째로 두면 보존이 아니라 **비가시**다.
        if para_tokens > target_tokens and not current_chunk:
            chunks.extend(_split_oversize(para, target_tokens, language))
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
    target_tokens = (chunking_cfg.get("korean_tokens", 1100) if language == "ko"
                     else chunking_cfg.get("english_tokens", 700))
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
