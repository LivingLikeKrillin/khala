"""BM25 인덱싱 — mecab-ko → tsvector.

get_search_text()로 생성된 텍스트를 mecab-ko로 형태소 분석하여
PostgreSQL tsvector에 저장한다. chunk_text를 직접 사용하지 않는다.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Protocol

import structlog

from nexus import db
from nexus.utils import get_search_text

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
    """토큰 리스트 → PostgreSQL tsquery 문자열. **OR 로 잇는다** (SPEC-nexus-search-recall §4.1).

    AND 였다. 그러면 질의의 모든 어휘가 한 청크 안에 있어야 한다 — mecab 이 `엔티티` 를
    `엔`+`티티` 로 쪼개므로 `Entity 식별` 이라 적힌 문서는 영영 걸리지 않는다.
    14개 질의 중 11개에서 키워드 다리가 0건을 반환했다(2026-07-10 측정).

    정밀도는 `ts_rank` 가 지킨다. 많은 어휘를, 조밀하게 맞힌 청크가 위로 온다. 그리고 이 다리는
    `search.bm25_top_k`(기본 20) 개만 돌려주므로, OR 은 **매칭을 넓힐 뿐 반환을 넓히지 않는다.**

    따옴표 이스케이프는 남긴다. mecab 은 따옴표를 내놓지 않지만, 토크나이저는 바뀔 수 있다.
    """
    if not tokens:
        return ""
    safe = [t.replace("'", "''") for t in tokens if t.strip()]
    if not safe:
        return ""
    return " | ".join(f"'{t}'" for t in safe)


class Tokenizer(Protocol):
    """색인·질의 양쪽이 쓰는 토크나이저 (SPEC-nexus-korean-retrieval-eval §4.4).

    `policy` 는 **실제로 적용된 필터 정책**을 사람이 읽을 수 있게 적은 문자열이다. 이게 없으면
    한쪽만 품사 필터가 걸린 채로 비교하고서 그 차이를 "분해 차이" 라고 부르게 된다 — 평가셋이
    제거하려던 바로 그 교란이다.
    """

    id: str
    policy: str

    def tokenize(self, text: str) -> list[str]: ...


class MecabTokenizer:
    """프로덕션 기본값. `tokenize_korean` 을 그대로 부른다 — 동작은 한 글자도 안 바뀐다."""

    id = "mecab-ko"

    def __init__(self) -> None:
        self.policy = f"mecab-ko POS allow-list {sorted(_INCLUDE_POS)}"

    def tokenize(self, text: str) -> list[str]:
        return tokenize_korean(text)


_DEFAULT_TOKENIZER = MecabTokenizer()
_active_tokenizer: Tokenizer | None = None


def active_tokenizer() -> Tokenizer:
    """지금 쓸 토크나이저. 주입이 없으면 언제나 mecab 이다."""
    return _active_tokenizer or _DEFAULT_TOKENIZER


@contextmanager
def use_tokenizer(tokenizer: Tokenizer | None):
    """토크나이저를 한 실행 동안 갈아끼운다 — **평가 하니스 전용**.

    색인과 질의가 같은 객체를 쓰도록 한 곳에서만 갈아끼운다. 색인은 mecab 으로, 질의는 nori 로
    돈 실행은 그럴듯한 숫자를 내지만 아무 의미가 없다 (SPEC §4.4).
    """
    global _active_tokenizer
    previous = _active_tokenizer
    _active_tokenizer = tokenizer
    try:
        yield active_tokenizer()
    finally:
        _active_tokenizer = previous


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
        tokens = active_tokenizer().tokenize(search_text)

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
