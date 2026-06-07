from pathlib import Path

from khala.index.code_source import CodeValueResolver

FIX = Path(__file__).parent / "fixtures"


def test_reads_current_int_constant():
    res = CodeValueResolver(FIX).resolve("PlaylistPolicy.ASSOCIATE_MAX_PLAYLISTS")
    assert res.found and res.value == "5"
    assert res.symbol == "ASSOCIATE_MAX_PLAYLISTS"
    assert res.rel_path.endswith("PlaylistPolicy.java")
    assert res.symbol_hash


def test_tolerates_extra_whitespace():
    res = CodeValueResolver(FIX).resolve("PlaylistPolicy.TRACK_TIME_LIMIT_SECONDS")
    assert res.value == "360"


def test_hash_changes_with_value(tmp_path):
    f = tmp_path / "P.java"
    f.write_text("class P { public static final int X = 5; }")
    h1 = CodeValueResolver(tmp_path).resolve("P.X").symbol_hash
    f.write_text("class P { public static final int X = 10; }")
    h2 = CodeValueResolver(tmp_path).resolve("P.X").symbol_hash
    assert h1 != h2


def test_missing_symbol_not_found():
    assert CodeValueResolver(FIX).resolve("PlaylistPolicy.NOPE").found is False
