"""Arbiter CLI — 사람(그리고 에이전트)이 손으로 게이트를 돌린다.

MCP 서버(`server.py`)와 **같은 함수**를 부른다. 표면만 얇게 씌운다. 지금까지 12개 도구가
MCP 전용이라, 승인 게이트를 돌리려면 `khala.arbiter.ledger` 에 대고 파이썬을 손으로 짜야
했다 — 거버넌스 코어를 사람이 못 돌리는 것은 거버넌스가 아니다.

    arbiter record spec "제목"          # 초안 등록 → id 출력
    arbiter critique <id>               # 비평 실행 → 이슈 출력
    arbiter approve <id> --dispositions disp.json --approver 이름
    arbiter status [<id>]               # 상태 조회
    arbiter check-gate <path>...        # 보호 경로 점검

critic 은 주입 가능(테스트는 FakeCritic, 프로덕션은 AnthropicCritic).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer

# Windows 콘솔(cp949)은 한글이 든 출력에서 죽는다. UTF-8 로 재구성 (nexus/cli.py 와 동일 패턴).
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 — 재구성 불가 환경이면 그냥 둔다
        pass

from . import review
from .config import ArbiterConfig
from .critique import AnthropicCritic, critique
from .errors import ArtifactNotFoundError
from .gate import Gate
from .ledger import Ledger


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_cli(root: Path, docs: Path, critic) -> typer.Typer:
    """MCP 서버와 같은 조립(ledger/gate/critic)을 CLI 명령으로 노출한다."""
    app = typer.Typer(help="Arbiter — 문서·결정 승인 게이트 (SPEC/ADR)", no_args_is_help=True)
    config = ArbiterConfig.load(root)
    ledger = Ledger(docs, now=_utc_now)
    gate = Gate(root, now=_utc_now)

    def _resolve_or_die(artifact_id: str):
        try:
            return ledger._resolve(artifact_id)
        except ArtifactNotFoundError as e:
            typer.echo(f"없는 아티팩트: {artifact_id}", err=True)
            raise typer.Exit(1) from e

    @app.command()
    def record(
        type: str = typer.Argument(..., help="spec | adr"),
        title: str = typer.Argument(...),
        slug: str | None = typer.Option(None, "--slug"),
    ) -> None:
        """초안을 등록하고 id 를 출력한다."""
        try:
            typer.echo(ledger.record(type, title, slug))
        except ValueError as e:
            typer.echo(f"거부: {e}", err=True)
            raise typer.Exit(1) from None

    @app.command()
    def status(artifact_id: str | None = typer.Argument(None)) -> None:
        """아티팩트 상태 조회. id 를 비우면 전체."""
        for row in ledger.status(artifact_id):
            typer.echo(f"{row['id']:40} {row.get('status', '?'):10} {row.get('title', '')}")

    @app.command(name="critique")
    def critique_cmd(artifact_id: str = typer.Argument(...)) -> None:
        """비평을 실행하고 이슈를 출력한다."""
        _resolve_or_die(artifact_id)
        issues = critique(ledger, artifact_id, critic, now=_utc_now)
        if not issues:
            typer.echo("이슈 없음.")
            return
        for i in issues:
            d = i.to_dict()
            typer.echo(f"[{d['issue_id']}] ({d['severity']}) {d['category']}: {d['description']}")

    @app.command()
    def approve(
        artifact_id: str = typer.Argument(...),
        dispositions: Path = typer.Option(..., "--dispositions",
                                          help="처분 JSON 파일 (리스트: {issue_id, disposition, reason?})"),
        approver: str = typer.Option(..., "--approver", help="승인자 (사람의 서명)"),
    ) -> None:
        """비평 이슈에 처분을 적용하고 승인한다. rejected/deferred 는 사유 필수."""
        _resolve_or_die(artifact_id)
        try:
            disp = json.loads(dispositions.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            typer.echo(f"처분 파일을 읽을 수 없습니다: {e}", err=True)
            raise typer.Exit(1) from None
        try:
            review.approve(ledger, artifact_id, disp, approver, now=_utc_now)
        except Exception as e:  # noqa: BLE001 — ReviewError 등을 깔끔한 메시지로
            typer.echo(f"거부: {e}", err=True)
            raise typer.Exit(1) from None
        typer.echo(f"승인됨: {artifact_id} (by {approver})")

    @app.command(name="check-gate")
    def check_gate(paths: list[str] = typer.Argument(...)) -> None:
        """경로가 보호 대상인지 점검한다."""
        result = gate.check_gate(paths, ledger, config)
        typer.echo(json.dumps(result, ensure_ascii=False))

    return app


def main() -> None:
    root = Path(os.environ.get("ARBITER_ROOT", "."))
    docs = Path(os.environ.get("ARBITER_DOCS", str(root / "docs")))
    build_cli(root, docs, AnthropicCritic())()


if __name__ == "__main__":
    main()
