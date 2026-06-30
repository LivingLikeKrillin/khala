from khala.arbiter.config import ArbiterConfig


def test_defaults_when_missing(tmp_path):
    cfg = ArbiterConfig.load(tmp_path)
    assert cfg.allow_globs == ["docs/**", "tests/**"]
    assert cfg.exempt_paths == []
    assert cfg.nexus is None


def test_loads_yaml(tmp_path):
    d = tmp_path / ".specledger"
    d.mkdir()
    (d / "config.yaml").write_text(
        "exempt_paths: ['scripts/**']\nnexus: {url: 'http://x'}\n", encoding="utf-8")
    cfg = ArbiterConfig.load(tmp_path)
    assert cfg.exempt_paths == ["scripts/**"]
    assert cfg.nexus == {"url": "http://x"}
    assert cfg.allow_globs == ["docs/**", "tests/**"]
