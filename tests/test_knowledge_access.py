"""에이전트가 조직 지식을 어디서 가져갔는지 세는 분류기에 이가 있는가.

이 자가 재려는 것은 하나다 — **문을 열어 놨더니 실제로 그 문으로 가는가.** 그러니 두 방향을
다 틀리면 안 된다: khala 를 거친 것을 우회로 세면 비율이 거짓으로 낮아지고, 아무 명령이나
우회로 세면 분모가 부풀어 같은 방향으로 거짓이 된다.

**khala 자신의 코드를 grep 하는 것은 우회가 아니다.** 그건 `grep` 이 정확한 자리이고, 그것까지
세면 이 수는 "에이전트가 grep 을 얼마나 쓰나" 가 된다.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 리포 관례 — tests/test_fingerprint_scan.py 와 같다
sys.path.insert(0, str(ROOT / "scripts" / "hooks"))

import knowledge_access  # noqa: E402
from knowledge_access import classify, host_code_tree  # noqa: E402


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


def test_the_team_code_tree_counts_on_the_host_too():
    """⛔ 이 자가 없으면 계수기는 **컨테이너 안에서만** 우회를 본다.

    `/code-src` 는 마운트 지점이다 — 에이전트는 호스트에서 돌고, 호스트에서 팀 코드 트리를
    직접 grep 하는 것이 바로 이 계수기가 잡으려던 우회다. 그 경로는 배포마다 다르고
    (이 리포는 public 이라) 박아 넣을 수 없으니 **설정에서 온다**.
    """
    tree = "/srv/team-platform"
    for cmd in (
        f"grep -rn 'PartyRoom' {tree}/src/main/java",
        f"rg --files {tree}",
        f"cat {tree}/README.md",
    ):
        assert classify(cmd, code_src=tree) == "bypass", cmd


def test_the_team_code_tree_matches_regardless_of_slash_or_case():
    r"""호스트가 Windows 다. 같은 트리를 `C:\...` 로도 `C:/...` 로도 친다."""
    tree = "C:/labs/team-platform"
    assert classify(r"grep -rn 'X' C:\labs\team-platform\src", code_src=tree) == "bypass"
    assert classify("grep -rn 'X' c:/LABS/team-platform/src", code_src=tree) == "bypass"


def test_a_configured_tree_does_not_make_this_repo_a_bypass():
    """대조군 — 설정이 붙었다고 khala 자신을 뒤지는 것까지 우회가 되면 안 된다."""
    assert classify("grep -rn 'hybrid_search' nexus/nexus/search/hybrid.py",
                    code_src="/srv/team-platform") is None


def test_the_host_tree_comes_from_the_deployment_env_file(tmp_path):
    """경로는 리포에 못 박는다(public). 배포가 이미 갖고 있는 값을 읽는다 —
    `nexus/.env` 의 `CODE_SRC_PATH` 가 컨테이너 `/code-src` 마운트의 **원본**이다."""
    env = tmp_path / ".env"
    env.write_text("\n".join([
        "# comment",
        "NEXUS_DB_URL=postgresql://x",
        "CODE_SRC_PATH=/srv/team-platform",
    ]), encoding="utf-8")
    assert host_code_tree(env_file=env) == "/srv/team-platform"


def test_no_configured_tree_is_not_an_error(tmp_path):
    """배포가 코드 트리를 안 붙였을 수 있다. 그때는 **그 축을 안 세는 것**이지 죽는 게 아니다."""
    env = tmp_path / ".env"
    env.write_text("CODE_SRC_PATH=", encoding="utf-8")
    assert host_code_tree(env_file=env) is None
    assert host_code_tree(env_file=tmp_path / "nope.env") is None


def test_the_hook_actually_passes_the_configured_tree(tmp_path, monkeypatch):
    """⛔ **배선 자.** 이 리포가 데인 모양이 정확히 이것이다 — 분류기 자는 초록인데 부르는
    데가 없어 라이브에서는 아무것도 안 세어진다. 그러니 훅을 통째로 돌린다."""
    monkeypatch.setattr(knowledge_access, "LOG", tmp_path / "ledger.jsonl")
    monkeypatch.setenv("CODE_SRC_PATH", "/srv/team-platform")
    payload = {"tool_input": {"command": "grep -rn 'PartyRoom' /srv/team-platform/src"}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    assert knowledge_access.main() == 0

    rows = [json.loads(ln) for ln
            in (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert [r["kind"] for r in rows] == ["bypass"]


def test_the_hook_stores_no_command_text(tmp_path, monkeypatch):
    """이 리포는 public 이고 질의문에는 조직 어휘가 들어간다. 남는 것은 분류와 해시뿐이다."""
    monkeypatch.setattr(knowledge_access, "LOG", tmp_path / "ledger.jsonl")
    secret = "docker exec nexus-app python -m nexus.cli query 'PartyRoom 정책'"
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"command": secret}})))

    assert knowledge_access.main() == 0

    written = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8")
    assert "PartyRoom" not in written
    assert json.loads(written.strip())["kind"] == "khala"


def test_a_non_bash_tool_reaching_the_team_tree_is_counted(tmp_path, monkeypatch):
    """우회는 **셸을 안 지나도** 일어난다 — Grep·Read 도구가 같은 트리를 연다.
    그쪽을 안 세면 분모만 줄어들어 비율이 또 구성상 1.0 으로 기운다."""
    monkeypatch.setattr(knowledge_access, "LOG", tmp_path / "ledger.jsonl")
    monkeypatch.setenv("CODE_SRC_PATH", "/srv/team-platform")
    for tool_input in (
        {"pattern": "PartyRoom", "path": "/srv/team-platform/src"},
        {"file_path": "/srv/team-platform/src/main/java/X.java"},
    ):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": tool_input})))
        assert knowledge_access.main() == 0

    rows = [json.loads(ln) for ln
            in (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert [r["kind"] for r in rows] == ["bypass", "bypass"]


def test_a_search_pattern_is_not_a_door(tmp_path, monkeypatch):
    """대조군 — 리포 안에서 `nexus.cli query` 라는 **문자열을 찾는 것**은 문을 지난 게 아니다.
    패턴까지 읽으면 분자가 부풀고, 그 방향의 거짓이 이 자에서 제일 달다."""
    monkeypatch.setattr(knowledge_access, "LOG", tmp_path / "ledger.jsonl")
    payload = {"tool_input": {"pattern": "nexus.cli query", "path": "scripts/hooks"}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    assert knowledge_access.main() == 0
    assert not (tmp_path / "ledger.jsonl").exists()


def test_the_matcher_covers_every_tool_the_hook_can_read():
    """⛔ 훅이 Read·Grep 을 해석해도 **하니스가 안 부르면** 죽은 코드다.
    `.claude/settings.json` 의 matcher 가 그 배선이고, 여기서 그것을 센다."""
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    matchers = [h["matcher"] for h in settings["hooks"]["PreToolUse"]]
    joined = "|".join(matchers)
    for tool in ("Bash", "Grep", "Glob", "Read"):
        assert tool in joined, tool
