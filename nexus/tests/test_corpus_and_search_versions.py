"""이 답이 **어떤 코퍼스**에서, **어떤 검색 설정**으로 나왔는가 — `corpus_version` · `search_fingerprint`.

⛔ **왜 생겼나 (2026-09-27, 설명 레이어 자문).** 같은 질문의 답이 어제와 다르면 까닭이 다섯 갈래다 —
프롬프트 · 코퍼스 내용 · 검색 스택 · 모델 · 표본. 프롬프트는 `prompt_version` 이 가른다. 나머지 중
khala 가 아는 둘이 응답에 없었다:

- **코퍼스 버전**: 재적재가 한 시간마다 돌아 원본이 바뀌면 코퍼스가 바뀐다. 경계 시각은 `ingest_runs`
  에 있지만 답 하나를 받은 쪽은 그 답이 경계의 어느 쪽인지 모른다
- **검색 스택 핑거프린트**: 이미 있었다(`evidence_fingerprint`) — 그런데 **충분성 판정자가 켜진 행에만**
  기록돼서, 판정자가 꺼진 배포에서 최근 12일 609행이 전부 비어 있었다

계약(편지 14, 소유자 승인 2026-09-30):
- `corpus_version` = 이번 답이 뒤진 테넌트들의 **읽을 수 있는**(정책 필터 넷) 문서의 `(tenant, rid,
  content_hash)` 를 정렬해 해시. 재적재돼도 내용이 같으면 같은 값. ⚠ 조각내기 · 임베딩 · 검색 설정의
  변화는 못 본다 — 그건 검색 스택 핑거프린트의 몫이다
- `search_fingerprint` = 임베딩 컬럼 · 모델 · 토크나이저 + **`search` 설정 절 전체**. 절 전체인 이유:
  목록을 사람이 적으면 `prompt_version` 이 겪은 것처럼 낡는다. 설정으로 켜는 보강(정정 확인 · 짝 ·
  참조 필 · 코드 값)도 여기서 보인다
"""

from __future__ import annotations

import os

import pytest

from nexus.search import versions as V


# ── 검색 스택 핑거프린트 ─────────────────────────────────────────────────────────────

_CFG = {"search": {"rrf_k": 60, "pair_expansion": True, "reconcile_pass": False},
        "embedding": {"model": "KURE-v1"}, "staleness": {"ttl_days": {"ADR": 365}}}


def _with(section: str, key: str, value):
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in _CFG.items()}
    cfg.setdefault(section, {})
    cfg[section] = {**cfg[section], key: value}
    return cfg


def test_the_same_stack_gives_the_same_fingerprint():
    assert V.search_fingerprint(_CFG) == V.search_fingerprint(dict(_CFG))
    assert len(V.search_fingerprint(_CFG)) == 12


def test_every_search_setting_moves_it_even_one_nobody_listed():
    """⭐ 목록이 아니라 **절 전체**를 본다 — 내일 생길 설정도 오늘 이미 들어간다."""
    base = V.search_fingerprint(_CFG)
    assert V.search_fingerprint(_with("search", "rrf_k", 61)) != base
    assert V.search_fingerprint(_with("search", "pair_expansion", False)) != base
    assert V.search_fingerprint(_with("search", "a_setting_added_next_month", 1)) != base


def test_the_embedding_generation_moves_it():
    assert V.search_fingerprint(_with("embedding", "model", "nomic-embed-text")) != \
        V.search_fingerprint(_CFG)


def test_settings_outside_search_do_not_move_it():
    """검색에 안 닿는 절까지 넣으면 핑거프린트가 아무 때나 바뀌어 경계가 뜻을 잃는다."""
    assert V.search_fingerprint(_with("staleness", "ttl_days", {"ADR": 30})) == \
        V.search_fingerprint(_CFG)


# ── 코퍼스 버전 ─────────────────────────────────────────────────────────────────

_ROWS = [("picasso", "doc_a", "h1"), ("picasso", "doc_b", "h2"), ("narrator", "doc_c", "h3")]


def test_the_corpus_version_does_not_depend_on_row_order():
    assert V.corpus_version_of(_ROWS) == V.corpus_version_of(list(reversed(_ROWS)))
    assert len(V.corpus_version_of(_ROWS)) == 12


def test_a_changed_body_an_added_doc_or_a_removed_doc_moves_it():
    base = V.corpus_version_of(_ROWS)
    assert V.corpus_version_of([_ROWS[0], ("picasso", "doc_b", "h2-new"), _ROWS[2]]) != base
    assert V.corpus_version_of(_ROWS + [("picasso", "doc_d", "h4")]) != base
    assert V.corpus_version_of(_ROWS[:2]) != base


def test_the_tenant_is_part_of_the_identity():
    """같은 rid · 같은 해시가 다른 테넌트에 있으면 다른 코퍼스다."""
    assert V.corpus_version_of([("picasso", "doc_a", "h1")]) != \
        V.corpus_version_of([("narrator", "doc_a", "h1")])


# ── 접합부가 찍는다 ────────────────────────────────────────────────────────────

class _R:
    hits: list = []
    graph = None
    fill: list = []


#: 접합부 검사용 — 보강 설정을 **끈** 버전. 켜면 짝 · 참조 보강이 DB 를 치러 간다.
_SEAM_CFG = {"search": {"rrf_k": 61}, "embedding": {"model": "KURE-v1"}}


async def test_the_seam_stamps_the_search_fingerprint():
    """답변 경로 넷이 전부 지나는 자리에서 찍는다 — `prompt_version` 과 같은 자리, 같은 이유다."""
    from nexus.search import reconcile

    packet = await reconcile.packet_for_answer(
        _R(), "default", "INTERNAL", config=_SEAM_CFG, search=None, question=None, pool=None)
    assert packet.search_fingerprint == V.search_fingerprint(_SEAM_CFG)


async def test_without_a_database_the_corpus_version_says_it_does_not_know():
    """DB 없이 만든 근거 묶음(평가 하네스 · 검사)는 코퍼스를 못 센다. 모르는 것을 지어 채우지 않는다."""
    from nexus.search import reconcile

    packet = await reconcile.packet_for_answer(
        _R(), "default", "INTERNAL", config=_SEAM_CFG, search=None, question=None, pool=None)
    assert packet.corpus_version == ""


# ── 코퍼스 버전은 **읽을 수 있는 것만** 센다 (DB) ─────────────────────────────────

pytestmark_db = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_T1, _T2, _OTHER = "corpus_version_t1", "corpus_version_t2", "corpus_version_other"


async def _seed(pool):
    async with pool.acquire() as con:
        for t in (_T1, _T2, _OTHER):
            await con.execute("DELETE FROM documents WHERE tenant=$1", t)

        async def doc(tenant, name, content_hash, classification="INTERNAL",
                      status="active", quarantined=False):
            await con.execute(
                "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, title, "
                "doc_type, classification, status, is_quarantined) "
                "VALUES ($1,$2,$3,'h',$4,$5,'policy',$6,$7,$8)",
                f"doc_{tenant}_{name}", tenant, f"{tenant}:{name}", content_hash, name,
                classification, status, quarantined)

        await doc(_T1, "a", "h-a")
        await doc(_T1, "b", "h-b")
        await doc(_T2, "c", "h-c")
        await doc(_T1, "hidden", "h-hidden", status="soft_deleted")      # 숨김 문서
        await doc(_T1, "quarantined", "h-q", quarantined=True)          # 격리
        await doc(_T1, "restricted", "h-r", classification="RESTRICTED")  # 등급 밖
        await doc(_OTHER, "x", "h-x")                                    # 범위 밖 테넌트


async def _cleanup(pool):
    async with pool.acquire() as con:
        for t in (_T1, _T2, _OTHER):
            await con.execute("DELETE FROM documents WHERE tenant=$1", t)


@pytestmark_db
async def test_it_counts_only_what_this_caller_could_read(db_pool):
    """⛔ `nexus/CLAUDE.md`: **모든 SELECT 에 정책 필터를 건다. 예외 없음.** 숨긴 · 격리된 · 등급
    밖 · 범위 밖 문서는 이 답의 코퍼스가 아니다 — 세면 답이 못 본 변화로 버전이 바뀐다."""
    await _seed(db_pool)
    try:
        got = await V.corpus_version([_T1, _T2], "INTERNAL", db_pool)
        expected = V.corpus_version_of([(_T1, f"doc_{_T1}_a", "h-a"), (_T1, f"doc_{_T1}_b", "h-b"),
                                        (_T2, f"doc_{_T2}_c", "h-c")])
        assert got == expected
    finally:
        await _cleanup(db_pool)


@pytestmark_db
async def test_a_changed_document_moves_it_and_an_unreadable_one_does_not(db_pool):
    await _seed(db_pool)
    try:
        before = await V.corpus_version([_T1, _T2], "INTERNAL", db_pool)
        async with db_pool.acquire() as con:
            await con.execute("UPDATE documents SET content_hash='h-r2' WHERE rid=$1",
                              f"doc_{_T1}_restricted")
            await con.execute("UPDATE documents SET content_hash='h-x2' WHERE rid=$1", f"doc_{_OTHER}_x")
        assert await V.corpus_version([_T1, _T2], "INTERNAL", db_pool) == before, \
            "읽을 수 없는 문서의 변화로 판이 바뀌었다"
        async with db_pool.acquire() as con:
            await con.execute("UPDATE documents SET content_hash='h-a2' WHERE rid=$1", f"doc_{_T1}_a")
        assert await V.corpus_version([_T1, _T2], "INTERNAL", db_pool) != before
    finally:
        await _cleanup(db_pool)


@pytestmark_db
async def test_the_seam_stamps_the_corpus_version_when_it_has_a_database(db_pool):
    from nexus.search import reconcile

    await _seed(db_pool)
    try:
        packet = await reconcile.packet_for_answer(
            _R(), [_T1, _T2], "INTERNAL", config=_SEAM_CFG, search=None, question=None, pool=db_pool)
        assert packet.corpus_version == await V.corpus_version([_T1, _T2], "INTERNAL", db_pool)
        assert packet.corpus_version != ""
    finally:
        await _cleanup(db_pool)
