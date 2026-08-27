"""에이전트가 조직 지식을 어디서 가져갔는지 세는 분류기에 이가 있는가.

이 테스트가 재려는 것은 하나다 — **문을 열어 놨더니 실제로 그 문으로 가는가.** 그러니 두 방향을
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
    된다 — 즉 테스트가 자기를 통과시킨다."""
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
    """⛔ 이 테스트가 없으면 계수기는 **컨테이너 안에서만** 우회를 본다.

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
    """⛔ **배선 테스트.** 이 리포가 데인 모양이 정확히 이것이다 — 분류기 테스트는 초록인데 부르는
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
    패턴까지 읽으면 분자가 부풀고, 그 방향의 거짓이 이 테스트에서 제일 달다."""
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


# ── 값싼 선별 ──────────────────────────────────────────────────────────────
#
# 훅은 이제 **모든** 도구 호출 앞에 선다. 그런데 그 호출의 압도적 다수는 조직 지식과
# 아무 상관이 없고(자기 리포 파일 읽기), 그 판정을 하려고 무거운 모듈을 다 부르는 것이
# 값의 전부였다 — 실측: 부팅·import 90 ms 대 실제 일 0 ms 에 가까움.
#
# 그래서 원문을 **디코드하기 전에** 문자열로 한 번 거른다. 이 선별은 일부러 **넉넉해야**
# 한다(거짓 양성은 느릴 뿐, 거짓 음성은 안 세어진다 = 비율이 거짓이 된다).


def test_an_ordinary_file_read_is_screened_out_before_any_work():
    """대부분의 호출이 여기서 끝나야 값이 준다."""
    for raw in (
        '{"tool_input": {"file_path": "docs/index.md"}}',
        '{"tool_input": {"pattern": "hybrid_search", "path": "nexus"}}',
        '{"tool_input": {"command": "git status --short"}}',
    ):
        assert knowledge_access.might_be_an_access(raw, None) is False, raw


def test_the_screen_lets_every_real_access_through():
    """⛔ **거짓 음성이 이 테스트의 유일한 치명상이다.** 여기서 놓치면 뒤의 정밀 분류기는
    아예 안 불린다 — 즉 안 세어지고, 분모만 조용히 줄어든다."""
    door = "docker exec app python -m " + "nexus" + ".cli " + "query 'x'"
    corpus = "docker exec " + "nexus" + "-db " + "psql" + " -U u -d d -c 'select 1'"
    for raw in ('{"tool_input": {"command": "' + door + '"}}',
                '{"tool_input": {"command": "' + corpus + '"}}'):
        assert knowledge_access.might_be_an_access(raw, None) is True, raw


def test_the_screen_survives_json_escaping_of_windows_paths():
    """원문은 아직 JSON 이다 — Windows 경로의 역슬래시가 `\\\\` 로 이스케이프돼 있고,
    그 상태로 설정 속 경로와 대 봐야 한다. 여기서 갈리면 우회가 통째로 안 세어진다."""
    esc = chr(92) * 2  # JSON 안에서 역슬래시 하나는 두 글자로 온다
    raw = ('{"tool_input": {"file_path": "C:' + esc + 'labs' + esc
           + 'team-platform' + esc + 'X.java"}}')
    assert knowledge_access.might_be_an_access(raw, "C:/labs/team-platform") is True
    assert knowledge_access.might_be_an_access(raw, "C:/labs/other-tree") is False


def test_the_hook_is_launched_without_site_scanning():
    """값의 전부가 부팅이다. 이 훅은 표준 라이브러리만 쓰므로 `site` 를 뒤질 이유가 없고,
    `-S -E` 하나가 이 머신에서 **71.6 → 32.4 ms** 였다(2026-08-27 실측).

    무해해 보여서 지우기 쉬운 플래그라 여기 박는다 — 지우면 훅이 배로 느려지고, 그
    느려짐은 **모든 도구 호출**에 붙는다.
    """
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    cmds = [h["command"] for grp in settings["hooks"]["PreToolUse"] for h in grp["hooks"]]
    assert any(" -S " in c for c in cmds), cmds


# ── 파이프는 UTF-8 이 아니다 ────────────────────────────────────────────────
#
# ⛔ **위의 배선 테스트들은 이것을 볼 수 없다.** 그것들은 `io.StringIO` 를 꽂는데, 그건 이미
# 디코드된 문자열이다 — 라이브에서 잃은 것은 **디코딩 그 자체**다. 실측 2026-08-27: 훅이
# 받는 stdin 은 콘솔 코드페이지로 열린다(한국어 Windows 에서 `cp949`, `surrogateescape`).
# 그래서 한글이 든 질의는 서러게이트가 섞인 채로 들어오고, 해시를 뜨는 자리에서 터진다.
# 분류는 이미 `khala` 로 끝난 뒤였다 — 즉 **문을 지난 것만 골라서 안 세어졌다.**
# 우회 쪽 명령은 대개 경로뿐이라 ASCII 로 살아남는다. 비율이 한 방향으로 거짓이 된다.
#
# 같은 이가 `terms_guard.py` 에서는 하루 먼저 잡혔다(#329). 이쪽으로 안 옮겨진 것뿐이다.


def _run_the_hook_in_a_real_process(tmp_path, payload: dict, stdin_encoding: str):
    """훅을 **별도 프로세스**로, 진짜 파이프로 돌린다.

    기록 파일 경로는 스크립트 위치에서 나오므로(`_root()`) 정본을 tmp 로 복사해 돌린다 —
    테스트가 라이브 기록 파일을 더럽히면 그 기록이 곧 지표라 값이 상한다.

    `-E` 는 일부러 뺀다. 프로덕션에서 이 인코딩은 인터프리터 **밖에서**(Windows 콘솔)
    정해지고, 테스트는 그것을 `PYTHONIOENCODING` 으로 흉내 내는 것이기 때문이다.
    """
    import os
    import shutil
    import subprocess

    hooks = tmp_path / "scripts" / "hooks"
    hooks.mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "hooks" / "knowledge_access.py",
                hooks / "knowledge_access.py")
    env = {**os.environ, "PYTHONIOENCODING": stdin_encoding}
    env.pop("CODE_SRC_PATH", None)
    proc = subprocess.run(
        [sys.executable, "-S", str(hooks / "knowledge_access.py")],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True, env=env,
    )
    ledger = tmp_path / ".khala" / "knowledge-access.jsonl"
    rows = ([json.loads(ln) for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
            if ledger.exists() else [])
    return proc, rows


def test_a_korean_query_survives_a_console_codepage_pipe(tmp_path):
    """이 리포의 실제 질의는 한국어다. 이것이 안 세어지면 분자가 통째로 사라진다."""
    payload = {"tool_name": "Bash", "tool_input": {
        "command": 'docker exec nexus-app python -m nexus.cli query "정책은 무엇인가" --no-answer'}}
    proc, rows = _run_the_hook_in_a_real_process(tmp_path, payload, "cp949:surrogateescape")

    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert [r["kind"] for r in rows] == ["khala"]


def test_an_ascii_command_still_counts_in_the_same_process(tmp_path):
    """대조군 — 위를 통과시키려고 전부 삼키면 이쪽이 빈다."""
    payload = {"tool_name": "Bash", "tool_input": {
        "command": 'docker exec nexus-db psql -U nexus -d nexus -c "select 1"'}}
    proc, rows = _run_the_hook_in_a_real_process(tmp_path, payload, "cp949:surrogateescape")

    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert [r["kind"] for r in rows] == ["bypass"]
