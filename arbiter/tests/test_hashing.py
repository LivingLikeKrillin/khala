from khala.arbiter.hashing import content_hash


def test_hash_is_sha256_prefixed():
    h = content_hash("hello")
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64


def test_hash_ignores_line_ending_style():
    assert content_hash("a\r\nb") == content_hash("a\nb")


def test_hash_ignores_trailing_whitespace_per_line():
    assert content_hash("a   \nb\t\n") == content_hash("a\nb\n")


def test_hash_ignores_surrounding_blank_lines():
    assert content_hash("\n\nbody\n\n") == content_hash("body")


def test_hash_differs_on_real_change():
    assert content_hash("decision A") != content_hash("decision B")
