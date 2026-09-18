"""문서가 **자기에 대해** 말할 수 있는 것만 받는가.

⛔ **왜 필요했나 (실측 2026-09-18).** PR #500 이 `synthetic` 을 정본으로 세우고 검색 결과까지
실어 보내게 했는데, **파일 적재 경로에는 그 라벨을 붙일 방법이 없었다.** `_save_document` 의
INSERT 에 `labels` 컬럼이 아예 없어서 파일로 들어온 문서는 영원히 `{}` 였다. 읽는 쪽만 있고
쓰는 쪽이 없는 표식이었다.

⛔ **그리고 아무 라벨이나 받으면 안 된다.** `external_spec` 은 *"나는 외부 사양 관문으로
들어왔다"* 는 **경로에 대한 주장**이고, 그 문서가 거버넌스 밖(`approved_hash` 없음)이라는
뜻이다. 문서가 자칭하면 파일 한 줄로 그 얼굴을 쓸 수 있고, 읽는 사람에게는 스탬프가 없는
것이 정상으로 보인다. `synthetic` 은 반대다 — 지어낸 문서라는 것은 쓴 사람만 아는 사실이다.
"""

from __future__ import annotations

import pathlib

import pytest

from nexus.labels import (
    EXTERNAL_LABEL,
    SELF_DECLARABLE,
    SYNTHETIC_LABEL,
    declarable,
    merge_sql,
)

_PIPELINE = pathlib.Path(__file__).resolve().parents[1] / "nexus" / "ingest" / "pipeline.py"


# ── 무엇을 받고 무엇을 무는가 ──────────────────────────────────────────────

def test_a_document_may_say_it_is_synthetic():
    assert declarable([SYNTHETIC_LABEL]) == ([SYNTHETIC_LABEL], [])


def test_a_document_may_not_say_where_it_came_from():
    """⛔ 이 검사가 이 단위의 이유다. 자칭을 허용하면 거버넌스 밖 문서인 척할 수 있다."""
    ok, no = declarable([EXTERNAL_LABEL])
    assert ok == [] and no == [EXTERNAL_LABEL]


def test_a_bare_string_is_a_label_too():
    """`labels: synthetic` 은 YAML 에서 리스트가 아니라 문자열이다. 사람이 그렇게 쓴다."""
    assert declarable(SYNTHETIC_LABEL) == ([SYNTHETIC_LABEL], [])


def test_a_mixed_list_keeps_the_good_and_names_the_rest():
    ok, no = declarable([SYNTHETIC_LABEL, EXTERNAL_LABEL, "typoo"])
    assert ok == [SYNTHETIC_LABEL]
    assert no == [EXTERNAL_LABEL, "typoo"], "무엇이 물렸는지 말해야 고칠 수 있다"


def test_no_labels_is_not_an_error():
    assert declarable(None) == ([], [])
    assert declarable([]) == ([], [])


def test_an_unknown_label_is_not_silently_dropped():
    """⛔ 조용히 버리면 오타가 영원히 안 보인다. 세어서 요약에 낸다."""
    _ok, no = declarable(["synthethic"])          # 오타
    assert no == ["synthethic"]


# ── 관문이 실제로 그 자리에 있는가 ─────────────────────────────────────────

def _src() -> str:
    return _PIPELINE.read_text(encoding="utf-8")


def test_the_file_path_actually_writes_the_column():
    """⛔ PR #500 이 놓친 자리. 읽는 쪽만 있고 쓰는 쪽이 없으면 표식은 없는 것이다."""
    src = _src()
    assert "origin_updated_at, labels" in src, "INSERT 에 labels 컬럼이 없다"
    assert "labels = \"\"\" + label_merge" in src, "ON CONFLICT 에 labels 갱신이 없다"


def test_the_pipeline_does_not_keep_its_own_copy_of_the_rule():
    """⚠ 규칙이 두 곳에 있으면 한쪽만 고쳐지고, 어느 쪽이 도는지 아무도 모른다."""
    src = _src()
    assert "merge_sql(" in src, "정본 함수를 안 쓰고 있다"
    assert "array_agg(DISTINCT l)" not in src, "파이프라인이 SQL 사본을 들고 있다"


def test_the_refusal_is_counted_and_is_not_a_failure():
    """문서는 정상 적재됐고 표식만 안 붙었다. `failed` 와 섞으면 읽는 사람이 딴 데를 고친다."""
    from nexus.ingest.pipeline import IngestResult
    from nexus.ingest.runs_store import summarize

    r = IngestResult()
    assert r.refused_labels == 0 and r.failed == 0
    assert "refused_labels" in IngestResult.__dataclass_fields__
    assert "refused_labels" in summarize(r), "적재 기록에도 남아야 한다"


def test_the_allowed_set_is_not_empty_and_excludes_the_path_label():
    assert SYNTHETIC_LABEL in SELF_DECLARABLE
    assert EXTERNAL_LABEL not in SELF_DECLARABLE


# ── DB 가 실제로 그렇게 움직이는가 ─────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_the_merge_keeps_the_path_label_and_drops_the_self_declared_one(db_pool):
    """⭐ **위 소스 검사는 문자열을 볼 뿐이다.** 실제 SQL 이 두 방향으로 도는지는 DB 가 답한다:
    경로가 붙인 것은 살아남고, frontmatter 에서 뺀 것은 사라져야 한다 (못 끄면 표식이 아니다).
    """
    async with db_pool.acquire() as con:
        await con.execute(
            "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, title) "
            "VALUES ('doc_lbl_probe', 'lbl_probe', 'lbl:probe.md', 'h', 'h', 't')")
        await con.execute(
            "UPDATE documents SET labels = $1 WHERE rid = 'doc_lbl_probe'",
            [EXTERNAL_LABEL, SYNTHETIC_LABEL])

        # ⭐ **파이프라인이 쓰는 그 식을 그대로 돌린다.** 여기에 SQL 을 베껴 쓰면 본체가
        # 바뀌어도 이 검사는 자기 사본을 통과시킨다 — 그러면 아무것도 안 지킨 것이다.
        # 재적재가 `synthetic` 을 선언하지 않은 경우($2 = 빈 목록).
        await con.execute(
            "UPDATE documents SET labels = " + merge_sql(1, "$2::text[]")
            + " WHERE rid = 'doc_lbl_probe'",
            sorted(SELF_DECLARABLE), [],
        )
        got = await con.fetchval("SELECT labels FROM documents WHERE rid = 'doc_lbl_probe'")

    assert list(got) == [EXTERNAL_LABEL], (
        "경로가 붙인 표식은 남고, 자칭 표식은 선언을 빼면 사라져야 한다")
