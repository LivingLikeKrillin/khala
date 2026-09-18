"""`labels:` 한 줄만 고친 파일을 변경 감지가 보는가.

⛔ **왜 필요했나 (실측 2026-09-18).** `content_hash` 는 스펙 ⑥ 대로 frontmatter 를 뺀 본문만
센다. 그래서 라벨만 고친 파일은 "안 바뀜" 으로 건너뛰고 **표식이 옛 값으로 남는다.** 합성
코퍼스 안내 문서에 `labels: [synthetic]` 을 붙였는데 재적재가 조용히 무시했고, `--force` 를
아는 사람만 붙일 수 있었다. 라벨은 frontmatter 에만 사는 값이라 이 구멍이 라벨 기능 전체를
「아는 사람만 되는 것」으로 만든다.

⚠ **반대쪽 위험이 더 조용하다.** 비교가 조금이라도 비대칭이면 그 파일은 **매 주기마다**
바뀐 것으로 잡혀 영원히 재색인된다. 주기 재적재를 켜 둔 배포에서는 아무도 모르는 채로
돌기만 한다. 그래서 멱등을 같이 검사한다.
"""

from __future__ import annotations

import pytest

from nexus.ingest.collector import collect_files
from nexus.labels import EXTERNAL_LABEL, SYNTHETIC_LABEL

_TENANT = "lbl_change_probe"

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def wired(db_pool):
    """수집기가 쓰는 **전역 풀**을 시험 DB 로 물린다.

    ⛔ **이것이 없으면 이 파일의 모든 검사가 거짓으로 통과한다.** 수집기의 조회는
    `except Exception: pass` 로 감싸여 있고(DB 미연결 시 전부 수집), 전역 풀이 안 물려
    있으면 조회가 조용히 실패해 **모든 파일이 「바뀜」으로 나온다.** 그러면 "바뀐 것을
    본다" 는 검사들은 통과하고, 실제로 아무것도 안 본 것이다. 처음 돌렸을 때 실제로
    그렇게 나왔다 — 「안 바뀜」쪽 넷이 먼저 깨져서 알았다.
    """
    from nexus import db

    before = db._pool
    db._pool = db_pool
    try:
        yield db_pool
    finally:
        db._pool = before


def _write(d, name: str, labels: str | None, body: str = "본문이다.\n") -> None:
    fm = f"---\nlabels: {labels}\n---\n\n" if labels is not None else ""
    (d / name).write_text(f"{fm}# 제목\n\n{body}", encoding="utf-8")


async def _seed(con, uri: str, content_hash: str, labels: list[str]) -> None:
    await con.execute(
        "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, title, labels) "
        "VALUES ($1, $2, $3, 'h', $4, 't', $5) "
        "ON CONFLICT (rid) DO UPDATE SET content_hash = EXCLUDED.content_hash, "
        "labels = EXCLUDED.labels",
        f"doc_{abs(hash(uri))}", _TENANT, uri, content_hash, labels,
    )


async def _hash_of(tmp_path) -> str:
    """이 본문의 `content_hash` — 수집기가 계산하는 그 값."""
    got = await collect_files(str(tmp_path), "**/*.md", force=True, tenant=_TENANT)
    return got.files[0].content_hash


async def test_a_label_only_edit_is_seen_as_a_change(tmp_path, wired):
    """⛔ 이 검사가 이 단위의 이유다."""
    _write(tmp_path, "a.md", "[synthetic]")
    h = await _hash_of(tmp_path)
    async with wired.acquire() as con:
        await _seed(con, f"{_TENANT}:a.md", h, [])          # 저장된 라벨은 비어 있다

    got = await collect_files(str(tmp_path), "**/*.md", tenant=_TENANT)
    assert got.changed == 1, "라벨을 붙였는데 안 바뀐 것으로 봤다"


async def test_the_same_labels_are_not_a_change(tmp_path, wired):
    """⚠ 비대칭이면 이 파일이 **매 주기마다** 재색인된다. 주기 잡에서는 아무도 모른다."""
    _write(tmp_path, "a.md", "[synthetic]")
    h = await _hash_of(tmp_path)
    async with wired.acquire() as con:
        await _seed(con, f"{_TENANT}:a.md", h, [SYNTHETIC_LABEL])

    got = await collect_files(str(tmp_path), "**/*.md", tenant=_TENANT)
    assert got.changed == 0 and got.unchanged == 1


async def test_removing_a_label_is_also_a_change(tmp_path, wired):
    """못 끄면 표식이 아니다 — 붙이는 쪽만 보면 반쪽이다."""
    _write(tmp_path, "a.md", None)
    h = await _hash_of(tmp_path)
    async with wired.acquire() as con:
        await _seed(con, f"{_TENANT}:a.md", h, [SYNTHETIC_LABEL])

    got = await collect_files(str(tmp_path), "**/*.md", tenant=_TENANT)
    assert got.changed == 1


async def test_a_label_the_path_set_does_not_cause_churn(tmp_path, wired):
    """⛔ **가장 조용한 실패 모드.** 문서는 `external_spec` 을 선언할 수 없는데, 그것을
    "선언 안 했다" 로 읽고 매번 재색인하면 게이트웨이로 들어온 문서 전부가 영원히 돈다."""
    _write(tmp_path, "a.md", None)
    h = await _hash_of(tmp_path)
    async with wired.acquire() as con:
        await _seed(con, f"{_TENANT}:a.md", h, [EXTERNAL_LABEL])

    got = await collect_files(str(tmp_path), "**/*.md", tenant=_TENANT)
    assert got.changed == 0, "경로가 붙인 표식을 문서 탓으로 읽고 있다"


async def test_other_frontmatter_still_does_not_trigger_a_reingest(tmp_path, wired):
    """⚠ frontmatter 전체를 해시에 넣은 것이 아니다. 스펙 ⑥ 은 그대로다 — 아무 메타데이터나
    고쳤다고 전량 재색인이 돌면 그 규칙을 지운 것이다."""
    _write(tmp_path, "a.md", None)
    h = await _hash_of(tmp_path)
    async with wired.acquire() as con:
        await _seed(con, f"{_TENANT}:a.md", h, [])

    (tmp_path / "a.md").write_text(
        "---\ntitle: 제목을 바꿨다\nowner: 누군가\n---\n\n# 제목\n\n본문이다.\n",
        encoding="utf-8")
    got = await collect_files(str(tmp_path), "**/*.md", tenant=_TENANT)
    assert got.changed == 0, "라벨이 아닌 frontmatter 까지 변경으로 읽고 있다"


async def test_a_label_a_document_cannot_declare_is_not_a_change(tmp_path, wired):
    """문서가 `external_spec` 을 자칭해도 저장되지 않는다(#505). 그것을 변경으로 읽으면
    그 파일은 저장되지 않는 값을 쫓아 영원히 재색인된다."""
    _write(tmp_path, "a.md", "[external_spec]")
    h = await _hash_of(tmp_path)
    async with wired.acquire() as con:
        await _seed(con, f"{_TENANT}:a.md", h, [])

    got = await collect_files(str(tmp_path), "**/*.md", tenant=_TENANT)
    assert got.changed == 0, "자칭할 수 없는 라벨을 쫓아 재색인이 돈다"
