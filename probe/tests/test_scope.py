from mutqa.scope import changed_source_modules


def test_filters_to_python_sources():
    diff_output = "src/pkg/a.py\nsrc/pkg/b.py\nREADME.md\n"
    mods = changed_source_modules(base="HEAD~1", run=lambda cmd: diff_output)
    assert mods == ["src/pkg/a.py", "src/pkg/b.py"]


def test_excludes_tests_and_dunder():
    diff_output = "src/pkg/a.py\ntests/test_a.py\nsrc/pkg/__init__.py\n"
    mods = changed_source_modules(base="HEAD~1", run=lambda cmd: diff_output)
    assert mods == ["src/pkg/a.py"]


def test_empty_diff_returns_empty():
    mods = changed_source_modules(base="HEAD~1", run=lambda cmd: "")
    assert mods == []
