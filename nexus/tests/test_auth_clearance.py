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


def _modules_with_an_ordering_table() -> list[str]:
    """등급 순서표를 **직접 적은** 파이썬 모듈들. AST 로 본다.

    ⛔ **왜 AST 인가.** 이 리포는 소스 문자열 검사에 데인 적이 있다(*"문자열이 있다는 것은 그
    코드가 돌았다는 뜻이 아니다"*). 그런데 여기서 지켜야 할 성질은 **텍스트 그 자체**다 —
    "이 순서를 적은 자리가 몇 곳인가". 돌든 안 돌든 두 번째 사본이 존재하면 갈릴 수 있다.
    그래서 정규식 대신 **딕셔너리 리터럴의 키 집합**을 본다: 주석·문자열 안의 낱말에 안 걸리고,
    줄바꿈·따옴표 모양이 달라도 잡힌다.
    """
    import ast as _ast

    root = Path(__file__).resolve().parent.parent / "nexus"
    want = set(clearance.LEVELS)
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        try:
            tree = _ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                       # 검사가 파싱 때문에 죽지 않는다
            continue
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.Dict) or len(node.keys) != len(want):
                continue
            keys = {k.value for k in node.keys
                    if isinstance(k, _ast.Constant) and isinstance(k.value, str)}
            if keys == want:
                found.append(str(path.relative_to(root)).replace("\\", "/"))
                break
    return found


def test_the_order_lives_in_exactly_one_place():
    """⛔ 이 모듈의 첫 줄이 *"the single source of truth"* 라고 주장한다 — 그 주장을 검사로 만든다.

    **왜 (외부 평가 F1, 2026-09-02).** `models/resource.py` 에 두 번째 순서표가 있었고 그것으로
    접근 통제 함수까지 구현돼 있었다. 프로덕션 호출자는 0이었지만, 정본에는 SQL enum 동등성
    검사가 있고 **사본에는 없어서** enum 에 등급이 추가되면 사본만 조용히 뒤처지는 구조였다.

    주장이 코드와 갈렸는데 **아무 검사도 그 주장을 지키지 않았다** — 이 리포의 반복 결함이
    "틀린 답" 이 아니라 "문서가 주장하는데 코드가 안 하는 것" 이라고 평가서가 적은 그대로다.
    """
    where = _modules_with_an_ordering_table()
    assert where == ["auth/clearance.py"], (
        f"등급 순서표가 {len(where)}곳에 있다: {where}. 사본은 고치지 말고 **없애라** — "
        "정본에만 SQL enum 동등성 검사가 붙어 있어 사본은 조용히 뒤처진다")


def test_that_check_can_see_a_copy():
    """⛔ 일부러 확인한다 — 찾아내지 못하는 검사는 초록이어도 아무 말도 안 한다."""
    import ast as _ast

    tree = _ast.parse('X = {"PUBLIC": 0, "INTERNAL": 1, "RESTRICTED": 2}')
    dicts = [n for n in _ast.walk(tree) if isinstance(n, _ast.Dict)]
    keys = {k.value for k in dicts[0].keys}
    assert keys == set(clearance.LEVELS), "탐지 규칙이 실제 사본 모양을 못 알아본다"
