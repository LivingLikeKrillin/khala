"""BM25 인덱싱 — mecab-ko → tsvector.

get_search_text()로 생성된 텍스트를 mecab-ko로 형태소 분석하여
PostgreSQL tsvector에 저장한다. chunk_text를 직접 사용하지 않는다.
"""

from __future__ import annotations

import structlog

from khala import db
from khala.utils import get_search_text

logger = structlog.get_logger(__name__)

# mecab-ko 형태소 분석기 (한 번만 초기화)
_mecab = None


def _get_mecab():
    """mecab-ko 인스턴스 획득. 실패 시 None (pg_trgm fallback)."""
    global _mecab
    if _mecab is not None:
        return _mecab
    try:
        import MeCab
        _mecab = MeCab.Tagger()
        return _mecab
    except Exception as e:
        logger.warning("mecab_init_failed", error=str(e))
        return None


# 검색에 유용한 품사 태그 (mecab-ko)
_INCLUDE_POS = {
    "NNG",   # 일반 명사
    "NNP",   # 고유 명사
    "VV",    # 동사 어간
    "VA",    # 형용사 어간
    "SL",    # 외래어/라틴문자
    "SN",    # 숫자
    "XR",    # 어근
}


def tokenize_korean(text: str) -> list[str]:
    """한국어 텍스트 → 검색용 형태소 토큰 리스트.

    mecab-ko로 분석 후 명사/동사어간/외래어/숫자만 추출.
    조사(JK*), 어미(E*), 기호(S* except SL/SN)는 제거.
    """
    mecab = _get_mecab()
    if mecab is None:
        # fallback: 공백 기반 토큰화
        return text.lower().split()

    tokens: list[str] = []
    parsed = mecab.parse(text)
    if not parsed:
        return text.lower().split()

    for line in parsed.strip().split("\n"):
        if line == "EOS" or line == "":
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        surface = parts[0]
        features = parts[1].split(",")
        pos = features[0] if features else ""

        if pos in _INCLUDE_POS:
            tokens.append(surface.lower())

    return tokens


def tokens_to_tsquery(tokens: list[str]) -> str:
    """토큰 리스트 → PostgreSQL tsquery 문자열."""
    if not tokens:
        return ""
    # 각 토큰을 안전하게 감싸고 AND로 연결
    safe = [t.replace("'", "''") for t in tokens if t.strip()]
    if not safe:
        return ""
    return " & ".join(f"'{t}'" for t in safe)


async def index_chunk_bm25(chunk_rid: str, chunk) -> bool:
    """단일 청크의 tsvector를 생성하여 DB에 저장.

    Args:
        chunk_rid: 청크의 rid
        chunk: Chunk 객체 (get_search_text()에 전달)

    Returns:
        성공 여부
    """
    try:
        search_text = get_search_text(chunk)
        tokens = tokenize_korean(search_text)

        if not tokens:
            logger.warning("no_tokens_extracted", chunk_rid=chunk_rid)
            return False

        # PostgreSQL tsvector 직접 생성
        token_str = " ".join(tokens)
        await db.execute(
            """
            UPDATE chunks
            SET tsvector_ko = to_tsvector('simple', $1),
                updated_at = now()
            WHERE rid = $2
            """,
            token_str, chunk_rid,
        )
        return True

    except Exception as e:
        logger.error("bm25_index_failed", chunk_rid=chunk_rid, error=str(e))
        return False


async def index_chunks_bm25(chunk_rids_and_chunks: list[tuple[str, object]]) -> int:
    """복수 청크의 BM25 인덱스 일괄 생성.

    Returns:
        성공한 청크 수
    """
    success = 0
    for rid, chunk in chunk_rids_and_chunks:
        if await index_chunk_bm25(rid, chunk):
            success += 1
    logger.info("bm25_batch_indexed", total=len(chunk_rids_and_chunks), success=success)
    return success
