"""에이전트가 조직 지식을 어디서 가져갔는지 세는 분류기에 이가 있는가.

이 자가 재려는 것은 하나다 — **문을 열어 놨더니 실제로 그 문으로 가는가.** 그러니 두 방향을
다 틀리면 안 된다: khala 를 거친 것을 우회로 세면 비율이 거짓으로 낮아지고, 아무 명령이나
우회로 세면 분모가 부풀어 같은 방향으로 거짓이 된다.

**khala 자신의 코드를 grep 하는 것은 우회가 아니다.** 그건 `grep` 이 정확한 자리이고, 그것까지
세면 이 수는 "에이전트가 grep 을 얼마나 쓰나" 가 된다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 리포 관례 — tests/test_fingerprint_scan.py 와 같다
sys.path.insert(0, str(ROOT / "scripts" / "hooks"))

from knowledge_access import classify  # noqa: E402


def test_the_khala_door_is_counted_as_the_door():
    for cmd in (
        'docker exec nexus-app python -m nexus.cli query "질문" --no-answer',
        'docker exec nexus-app python -m nexus.cli query "질문" --tenant design_docs',
        'curl -X POST http://localhost:8000/search/answer -d "{}"',
    ):
        assert classify(cmd) == "khala", cmd


def test_going_straight_to_the_corpus_is_a_bypass():
    """**가장 중요한 대조군.** 이 셋이 세어지지 않으면 분모가 사라지고, 비율은 언제나 1.0 이
    된다 — 즉 자가 자기를 통과시킨다."""
    for cmd in (
        'docker exec nexus-db psql -U nexus -d nexus -c "SELECT count(*) FROM documents"',
        'psql "postgresql://nexus:nexus@localhost:5432/nexus" -c "select 1"',
        "grep -rn 'PartyRoom' /code-src/src/main/java",
    ):
        assert classify(cmd) == "bypass", cmd


def test_grepping_this_repo_is_not_a_bypass():
    """khala 자신의 코드·문서는 조직 지식이 아니다. 세면 이 수의 뜻이 바뀐다."""
    for cmd in (
        "grep -rn 'hybrid_search' nexus/nexus/search/hybrid.py",
        "git log --oneline -5",
        "python -m pytest nexus/tests -q",
        "cat OPEN.md",
    ):
        assert classify(cmd) is None, cmd


def test_the_door_wins_when_a_command_mentions_both():
    """khala 질의를 psql 로 파이프하는 명령은 **문을 지난 것**이다 — 우회로 세면 안 된다."""
    cmd = ('docker exec nexus-app python -m nexus.cli query "x" --no-answer '
           '| tee /tmp/out; docker exec nexus-db psql -c "select 1"')
    assert classify(cmd) == "khala"


def test_an_empty_command_is_not_an_access():
    assert classify("") is None
    assert classify(None or "") is None
