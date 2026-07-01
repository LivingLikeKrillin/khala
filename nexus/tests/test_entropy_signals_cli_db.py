"""DB-backed test for `nexus entropy-signals` — the `v_entropy_signals` 관측 CLI (Task 8).

Measurement is useless if unreadable → a thin CLI reads the migration-001 view and prints
the 4 공존 잔차(coexistence-residue) signals. This test seeds a state that makes three of the
four signals positive, then asserts (a) the view row reflects the seeded state, and (b) the
new `entropy-signals` CLI command is registered and surfaces all four signal lines.

Own SelectorEventLoop + injected asyncpg pool — pytest-asyncio's async fixtures are broken on
this Windows env (see conftest / test_a2a_provenance_db). Uses a real Postgres
(docker-compose.test.yml); skipped without NEXUS_TEST_DB_URL.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

DB_URL = os.getenv("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요 (docker-compose.test.yml)")

_TENANT = "acme"


def _run(coro_fn):
    """Own SelectorEventLoop (asyncpg needs it on Windows). Wire nexus.db to the test pool."""
    from nexus import db

    loop = asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()

    async def _outer():
        import asyncpg
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        db._pool = pool  # all db.execute/fetch_* use this pool
        try:
            async with pool.acquire() as con:
                await con.execute("TRUNCATE documents, chunks, doc_reingest_events CASCADE")
            return await coro_fn()
        finally:
            await pool.close()
            db._pool = None

    try:
        return loop.run_until_complete(_outer())
    finally:
        loop.close()


async def _seed_entropy_state() -> None:
    """Seed a state that makes 3 of the 4 v_entropy_signals positive."""
    from nexus import db

    # 1) supersession: one superseded doc pointing at some rid ⇒ supersessions >= 1
    await db.execute(
        "INSERT INTO documents (rid, tenant, source_uri, hash, title, status, superseded_by) "
        "VALUES ($1, $2, 'seed:old.md', 'h-old', '옛 결제 스펙', 'superseded', $3)",
        "doc_old", _TENANT, "doc_new",
    )
    # the superseding doc itself (active) — unique content_hash so it forms no dup pair
    await db.execute(
        "INSERT INTO documents (rid, tenant, source_uri, hash, title, status, content_hash) "
        "VALUES ($1, $2, 'seed:new.md', 'h-new', '새 결제 스펙', 'active', 'ch-unique')",
        "doc_new", _TENANT,
    )

    # 2) exact-duplicate pair: two ACTIVE docs, SAME non-empty content_hash, distinct rids
    #    (view joins active docs on equal non-empty content_hash, d1.rid < d2.rid) ⇒ exact_dup_pairs >= 1
    for rid in ("doc_dupA", "doc_dupB"):
        await db.execute(
            "INSERT INTO documents (rid, tenant, source_uri, hash, title, status, content_hash) "
            "VALUES ($1, $2, $3, 'h-dup', $4, 'active', 'ch-dup-shared')",
            rid, _TENANT, f"seed:{rid}.md", f"복제 문서 {rid}",
        )

    # 3) reingest overwrite event ⇒ reingest_overwrite_events >= 1
    await db.execute(
        "INSERT INTO doc_reingest_events (rid, tenant, old_content_hash, new_content_hash) "
        "VALUES ($1, $2, 'ch-before', 'ch-after')",
        "doc_new", _TENANT,
    )


def test_view_reflects_seeded_entropy_state():
    """v_entropy_signals exposes exactly 4 keys and reflects the seeded positive signals."""
    from nexus import db

    async def inner():
        await _seed_entropy_state()
        row = await db.fetch_one("SELECT * FROM v_entropy_signals")
        assert row is not None
        signals = dict(row)
        assert set(signals) == {
            "reingest_overwrite_events",
            "exact_dup_pairs",
            "title_stem_collisions",
            "supersessions",
        }
        assert signals["supersessions"] >= 1
        assert signals["exact_dup_pairs"] >= 1
        assert signals["reingest_overwrite_events"] >= 1

    _run(inner)


def test_entropy_signals_command_registered():
    """The `entropy-signals` command is registered on the Typer app."""
    from nexus.cli import app

    names = {c.name for c in app.registered_commands}
    assert "entropy-signals" in names


def test_entropy_signals_cli_prints_four_signals(monkeypatch):
    """Invoking `entropy-signals` prints all four signal lines from the seeded view.

    The command manages its own pool via db.get_pool()/DATABASE_URL, so we point DATABASE_URL
    at the test DB and (on Windows) select the Selector loop policy so asyncpg works under the
    command's asyncio.run().
    """
    from typer.testing import CliRunner

    from nexus.cli import app

    # seed the real DB (the _run harness truncates → seeds → commits → closes its pool)
    _run(_seed_entropy_state)

    monkeypatch.setenv("DATABASE_URL", DB_URL)  # auto-reverted after the test
    prev_policy = asyncio.get_event_loop_policy()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        result = CliRunner().invoke(app, ["entropy-signals"])
    finally:
        asyncio.set_event_loop_policy(prev_policy)

    assert result.exit_code == 0, result.output
    for key in (
        "reingest_overwrite_events",
        "exact_dup_pairs",
        "title_stem_collisions",
        "supersessions",
    ):
        assert key in result.output
