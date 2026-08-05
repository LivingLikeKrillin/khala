"""재임베딩 CLI 가 **광고하는 옵션을 실제로 가지고 있는가** (SPEC-nexus-embedding-cutover-seam §4.3, §4.6).

이 파일이 존재하는 이유는 구체적이다: `--all-tenants` 를 `run` 과 `status` 양쪽에 넣었다고 적어
놓고 실제로는 `run` 에만 들어간 채 머지됐다. 치환이 조용히 빗나갔고, 어떤 테스트도 CLI 표면을 보지
않았으며, 런북의 절차는 `status --all-tenants` 를 부른다 — 컷오버 당일에 "No such option" 으로
멈추는 종류의 결함이다.

여기서 재는 것은 동작이 아니라 **계약**이다: 런북과 SPEC 이 부르는 명령줄이 파서를 통과하는가.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from nexus.cli import app

runner = CliRunner()


def _rejects(command: str, argv: list[str]) -> str:
    """명령을 실제로 파싱시켜 본다. **표현이 아니라 행동을 재는 이유는 두 번 데였기 때문이다.**

    1. `--help` 출력에서 `"--all-tenants"` 를 찾는 검사는 CI 에서 깨졌다. 원인은 폭이 아니라
       **색**이다: CI 는 색을 켜고, typer 의 rich 하이라이터는 옵션 이름을 style 세그먼트로
       쪼갠다 — 원문에는 `\\x1b[1;36m-\\x1b[0m\\x1b[1;36m-all\\x1b[0m\\x1b[1;36m-tenants\\x1b[0m`
       가 들어 있어 `"--all-tenants"` 라는 연속 문자열이 **존재하지 않는다**(FORCE_COLOR=1 로 재현).
    2. 그 다음에 쓴 파서 내부 순회(`isinstance(p, click.Option)`)도 깨졌다. typer 0.26+ 는
       **click 을 벤더링**해서(`typer._click`) 설치된 click 으로 한 isinstance 가 전부 빗나가고,
       조용히 빈 집합이 된다. 로컬은 typer 0.24 라 통과했다.

    남는 것은 행동이다: 옵션이 없으면 click 이 `No such option` 으로 죽고, 있으면 우리 자신의
    거부 메시지가 나온다. 그 차이는 색에도 버전에도 흔들리지 않는다.
    """
    result = runner.invoke(app, ["reembed", command, *argv])
    return result.stdout + str(result.stderr or "")


@pytest.mark.parametrize("command", ["run", "status"])
def test_both_commands_take_all_tenants(command):
    """범위를 손으로 세지 않는다는 약속은 두 명령 모두에 있어야 한다 — 런북이 둘 다 부른다."""
    output = _rejects(command, ["--tenant", "t", "--all-tenants"])
    assert "No such option" not in output, f"{command} 이 --all-tenants 를 모른다"
    assert "함께 쓸 수 없다" in output, "옵션은 있는데 범위 충돌을 안 막는다"


@pytest.mark.parametrize("command,option", [
    ("run", "--column"), ("run", "--model"), ("run", "--backend"), ("run", "--tenant"),
    ("status", "--column"), ("status", "--tenant"),
])
def test_the_runbook_command_lines_parse(command, option):
    """런북과 SPEC 이 타이핑하는 옵션들 — 하나라도 없으면 컷오버 당일에 멈춘다.

    값을 안 주고 부르면 파서가 "값이 필요하다" 고 하고, 옵션 자체가 없으면 "No such option" 이다.
    """
    assert "No such option" not in _rejects(command, [option])


@pytest.mark.parametrize("command", ["run", "status"])
def test_the_scope_must_be_one_thing(command):
    """`--tenant` 와 `--all-tenants` 를 함께 주면 어느 범위인지 알 수 없다 — DB 없이도 막힌다."""
    result = runner.invoke(app, ["reembed", command, "--tenant", "t", "--all-tenants"])
    assert result.exit_code == 2
    assert "함께 쓸 수 없다" in (result.stdout + str(result.stderr))


def test_a_run_whose_model_and_column_disagree_stops_before_reading_a_row():
    """차원이 다른 조합은 절반쯤 돌다 실패하는 대신 시작하지 않아야 한다 (§4.3 불변식 2)."""
    result = runner.invoke(app, ["reembed", "run", "--column", "embedding",
                                 "--model", "KURE-v1", "--tenant", "t"])
    assert result.exit_code == 2
    assert "차원이 다르다" in (result.stdout + str(result.stderr))


@pytest.mark.parametrize("command", ["run", "status"])
def test_the_check_survives_the_thing_that_broke_it(command, monkeypatch):
    """색이 켜진 상태 — CI 가 실제로 도는 조건이다. 이 계열의 결함이 되돌아오면 여기서 걸린다.

    `FORCE_COLOR` 는 rich 가 렌더 시점에 읽으므로, 테스트가 켜면 CI 의 그 조건이 된다.
    """
    monkeypatch.setenv("FORCE_COLOR", "1")
    output = _rejects(command, ["--tenant", "t", "--all-tenants"])
    assert "No such option" not in output
    assert "함께 쓸 수 없다" in output


def test_the_agreeing_pair_is_not_rejected_by_that_guard():
    """음성 대조군 — 무엇이든 거부하는 가드는 가드가 아니다. (DB 가 없으니 그 다음에 실패한다.)"""
    result = runner.invoke(app, ["reembed", "run", "--column", "embedding_1024",
                                 "--model", "KURE-v1", "--tenant", "t"])
    assert "차원이 다르다" not in (result.stdout + str(result.stderr))
