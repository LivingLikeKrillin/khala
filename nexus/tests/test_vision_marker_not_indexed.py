"""그림 추출 마커는 **본문에 남고 색인에는 안 들어간다** (2026-08-18).

마커는 기계용 손잡이다 — 인용에서 원본 그림으로 되돌아가는 경로가 `chunk_text` 에서 그것을
파싱한다. 그래서 본문에서 지우면 그 기능이 죽는다. 그런데 그 줄이 색인에도 들어가고 있었다:
라이브 정책 코퍼스 309청크 중 41개(13.3%)가 `derived`·`gemini`·`img`·해시를 토큰으로 실었다.

무엇이 망가졌는지는 실측으로 드러났다 — 1홉 근거의 어휘로 질의를 넓히려 했더니 확장어가
`['flash', '내용', 'derived']` 로 뽑혀 실험이 통째로 막혔다.
"""

from __future__ import annotations

from types import SimpleNamespace

from nexus.ingest.vision import marker_line, strip_marker_line
from nexus.utils import get_search_text

_MARKER = "![](){: derived=vision extractor=gemini-3.6-flash/06e83390 img=5fb56e7061f746c6 }"
_BODY = f"{_MARKER}\n> (그림에서 읽은 내용)\n> 로그인 유형별 표"


def _chunk(text=_BODY, section="정책", prefix=None):
    return SimpleNamespace(chunk_text=text, section_path=section, context_prefix=prefix)


def test_the_marker_does_not_reach_the_index():
    out = get_search_text(_chunk())

    for token in ("derived", "gemini", "flash", "img=", "06e83390"):
        assert token not in out, f"색인 텍스트에 {token!r} 가 남았다"


def test_the_human_readable_line_survives():
    """`(그림에서 읽은 내용)` 은 뜻이 있는 문장이다 — 마커와 함께 지우면 안 된다."""
    out = get_search_text(_chunk())

    assert "그림에서 읽은 내용" in out
    assert "로그인 유형별 표" in out


def test_the_body_itself_is_untouched():
    """본문에서 지우면 인용→원본 그림 왕복이 죽는다 (`vision_source` 가 여기서 파싱한다)."""
    chunk = _chunk()
    get_search_text(chunk)

    assert marker_line(chunk.chunk_text) == _MARKER


def test_a_chunk_without_a_marker_is_unchanged():
    """마커 없는 청크의 색인 텍스트는 오늘과 바이트 단위로 같다 — 대다수가 그렇다."""
    plain = _chunk(text="로그인 정책 본문")

    assert get_search_text(plain) == "[정책] 로그인 정책 본문"


def test_the_section_prefix_still_leads():
    assert get_search_text(_chunk()).startswith("[정책] ")


def test_stripping_is_idempotent_and_safe_on_empty():
    assert strip_marker_line(strip_marker_line(_BODY)) == strip_marker_line(_BODY)
    assert strip_marker_line("") == ""
    assert strip_marker_line(None) == ""


# ── 파이썬과 DB 가 같은 텍스트를 만드는가 (실 Postgres) ──────────────────────
#
# `get_search_text()` 와 `search_text` 생성 컬럼은 **같은 정의의 두 구현**이다. 갈라지면 색인은
# 한쪽으로, trigram fallback 은 다른 쪽으로 돌고, 갈라졌다는 사실은 조용하다. 소스 문자열을
# 비교하는 검사로는 못 잡는다 — 같은 입력을 양쪽에 넣어 **결과를 비교**한다.

import os

import pytest

pytestmark_db = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")


@pytestmark_db
async def test_the_database_column_matches_the_python_seam(db_pool):
    from nexus import db as dbmod

    dbmod._pool = db_pool
    body = _BODY
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant='marker_parity'")
        await con.execute("DELETE FROM documents WHERE tenant='marker_parity'")
        await con.execute(
            "INSERT INTO documents (rid,tenant,source_uri,hash,content_hash,title,status) "
            "VALUES ('d_par','marker_parity','u','h','h','t','active')")
        await con.execute(
            "INSERT INTO chunks (rid,tenant,source_uri,doc_rid,chunk_text,section_path,"
            "chunk_index,status,hash) VALUES ('c_par','marker_parity','u','d_par',$1,'정책',0,"
            "'active','h')", body)
        from_db = await con.fetchval("SELECT search_text FROM chunks WHERE rid='c_par'")
        await con.execute("DELETE FROM chunks WHERE tenant='marker_parity'")
        await con.execute("DELETE FROM documents WHERE tenant='marker_parity'")
    dbmod._pool = None

    assert from_db == get_search_text(_chunk(text=body))
