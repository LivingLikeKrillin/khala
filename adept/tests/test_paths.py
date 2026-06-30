from khala.adept.paths import discover_root, MANIFEST_NAME


def test_finds_marker_in_start(tmp_path):
    (tmp_path / MANIFEST_NAME).write_text("[]", encoding="utf-8")
    assert discover_root(tmp_path) == tmp_path.resolve()


def test_finds_marker_in_ancestor(tmp_path):
    (tmp_path / MANIFEST_NAME).write_text("[]", encoding="utf-8")
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    assert discover_root(sub) == tmp_path.resolve()


def test_returns_none_when_absent(tmp_path):
    assert discover_root(tmp_path) is None
