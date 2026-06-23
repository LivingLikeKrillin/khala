from ken.registry import register, load_manifest, current_hash


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
