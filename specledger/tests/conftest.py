import pytest


@pytest.fixture
def docs_root(tmp_path):
    """A temporary docs root with specs/ and adr/ subdirs."""
    (tmp_path / "specs").mkdir()
    (tmp_path / "adr").mkdir()
    (tmp_path / ".reviews").mkdir()
    return tmp_path
