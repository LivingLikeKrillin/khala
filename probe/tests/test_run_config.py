import tomllib

from khala.probe.run import build_config


def test_config_targets_given_module():
    cfg = build_config(module_path="src/khala/arbiter/review.py")
    parsed = tomllib.loads(cfg)
    assert parsed["cosmic-ray"]["module-path"] == "src/khala/arbiter/review.py"


def test_config_default_test_command():
    cfg = build_config(module_path="src/pkg/a.py")
    parsed = tomllib.loads(cfg)
    assert parsed["cosmic-ray"]["test-command"] == "python -m pytest -q -x"


def test_config_custom_test_command():
    cfg = build_config(module_path="src/pkg/a.py", test_command="pytest -q")
    assert tomllib.loads(cfg)["cosmic-ray"]["test-command"] == "pytest -q"


def test_config_escapes_backslashes_in_path():
    # Windows 네이티브 경로(역슬래시)가 TOML 이스케이프를 깨지 않고 원값으로 라운드트립.
    cfg = build_config(module_path=r"src\pkg\review.py")
    assert tomllib.loads(cfg)["cosmic-ray"]["module-path"] == r"src\pkg\review.py"


def test_config_escapes_quotes_in_test_command():
    cfg = build_config(module_path="a.py", test_command='pytest -k "my test"')
    assert tomllib.loads(cfg)["cosmic-ray"]["test-command"] == 'pytest -k "my test"'
