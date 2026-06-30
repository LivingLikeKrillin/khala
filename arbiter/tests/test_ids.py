from khala.arbiter.ids import slugify, make_spec_id, next_adr_id


def test_slugify_lowercases_and_hyphenates():
    assert slugify("Virtual DJ Playlist") == "virtual-dj-playlist"


def test_slugify_strips_punctuation_and_collapses_hyphens():
    assert slugify("Auth!! (v2) -- final") == "auth-v2-final"


def test_slugify_keeps_korean():
    assert slugify("리뷰 게이트 설계") == "리뷰-게이트-설계"


def test_slugify_caps_at_56_chars():
    assert len(slugify("x" * 100)) == 56


def test_make_spec_id_basic(tmp_path):
    assert make_spec_id(tmp_path, "Virtual DJ Playlist") == "SPEC-virtual-dj-playlist"


def test_make_spec_id_collision_suffix(tmp_path):
    (tmp_path / "SPEC-auth.md").write_text("x", encoding="utf-8")
    assert make_spec_id(tmp_path, "auth") == "SPEC-auth-2"
    (tmp_path / "SPEC-auth-2.md").write_text("x", encoding="utf-8")
    assert make_spec_id(tmp_path, "auth") == "SPEC-auth-3"


def test_make_spec_id_explicit_slug(tmp_path):
    assert make_spec_id(tmp_path, "ignored title", slug="custom") == "SPEC-custom"


def test_next_adr_id_first(tmp_path):
    assert next_adr_id(tmp_path) == "ADR-0001"


def test_next_adr_id_increments(tmp_path):
    (tmp_path / "ADR-0001-foo.md").write_text("x", encoding="utf-8")
    (tmp_path / "ADR-0007-bar.md").write_text("x", encoding="utf-8")
    assert next_adr_id(tmp_path) == "ADR-0008"
