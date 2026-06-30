import pytest

from ken.registry import register, load_manifest, current_hash, _artifact_id


def test_register_adds_entry_and_is_idempotent(tmp_path):
    man = tmp_path / "m.yaml"
    art = tmp_path / "a.md"
    art.write_text("hello\n", encoding="utf-8")
    register(str(art), manifest_path=man)
    register(str(art), manifest_path=man)  # idempotent on path
    entries = load_manifest(man)
    assert len(entries) == 1 and entries[0].path == str(art)


def test_current_hash_matches_content(tmp_path):
    art = tmp_path / "a.md"
    art.write_text("hello\n", encoding="utf-8")
    from ken.hashing import content_hash

    assert current_hash(str(art)) == content_hash("hello\n")


def test_root_mode_stores_relative_and_resolves_absolute(tmp_path):
    art = tmp_path / "sub" / "a.md"
    art.parent.mkdir(parents=True)
    art.write_text("hello\n", encoding="utf-8")
    man = tmp_path / "ken.manifest.yaml"

    ref = register(str(art), manifest_path=man, root=tmp_path)
    assert ref.path == str(art)  # returned path is absolute (resolved)

    import yaml
    raw = yaml.safe_load(man.read_text(encoding="utf-8"))
    assert raw[0]["path"] == "sub/a.md"  # stored relative POSIX

    entries = load_manifest(man, root=tmp_path)
    assert entries[0].path == str(art) and entries[0].content_hash  # resolved + live hash


def test_root_mode_collapses_path_spelling_to_one_id(tmp_path, monkeypatch):
    art = tmp_path / "a.md"
    art.write_text("x\n", encoding="utf-8")
    man = tmp_path / "ken.manifest.yaml"
    monkeypatch.chdir(tmp_path)  # so Path("./a.md").resolve() == tmp_path/a.md

    r_abs = register(str(art), manifest_path=man, root=tmp_path)
    r_dot = register("./a.md", manifest_path=man, root=tmp_path)  # run-from-root spelling
    assert r_abs.artifact_id == r_dot.artifact_id == _artifact_id("a.md")
    assert len(load_manifest(man, root=tmp_path)) == 1  # one entry, not two


def test_root_mode_rejects_outside_root(tmp_path):
    outside = tmp_path / "out.md"
    outside.write_text("x\n", encoding="utf-8")
    root = tmp_path / "proj"
    root.mkdir()
    man = root / "ken.manifest.yaml"
    with pytest.raises(ValueError, match="outside the ken root"):
        register(str(outside), manifest_path=man, root=root)
