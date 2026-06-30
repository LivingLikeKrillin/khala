import pytest

from khala.probe.extract import extract_survivors
from khala.probe.models import Survivor


def test_extract_keeps_only_survivors(fixtures_dir):
    survivors = extract_survivors((fixtures_dir / "cr_dump_sample.jsonl").read_text())
    assert len(survivors) == 1  # killed 제외, 미실행(null) 제외


def test_survivor_fields_normalized(fixtures_dir):
    [s] = extract_survivors((fixtures_dir / "cr_dump_sample.jsonl").read_text())
    assert isinstance(s, Survivor)
    assert s.module == "src/khala/arbiter/review.py"
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


def test_module_path_separators_normalized():
    # cosmic-ray on Windows emits backslash module_path; key/module must be forward-slash
    line = (
        '[{"job_id":"x","mutations":[{"module_path":"src\\\\pkg\\\\review.py",'
        '"operator_name":"core/Op","occurrence":0,"start_pos":[5,0],"end_pos":[5,1],'
        '"operator_args":{},"definition_name":"f"}]},'
        '{"worker_outcome":"normal","output":"ok","test_outcome":"survived","diff":"d"}]'
    )
    [s] = extract_survivors(line)
    assert s.module == "src/pkg/review.py"
    assert s.key == "src/pkg/review.py:5:core/Op"
