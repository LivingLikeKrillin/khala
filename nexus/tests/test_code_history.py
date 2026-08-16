"""미해소 후보 분류 — 왜 없는지가 처분을 가른다 (nexus/index/history.py).

⚠ 픽스처 Java 는 전부 여기서 지어낸 것이다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from nexus.index.history import (
    DELETED,
    EXTERNAL,
    NEVER_EXISTED,
    classify,
    deletion_map,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "Keeper.java").write_text("class Keeper {}\n", encoding="utf-8")
    (tmp_path / "Goner.java").write_text("class Goner {}\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "first")
    (tmp_path / "Goner.java").unlink()
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "refactor: consolidate services")
    return tmp_path


def test_deletion_map_finds_the_removal_with_its_reason(repo: Path):
    """'없어졌다' 만으로는 처분이 안 된다. 언제·왜 까지 있어야 요청이 된다."""
    m = deletion_map(repo)

    assert "Goner" in m
    assert m["Goner"].subject == "refactor: consolidate services"
    assert m["Goner"].date
    assert m["Goner"].path.endswith("Goner.java")


def test_a_file_that_still_exists_is_not_in_the_map(repo: Path):
    assert "Keeper" not in deletion_map(repo)


def test_non_source_deletions_are_ignored(tmp_path: Path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "notes.md").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "add")
    (tmp_path / "notes.md").unlink()
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "drop")

    assert deletion_map(tmp_path) == {}


def test_outside_a_git_repo_returns_empty_rather_than_raising(tmp_path: Path):
    assert deletion_map(tmp_path) == {}


# ---------------------------------------------------------------- 분류

def test_external_types_are_not_called_missing(repo: Path):
    """프레임워크 클래스를 '사라졌다' 고 올리면 받는 쪽이 목록 전체를 신뢰하지 않는다."""
    v = classify(["ApplicationEventPublisher"],
                 imported=frozenset({"ApplicationEventPublisher"}),
                 deletions=deletion_map(repo))

    assert v[0].kind == EXTERNAL
    assert "문서 잘못이 아니다" in v[0].explain()


def test_a_deleted_symbol_is_drift_and_carries_its_commit(repo: Path):
    v = classify(["Goner"], imported=frozenset(), deletions=deletion_map(repo))

    assert v[0].kind == DELETED
    assert "refactor: consolidate services" in v[0].explain()


def test_a_name_with_no_history_may_simply_be_unbuilt(repo: Path):
    """설계 문서가 아직 만들지 않은 것을 서술하는 것은 드리프트가 아니다."""
    v = classify(["NotYetBuilt"], imported=frozenset(), deletions=deletion_map(repo))

    assert v[0].kind == NEVER_EXISTED


def test_external_wins_over_a_coincidental_old_deletion(repo: Path):
    """같은 이름이 예전에 있었더라도, 문서가 부른 것은 import 하는 쪽일 가능성이 높다."""
    v = classify(["Goner"], imported=frozenset({"Goner"}), deletions=deletion_map(repo))

    assert v[0].kind == EXTERNAL
