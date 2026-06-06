from specledger.config import SpecledgerConfig


def test_defaults_when_missing(tmp_path):
    cfg = SpecledgerConfig.load(tmp_path)
    assert cfg.allow_globs == ["docs/**", "tests/**"]
    assert cfg.exempt_paths == []
    assert cfg.khala is None


def test_loads_yaml(tmp_path):
    d = tmp_path / ".specledger"
    d.mkdir()
    (d / "config.yaml").write_text(
        "exempt_paths: ['scripts/**']\nkhala: {url: 'http://x'}\n", encoding="utf-8")
    cfg = SpecledgerConfig.load(tmp_path)
    assert cfg.exempt_paths == ["scripts/**"]
    assert cfg.khala == {"url": "http://x"}
    assert cfg.allow_globs == ["docs/**", "tests/**"]
