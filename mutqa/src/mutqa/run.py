import subprocess
from pathlib import Path

from mutqa.extract import extract_survivors
from mutqa.models import Survivor

DEFAULT_TEST_COMMAND = "python -m pytest -q -x"


def build_config(module_path: str, test_command: str = DEFAULT_TEST_COMMAND) -> str:
    """단일 모듈 대상 cosmic-ray config(TOML 문자열) 생성.

    cosmic-ray는 module-path를 단일 경로로 받으므로 모듈별 1 config.
    """
    return (
        "[cosmic-ray]\n"
        f'module-path = "{module_path}"\n'
        "timeout = 30.0\n"
        "excluded-modules = []\n"
        f'test-command = "{test_command}"\n'
        "\n"
        "[cosmic-ray.distributor]\n"
        'name = "local"\n'
    )


def run_mutation(module_path: str, workdir: Path, test_command: str = DEFAULT_TEST_COMMAND) -> list[Survivor]:
    """단일 모듈에 cosmic-ray 전체 사이클 실행 → survivor 목록.

    실패(init/exec 비정상 종료)는 예외로 전파 — 게이트 fail-open 금지(spec §8).
    """
    workdir = Path(workdir)
    cfg_path = workdir / "mutqa.cfg.toml"
    session = workdir / "mutqa.sqlite"
    cfg_path.write_text(build_config(module_path, test_command))

    def cr(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["cosmic-ray", *args], cwd=workdir, capture_output=True, text=True, check=True
        )

    cr("init", str(cfg_path), str(session))
    cr("exec", str(cfg_path), str(session))
    dump = subprocess.run(
        ["cosmic-ray", "dump", str(session)],
        cwd=workdir, capture_output=True, text=True, check=True,
    )
    return extract_survivors(dump.stdout)
