"""코드 인덱스의 **신원과 구멍**이 사람·에이전트에게 닿는가.

심볼 10,659개·앵커 2,674개가 라이브에 앉아 있는데 `nexus status` 는 코드에 대해 한 마디도
하지 않았다. 문서↔코드 판정("이 문단이 부른 이름이 지금도 있다")이 **어느 커밋 기준인지**,
그 인덱스에 **구멍이 있는지** 를 아무도 볼 수 없다는 뜻이다. 이 리포가 올해만 세 번 데인 모양
그대로다 — 감지기는 있고 전달이 없다.

그리고 세는 칸 하나가 두 사실을 뭉치고 있었다: `unparsed_files` 는 **읽지 못한 파일**과
**선언이 하나도 없는 정상 파일**(`__init__.py` 같은)을 같이 센다. 앞은 인덱스의 구멍이고
(그 파일의 심볼이 통째로 없으니 문서가 그 이름을 부르면 *코드에 없는 이름*으로 읽힌다)
뒤는 그냥 평범한 파일이다. 뭉쳐 두면 경보를 걸 수 없다 — 걸면 영원히 울린다.
"""

from __future__ import annotations

import os
import textwrap

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "code_health"
_REPO = "sample-repo"


def test_a_file_with_no_declarations_is_not_a_hole(tmp_path):
    """대조군 — 선언이 없는 파일은 **정상**이다. 구멍으로 세면 경보가 영원히 울린다."""
    from nexus.index.symbols import scan_repo

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "run.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "pkg" / "real.py").write_text(
        textwrap.dedent("""\
            class Thing:
                pass
        """), encoding="utf-8")

    r = scan_repo(tmp_path)
    assert len(r.symbols) >= 1
    assert r.unreadable_files == 0, "읽기 실패가 없는데 구멍으로 셌다"
    assert r.no_symbol_files == 2, "선언 0 파일은 따로 세어야 한다"


def test_a_file_we_could_not_read_is_a_hole(tmp_path):
    """읽지 못한 파일의 심볼은 통째로 없다 → 문서가 그 이름을 부르면 '없는 이름' 이 된다."""
    from nexus.index.symbols import scan_repo

    (tmp_path / "ok.py").write_text("class A:\n    pass\n", encoding="utf-8")
    (tmp_path / "broken.py").write_bytes(b"\xff\xfe\x00class B:\n")

    r = scan_repo(tmp_path)
    assert r.unreadable_files == 1
    assert r.no_symbol_files == 0


async def test_health_reports_the_commit_the_verdicts_rest_on(db_pool):
    """판정이 **어느 커밋 기준인지** 가 나와야 한다 — 안 나오면 낡음을 볼 방법이 없다."""
    from nexus import db
    from nexus.index import anchor_store
    from nexus.index.symbols import ScanResult, SymbolRow

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM code_symbols WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM code_scans WHERE tenant=$1", _TENANT)
    try:
        result = ScanResult(
            symbols=[SymbolRow(file_path="a.py", symbol_kind="class", symbol_name="A",
                               start_line=1, end_line=2, span_hash="h1")],
            unreadable_files=2, no_symbol_files=7, scanned_files=10,
            imported_names=frozenset(),
        )
        await anchor_store.replace_scan(_TENANT, _REPO, result, "c0ffee1234567890")

        rows = await anchor_store.code_index_health(_TENANT)
        assert len(rows) == 1
        row = rows[0]
        assert row["repo"] == _REPO
        assert row["scan_commit"].startswith("c0ffee")
        assert row["symbol_count"] == 1
        assert row["unreadable_files"] == 2, "구멍이 보고돼야 한다"
        assert row["no_symbol_files"] == 7, "정상 파일 수는 사실로만"
        assert row["scanned_at"] is not None
    finally:
        async with db_pool.acquire() as con:
            await con.execute("DELETE FROM code_symbols WHERE tenant=$1", _TENANT)
            await con.execute("DELETE FROM code_scans WHERE tenant=$1", _TENANT)
        db._pool = None


async def test_health_is_silent_for_a_tenant_that_never_scanned(db_pool):
    """대조군: 코드 인덱스를 안 쓰는 테넌트에는 한 줄도 찍지 않는다."""
    from nexus import db
    from nexus.index import anchor_store

    db._pool = db_pool
    try:
        assert await anchor_store.code_index_health("tenant_that_never_scanned") == []
    finally:
        db._pool = None


def test_nexus_status_names_the_commit_the_code_verdicts_rest_on(monkeypatch):
    """감지기가 아니라 **전달**을 본다 — `cli.py` 의 호출부를 지우면 red 여야 한다."""
    from typer.testing import CliRunner

    from nexus import db
    from nexus.cli import app

    db_url = os.environ["NEXUS_TEST_DB_URL"]
    tenant = "code_health_surface"

    import asyncio
    import sys

    def _run(coro_fn):
        loop = (asyncio.SelectorEventLoop() if sys.platform == "win32"
                else asyncio.new_event_loop())

        async def _outer():
            import asyncpg
            pool = await asyncpg.create_pool(db_url, min_size=1, max_size=2)
            db._pool = pool
            try:
                return await coro_fn()
            finally:
                await pool.close()
                db._pool = None

        try:
            return loop.run_until_complete(_outer())
        finally:
            loop.close()

    async def seed():
        from nexus.index import anchor_store
        from nexus.index.symbols import ScanResult, SymbolRow

        await anchor_store.replace_scan(
            tenant, "surfaced-repo",
            ScanResult(symbols=[SymbolRow(file_path="a.py", symbol_kind="class",
                                          symbol_name="A", start_line=1, end_line=2,
                                          span_hash="h")],
                       unreadable_files=3, no_symbol_files=1, scanned_files=5,
                       imported_names=frozenset()),
            "deadbeef12345678")

    async def purge():
        await db.execute("DELETE FROM code_symbols WHERE tenant=$1", tenant)
        await db.execute("DELETE FROM code_scans WHERE tenant=$1", tenant)

    _run(purge)
    _run(seed)
    monkeypatch.setenv("DATABASE_URL", db_url)
    db._pool = None
    try:
        out = CliRunner().invoke(app, ["status"]).stdout
        assert "코드 인덱스" in out, f"코드 인덱스가 상태에 한 줄도 없다\n{out}"
        assert "deadbeef1234" in out, "판정이 어느 커밋 기준인지 안 찍었다"
        assert "읽지 못한 파일 3건" in out, "인덱스의 구멍이 안 보인다"
    finally:
        db._pool = None
        _run(purge)


# ---------------------------------------------------------------- 스냅샷 가드

def _git(repo, *args):
    import subprocess
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _repo_with_crlf_worktree(tmp_path):
    """LF 로 커밋된 파일이 작업 트리에서는 CRLF — 윈도 체크아웃을 컨테이너에서 보는 상태."""
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "core.autocrlf", "false")
    (repo / "A.java").write_bytes(b"class A {\n  int x;\n}\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    (repo / "A.java").write_bytes(b"class A {\r\n  int x;\r\n}\r\n")
    return repo


def test_a_line_ending_only_difference_is_not_a_dirty_tree(tmp_path):
    """줄바꿈만 다른 트리에서 스캔을 거부하면, **문서화된 명령이 영원히 실패한다.**

    라이브에서 그랬다: 호스트는 `git status` 가 깨끗하다고 하는데 컨테이너는 같은 체크아웃을
    1,421개 수정됨으로 봤다(호스트 autocrlf, 컨테이너는 아님). 내용은 바이트로 같고
    (`git diff --ignore-cr-at-eol` 이 0), 심볼 추출도 span hash 도 **작업 트리 바이트를 읽으므로
    영향이 없다** — 그런데 `docker exec … nexus code scan` 이 항상 거부됐다.
    """
    from nexus.index import snapshot

    repo = _repo_with_crlf_worktree(tmp_path)
    head = snapshot.head_commit(repo)
    state = snapshot.check(repo, head)

    assert state.ok, f"줄바꿈 차이로 거부됐다: {state.explain()}"
    assert state.reason == "eol_only"
    assert any("줄바꿈" in w for w in state.warnings()), "왜 통과했는지 말하지 않는다"


def test_a_real_edit_is_still_refused(tmp_path):
    """대조군 — 진짜 내용 변경은 그대로 거부한다. 가드를 무르게 만들면 안 된다."""
    from nexus.index import snapshot

    repo = _repo_with_crlf_worktree(tmp_path)
    (repo / "A.java").write_bytes(b"class A {\r\n  int y;\r\n}\r\n")
    state = snapshot.check(repo, snapshot.head_commit(repo))

    assert not state.ok and state.reason == "dirty"


def test_an_untracked_file_is_still_dirty(tmp_path):
    """대조군 — `git diff` 는 추적되지 않는 파일을 못 본다. 그것까지 통과시키면 안 된다."""
    from nexus.index import snapshot

    repo = _repo_with_crlf_worktree(tmp_path)
    (repo / "B.java").write_bytes(b"class B {}\n")
    state = snapshot.check(repo, snapshot.head_commit(repo))

    assert not state.ok and state.reason == "dirty"
