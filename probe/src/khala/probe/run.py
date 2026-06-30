import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from khala.probe.extract import extract_survivors
from khala.probe.models import Survivor

DEFAULT_TEST_COMMAND = "python -m pytest -q -x"

# TOML basic string에서 반드시 이스케이프해야 하는 문자(역슬래시 우선).
_TOML_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _toml_basic_string(value: str) -> str:
    """문자열을 TOML basic string 리터럴로 안전하게 직렬화.

    Windows 경로의 역슬래시나 명령의 따옴표가 보간으로 TOML을 깨뜨리지 않도록
    문자 단위로 이스케이프한다(역슬래시 자기-이중화 방지를 위해 per-char 매핑).
    """
    return '"' + "".join(_TOML_ESCAPES.get(c, c) for c in value) + '"'


def build_config(module_path: str, test_command: str = DEFAULT_TEST_COMMAND) -> str:
    """단일 모듈 대상 cosmic-ray config(TOML 문자열) 생성.

    cosmic-ray는 module-path를 단일 경로로 받으므로 모듈별 1 config.
    """
    return (
        "[cosmic-ray]\n"
        f"module-path = {_toml_basic_string(module_path)}\n"
        "timeout = 30.0\n"
        "excluded-modules = []\n"
        f"test-command = {_toml_basic_string(test_command)}\n"
        "\n"
        "[cosmic-ray.distributor]\n"
        'name = "local"\n'
    )


def _cosmic_ray(args: list[str], workdir: Path) -> str:
    """cosmic-ray 호출(cwd=workdir) → stdout. 비정상 종료는 예외 전파(fail-open 금지, spec §8)."""
    return subprocess.run(
        ["cosmic-ray", *args], cwd=workdir, capture_output=True, text=True, check=True
    ).stdout


def run_mutation(
    module_path: str,
    workdir: Path,
    test_command: str = DEFAULT_TEST_COMMAND,
    *,
    runner: Callable[[list[str], Path], str] = _cosmic_ray,
) -> list[Survivor]:
    """단일 모듈에 cosmic-ray 전체 사이클 실행 → survivor 목록.

    config·session은 **호출별 고유 임시 디렉토리**(작업트리 밖)에 두고 끝나면 정리한다 —
    다중 모듈 루프의 세션 충돌(M-2)과 소비자 작업트리 잔여물을 동시에 없앤다.
    실패(init/exec 비정상 종료)는 예외로 전파 — 게이트 fail-open 금지(spec §8).
    """
    workdir = Path(workdir)
    session_dir = Path(tempfile.mkdtemp(prefix="probe-"))
    try:
        cfg_path = session_dir / "config.toml"
        session = session_dir / "session.sqlite"
        cfg_path.write_text(build_config(module_path, test_command), encoding="utf-8")
        runner(["init", str(cfg_path), str(session)], workdir)
        runner(["exec", str(cfg_path), str(session)], workdir)
        dump = runner(["dump", str(session)], workdir)
        return extract_survivors(dump)
    finally:
        shutil.rmtree(session_dir, ignore_errors=True)
