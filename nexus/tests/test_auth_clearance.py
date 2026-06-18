"""Clearance ordering — single source of truth + parity with the SQL enum."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from nexus.auth import clearance


def test_order_is_public_internal_restricted():
    assert clearance.ORDER == {"PUBLIC": 0, "INTERNAL": 1, "RESTRICTED": 2}
    assert clearance.LEVELS == ("PUBLIC", "INTERNAL", "RESTRICTED")


@pytest.mark.parametrize(
    "raw,expected",
    [("PUBLIC", "PUBLIC"), ("internal", "INTERNAL"), (" Restricted ", "RESTRICTED"),
     ("", None), ("INTERNL", None), (None, None), ("SECRET", None)],
)
def test_parse(raw, expected):
    assert clearance.parse(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [("RESTRICTED", "RESTRICTED"), ("internal", "INTERNAL"),
     ("INTERNL", "PUBLIC"), (None, "PUBLIC"), ("", "PUBLIC"), ("garbage", "PUBLIC")],
)
def test_floor_public_fails_safe(raw, expected):
    assert clearance.floor_public(raw) == expected


def test_min_level():
    assert clearance.min_level("INTERNAL", "RESTRICTED") == "INTERNAL"
    assert clearance.min_level("RESTRICTED", "PUBLIC") == "PUBLIC"
    assert clearance.min_level("INTERNAL", "INTERNAL") == "INTERNAL"


def test_sql_enum_parity():
    """ORDER must match the Postgres ``classification_level`` enum in init.sql."""
    sql = Path(__file__).resolve().parent.parent / "init.sql"
    if not sql.exists():
        pytest.skip("init.sql not found")
    text = sql.read_text(encoding="utf-8")
    m = re.search(r"create\s+type\s+classification_level\s+as\s+enum\s*\(([^)]*)\)", text, re.I)
    if not m:
        pytest.skip("classification_level enum not found in init.sql")
    values = [v.strip().strip("'\"") for v in m.group(1).split(",") if v.strip()]
    assert tuple(values) == clearance.LEVELS
