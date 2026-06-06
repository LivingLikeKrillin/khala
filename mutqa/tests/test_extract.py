import pytest

from mutqa.extract import extract_survivors
from mutqa.models import Survivor


def test_extract_keeps_only_survivors(fixtures_dir):
    survivors = extract_survivors((fixtures_dir / "cr_dump_sample.jsonl").read_text())
    assert len(survivors) == 1  # killed 제외, 미실행(null) 제외


def test_survivor_fields_normalized(fixtures_dir):
    [s] = extract_survivors((fixtures_dir / "cr_dump_sample.jsonl").read_text())
    assert isinstance(s, Survivor)
    assert s.module == "src/specledger/review.py"
    assert s.lineno == 88                       # start_pos[0]
    assert s.operator == "core/ReplaceComparisonOperator_Lt_LtE"
    assert "for d in []:" in s.mutation_diff


def test_blank_lines_ignored(fixtures_dir):
    text = (fixtures_dir / "cr_dump_sample.jsonl").read_text() + "\n\n"
    assert len(extract_survivors(text)) == 1


def test_malformed_line_raises_clear_error():
    bad = '{"not": "a two-element array"}'
    with pytest.raises(ValueError) as exc:
        extract_survivors(bad)
    assert "Malformed" in str(exc.value)
