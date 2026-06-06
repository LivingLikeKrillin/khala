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
        'name = "cosmic_ray.distribution.local.LocalDistributor"\n'
    )
