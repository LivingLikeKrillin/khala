"""Arbiter CLI — 사람(그리고 에이전트)이 손으로 게이트를 돌린다.

MCP 서버(`server.py`)와 **같은 함수**를 부른다. 표면만 얇게 씌운다. 지금까지 12개 도구가
MCP 전용이라, 승인 게이트를 돌리려면 `khala.arbiter.ledger` 에 대고 파이썬을 손으로 짜야
했다 — 거버넌스 코어를 사람이 못 돌리는 것은 거버넌스가 아니다.

    arbiter record spec "제목"          # 초안 등록 → id 출력
    arbiter critique <id>               # 비평 실행 → 이슈 출력
    arbiter approve <id> --dispositions disp.json --approver 이름
    arbiter status [<id>]               # 상태 조회
    arbiter begin-implementation <id>   # 구현 게이트 열기
    arbiter end-implementation          # 구현 게이트 닫기
    arbiter check-gate <path>...        # 보호 경로 점검

게이트를 여는 두 명령은 나중에 붙었다. `check-gate` 만 있던 동안 CLI 는 "활성 spec 없음 —
begin_implementation 필요" 라고 거절만 하고 그것을 푸는 방법을 주지 않았다. 게이트를 확인은
되는데 만족시킬 수 없으면 위 문단의 문제가 그대로 남는다.

critic 은 주입 가능(테스트는 FakeCritic, 프로덕션은 AnthropicCritic).
"""

from __future__ import annotations

import json
import os
import re
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
from .critique import critique, make_critic
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
            # SPEC-arbiter-status-is-read-only §3.1 — `in_review` alone cannot tell
            # "a critique was opened" from "the stamp went stale", and since status()
            # no longer writes, the file will not say either. The flags are the reader.
            flags = " ".join(k for k in ("needs_review", "tampered") if row.get(k))
            typer.echo(
                f"{row['id']:40} {row.get('status', '?'):10} {flags} "
                f"{row.get('title', '')}".rstrip()
            )

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
        dispositions: Path = typer.Option(
            ..., "--dispositions",
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

    @app.command(name="begin-implementation")
    def begin_implementation(spec_id: str = typer.Argument(...)) -> None:
        """구현 게이트를 연다 — 이 spec 에 대고 작업한다고 선언한다."""
        # 없는 id 로 열면 게이트는 status=None 으로 계속 거절하고, 왜 거절하는지는
        # 안 알려준다. 다른 CLI 명령과 같은 자리에서 먼저 걸러낸다.
        _resolve_or_die(spec_id)
        gate.begin_implementation(spec_id, set_by="cli")
        typer.echo(f"구현 시작: {spec_id}")

    @app.command(name="end-implementation")
    def end_implementation() -> None:
        """구현 게이트를 닫는다. 열려 있지 않아도 오류가 아니다."""
        active = gate.active_spec()
        gate.end_implementation()
        typer.echo(f"구현 종료: {active}" if active else "열린 구현 없음")

    @app.command(name="check-gate")
    def check_gate(paths: list[str] = typer.Argument(...)) -> None:
        """경로가 보호 대상인지 점검한다."""
        result = gate.check_gate(paths, ledger, config)
        typer.echo(json.dumps(result, ensure_ascii=False))

    return app


#: Git Bash / MSYS 는 `$PWD` 를 `/c/Users/...` 로 준다. Windows 의 Python 은 그것을 풀지
#: 못하고, 결과는 "아티팩트를 찾을 수 없음" 이라는 **원인과 무관해 보이는** 오류다.
#: 이 프로젝트는 이 함정으로 이미 한 번 라운드를 날렸다. 도구가 막는다.
_MSYS_DRIVE = re.compile(r"^/([A-Za-z])/(.*)$")


def _resolve_dir(raw: str) -> Path:
    """MSYS 형태(`/c/...`)를 Windows 형태로 바꾼다.

    `Path("/c/...").exists()` 를 조건으로 쓰면 안 된다 — Windows 는 선행 `/` 를 현재 드라이브의
    루트로 읽어 그 경로가 **존재한다고 답한다**. 그래서 변환은 raw 의 존재 여부가 아니라
    **변환형이 존재하는가** 로 판단한다. 진짜 `\\c\\...` 디렉터리가 있을 확률보다 MSYS 경로일
    확률이 압도적으로 높고, 틀렸을 때의 증상("아티팩트 없음")이 원인과 전혀 닮지 않았다.
    """
    if os.name == "nt":
        m = _MSYS_DRIVE.match(raw)
        if m:
            drive, rest = m.groups()
            converted = Path(f"{drive.upper()}:/{rest}")
            if converted.exists():
                return converted
    return Path(raw)


def main() -> None:
    root = _resolve_dir(os.environ.get("ARBITER_ROOT", "."))
    docs = _resolve_dir(os.environ.get("ARBITER_DOCS", str(root / "docs")))

    # 없는 경로를 안고 들어가면 나중에 "아티팩트 없음" 으로 나타난다. 여기서 이름을 대고 죽는다.
    for label, path in (("ARBITER_ROOT", root), ("ARBITER_DOCS", docs)):
        if not path.exists():
            typer.echo(
                f"{label} 이 가리키는 경로가 없습니다: {path}\n"
                "Git Bash 라면 `$PWD` 는 POSIX 경로(`/c/...`)라 Windows 에서 풀리지 않습니다. "
                "`C:/...` 형태로 주십시오.", err=True)
            # typer.Exit 는 명령 안에서만 잡힌다. 여기는 main() 이라 SystemExit 로 나간다.
            raise SystemExit(2)

    build_cli(root, docs, make_critic())()


if __name__ == "__main__":
    main()
