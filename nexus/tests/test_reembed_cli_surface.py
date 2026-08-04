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


@pytest.mark.parametrize("command", ["run", "status"])
def test_both_commands_take_all_tenants(command):
    """범위를 손으로 세지 않는다는 약속은 두 명령 모두에 있어야 한다 — 절차가 둘 다 부른다."""
    result = runner.invoke(app, ["reembed", command, "--help"])
    assert result.exit_code == 0
    assert "--all-tenants" in result.stdout


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


def test_the_agreeing_pair_is_not_rejected_by_that_guard():
    """음성 대조군 — 무엇이든 거부하는 가드는 가드가 아니다. (DB 가 없으니 그 다음에 실패한다.)"""
    result = runner.invoke(app, ["reembed", "run", "--column", "embedding_1024",
                                 "--model", "KURE-v1", "--tenant", "t"])
    assert "차원이 다르다" not in (result.stdout + str(result.stderr))
