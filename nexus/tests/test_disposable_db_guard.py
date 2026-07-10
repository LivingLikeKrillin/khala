"""테스트 스위트가 진짜 DB 를 TRUNCATE 하지 못하게 막는 가드.

이 가드가 없을 때 무슨 일이 있었나: `NEXUS_TEST_DB_URL` 을 개발 DB(5432/nexus)로 두고 스위트를
돌렸고, `clean_db` 와 픽스처들의 TRUNCATE 가 개발 코퍼스를 통째로 지웠다. 테스트는 전부 초록이었다.

그래서 규칙을 뒤집는다: **DB 가 스스로 버려도 된다고 선언해야만** 스위트가 붙는다.
선언은 `_disposable_test_db` 테이블의 존재다. 실수로 만들 수 있는 이름이 아니고,
운영/개발 DB 에는 영원히 없다.
"""

from __future__ import annotations

import asyncio
import os

import pytest

DB_URL = os.getenv("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요")


def _swap_dbname(url: str, name: str) -> str:
    head, _, _ = url.rpartition("/")
    return f"{head}/{name}"


def test_the_configured_test_db_declares_itself_disposable():
    from tests.disposable import assert_disposable

    asyncio.run(assert_disposable(DB_URL))          # 예외 없이 통과해야 한다


def test_a_database_without_the_marker_is_refused():
    """마커 없는 DB(여기선 유지보수용 `postgres`)에는 절대 붙지 않는다."""
    from tests.disposable import NotDisposable, assert_disposable

    with pytest.raises(NotDisposable) as e:
        asyncio.run(assert_disposable(_swap_dbname(DB_URL, "postgres")))

    # 거부 메시지는 어떻게 푸는지 알려줘야 한다 — 막기만 하는 가드는 우회당한다
    assert "_disposable_test_db" in str(e.value)
    assert "postgres" in str(e.value)               # 어느 DB 를 거부했는지 이름을 댄다
