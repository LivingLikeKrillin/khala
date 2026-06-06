import tomllib

from mutqa.run import build_config


def test_config_targets_given_module():
    cfg = build_config(module_path="src/specledger/review.py")
    parsed = tomllib.loads(cfg)
    assert parsed["cosmic-ray"]["module-path"] == "src/specledger/review.py"


def test_config_default_test_command():
    cfg = build_config(module_path="src/pkg/a.py")
    parsed = tomllib.loads(cfg)
    assert parsed["cosmic-ray"]["test-command"] == "python -m pytest -q -x"


def test_config_custom_test_command():
    cfg = build_config(module_path="src/pkg/a.py", test_command="pytest -q")
    assert tomllib.loads(cfg)["cosmic-ray"]["test-command"] == "pytest -q"
