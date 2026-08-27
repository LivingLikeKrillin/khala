"""BM25 인덱싱 — mecab-ko → tsvector.

get_search_text()로 생성된 텍스트를 mecab-ko로 형태소 분석하여
PostgreSQL tsvector에 저장한다. chunk_text를 직접 사용하지 않는다.
"""

from __future__ import annotations

import re
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

    for line in parsed.strip().split(chr(10)):
        if line == "EOS" or line == "":
            continue
        parts = line.split(chr(9))
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


#: 낱말 경계. 한글·라틴·숫자가 이어진 덩어리 하나를 한 낱말로 본다.
_WORD_RE = re.compile(r"[0-9A-Za-z가-힣]+")


def tokenize_with_surface(text: str, protect: set[str] | None = None) -> list[str]:
    """형태소 토큰 + **부서진 낱말의 표면형**.

    **왜 필요한가** (2026-08-26 진단). mecab 이 못 읽는 것이 아니라, 읽은 조각 중 일부를 우리
    품사 필터가 버리거나(디제잉 = 디+`제`(XSN)+잉 · 클러버 = `클`(VA+ETM)+러버) 복합어를
    합치지 않는다(파티룸 = 파티+룸). 도메인 어휘 15개 중 **8개가 원형을 잃었고**, 그중 하나가
    이 서비스를 가장 잘 식별하는 `디제잉` 이었다 — 색인에는 한 글자 `디` 로 남았다.

    그래서 형태소는 **그대로 두고**, 낱말의 표면형이 그 낱말의 토큰들 안에 없을 때만 같이 넣는다.

    · **제자리에 넣는다.** 뒤에 몰아 붙이면 `ts_rank_cd` 가 보는 근접성이 달라진다.
    · **이미 있으면 안 넣는다.** 위치가 중복되면 점수가 조용히 바뀐다.
    · 한 글자는 안 넣는다 — 정보가 없고 흔하다.

    `protect` 를 주면 **그 목록에 있는 낱말에만** 표면형을 넣는다. 두 실험군이 이 함수 하나를
    공유해야 처치가 분리된다 — 낱말 단위로 따로 분석하면 문맥이 달라져 **주입 말고 다른 것도**
    바뀌고(mecab 은 이웃에 따라 다르게 자른다), 그러면 무엇을 잰 것인지 알 수 없다.
    """
    mecab = _get_mecab()
    if mecab is None:
        return text.lower().split()
    parsed = mecab.parse(text)
    if not parsed:
        return text.lower().split()

    # (표면, 품사) 스트림. 낱말 경계에 맞춰 소비한다.
    stream: list[tuple[str, str]] = []
    for line in parsed.strip().split(chr(10)):
        if line in ("EOS", ""):
            continue
        parts = line.split(chr(9))
        if len(parts) < 2:
            continue
        feats = parts[1].split(",")
        stream.append((parts[0], feats[0] if feats else ""))

    # **표면을 원문 위치로 되짚어 낱말에 배정한다.** 앞판은 스트림을 앞에서부터 먹으며
    # `word.startswith(...)` 로 맞췄는데, 낱말 사이의 기호(`[`, `*`, `:`)도 스트림에 있어서
    # 정렬이 어긋났고 **그 낱말의 형태소를 통째로 버렸다** — `[파티룸] 디제잉 정책` 이
    # `['파티룸','디제잉']` 이 됐다(형태소 5개 소실). 위치로 배정하면 기호가 몇 개든 상관없다.
    words = [(m.group(0), m.start(), m.end()) for m in _WORD_RE.finditer(text)]
    buckets: list[list[str]] = [[] for _ in words]
    cursor = 0
    wi = 0
    for surface, pos_tag in stream:
        at = text.find(surface, cursor)
        if at < 0:
            continue
        cursor = at + len(surface)
        while wi < len(words) and words[wi][2] <= at:
            wi += 1
        if wi < len(words) and words[wi][1] <= at < words[wi][2] and pos_tag in _INCLUDE_POS:
            buckets[wi].append(surface.lower())

    out: list[str] = []
    for (word, _s, _e), kept in zip(words, buckets):
        out.extend(kept)
        low = word.lower()
        if len(low) >= 2 and low not in kept and (protect is None or low in protect):
            out.append(low)
    return out


#: 이름을 이루는 품사. 조사(J*)·어미(E*)는 여기 없다 — 그것들이 떨어지는 것은 형태소 분석이
#: **옳게** 동작한 것이고, 그런 낱말은 보호 대상이 아니다.
_NAME_POS = {"NNG", "NNP", "SL", "SN", "XSN"}


def compound_names(text: str) -> list[str]:
    """이 텍스트가 **이름으로 쓰는데 색인에서는 쪼개지는** 낱말들.

    보호 목록을 손으로 적지 않기 위한 도구다 — 손으로 미러링하는 목록은 이 리포에서 전부
    부패원이었다.

    **판정**: 낱말이 형태소 2개 이상으로 갈리는데 그 조각이 **전부 이름 품사**이고, 낱말 자체는
    토큰에 없을 때. 그러면 그것은 조직이 한 덩어리로 부르는 이름인데 색인에는 조각만 남는 것이다.

        파티룸  = 파티(NNG) + 룸(NNG)          → 보호
        디제잉  = 디(NNG) + 제(XSN) + 잉(NNG)   → 보호 (`제` 는 필터가 버린다)
        값은    = 값(NNG) + 은(JX)              → **아니다** — 조사가 떨어진 것은 정상이다
        같은    = 같(VA) + 은(ETM)              → 아니다

    ⚠ 앞선 두 판은 이 구분이 없어 351개·314개짜리 쓰레기 목록을 냈다(Notion 식별자 조각,
    그리고 `값은`·`거부한다` 같은 활용형). 그 목록으로는 "지정 보호" 가 무차별과 구별되지 않아
    측정 자체가 성립하지 않았다.

    ⚠ 이 규칙은 mecab 이 **동사로 오분석**하는 이름은 못 잡는다(클러버 = 클(VA+ETM)+러버,
    레퍼럴 = 레+퍼럴(VA+ETM)). 그건 이 판의 범위 밖이고, 문서에 적어 둔다.
    """
    mecab = _get_mecab()
    if mecab is None:
        return []
    out: list[str] = []
    for word in _WORD_RE.findall(text):
        low = word.lower()
        if len(low) < 2 or not all("가" <= ch <= "힣" for ch in low):
            continue
        parsed = mecab.parse(word)
        if not parsed:
            continue
        # **`tokenize_korean` 을 부르지 않는다.** bm25.py 안에서 그 함수를 부르는 것은
        # `MecabTokenizer` 하나여야 한다는 이음매 불변식이 있고(`test_tokenizer_seam`),
        # 여기 필요한 것은 어차피 태그와 표면뿐이다.
        tags, surfaces = [], []
        for line in parsed.strip().split("\n"):
            if line in ("EOS", ""):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            surfaces.append(parts[0].lower())
            tags.append(parts[1].split(",")[0])
        if len(tags) >= 2 and all(t in _NAME_POS for t in tags) and low not in surfaces:
            out.append(low)
    return out


class ProtectedTermTokenizer:
    """형태소 + **목록에 있는 낱말의 표면형만**.

    무차별 판(`SurfaceFormTokenizer`)은 모든 낱말에 텀을 더해 매치 수를 키웠고, 그 이득을 긴
    문서가 가져가 키워드 다리가 내려갔다(0.879 → 0.818, `tests/eval/tokenizer-surface/`).
    여기서는 **지정된 낱말에만** 붙이므로 그 기제가 성립하지 않는다.

    목록은 호출자가 준다. 이 클래스는 목록을 만들지 않는다 — 어디서 왔는지가 코드가 아니라
    실행 기록에 남아야 한다.
    """

    id = "mecab-ko+protected"

    def __init__(self, terms) -> None:
        self.terms = {t.lower() for t in terms}
        self.policy = (f"mecab-ko POS allow-list {sorted(_INCLUDE_POS)} "
                       f"+ surface form of {len(self.terms)} protected terms")

    def tokenize(self, text: str) -> list[str]:
        return tokenize_with_surface(text, protect=self.terms)


class SurfaceFormTokenizer:
    """형태소 + 부서진 낱말의 표면형. 색인·질의 양쪽이 같은 것을 써야 한다."""

    id = "mecab-ko+surface"

    def __init__(self) -> None:
        self.policy = (f"mecab-ko POS allow-list {sorted(_INCLUDE_POS)} "
                       "+ surface form of words the morphemes do not reproduce")

    def tokenize(self, text: str) -> list[str]:
        return tokenize_with_surface(text)


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
