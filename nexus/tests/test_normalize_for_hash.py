"""normalize_for_hash: 변경감지 해시용 지터제거(의미보존) 순수 정규화. 스펙 ⑥/§5.1."""
from nexus.ingest.normalize import normalize_for_hash


def test_crlf_and_cr_become_lf():
    assert normalize_for_hash("a\r\nb\rc") == "a\nb\nc\n"


def test_trailing_whitespace_stripped_per_line():
    assert normalize_for_hash("a  \nb\t\n") == "a\nb\n"


def test_trailing_blank_lines_collapsed_to_single_newline():
    assert normalize_for_hash("a\n\n\n") == "a\n"
    assert normalize_for_hash("a\nb") == "a\nb\n"


def test_empty_stays_empty():
    assert normalize_for_hash("") == ""
    assert normalize_for_hash("\n\n") == ""


def test_jitter_variants_collapse_equal_but_real_change_differs():
    base = "# 제목\n\n본문 한 줄\n"
    crlf = "# 제목\r\n\r\n본문 한 줄\r\n"
    trailing = "# 제목  \n\n본문 한 줄\n\n\n"
    assert normalize_for_hash(base) == normalize_for_hash(crlf) == normalize_for_hash(trailing)
    assert normalize_for_hash(base) != normalize_for_hash("# 제목\n\n본문 두 줄\n")
