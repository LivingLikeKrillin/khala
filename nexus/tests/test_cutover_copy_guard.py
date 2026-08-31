"""컷오버 스크립트가 **정본 없는 문서를 안 내리는가.**

⛔ **왜 이 검사가 있나.** 사본 122건을 일괄로 내리는 스크립트다. 술어가 사본 아닌 것을 하나라도
잡으면 **설계 문서가 영구 소실**된다(비평 I-003 — 정본 존재를 제목 일치로 판정하던 순환을 잡은
그 지적). 그래서 실행 전에 경로·해시·제목 셋을 다시 확인하고, 하나라도 어긋나면 멈춘다.

셋을 다 보는 이유는 **어느 하나도 신원이 아니기** 때문이다 — 제목은 우연히 같을 수 있고, 해시는
적재 경로가 다르면 갈리고, 경로는 이름이 바뀌면 끊긴다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "cutover_copy",
    Path(__file__).resolve().parents[1] / "scripts" / "cutover_copy.py")
cut = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cut)


def _row(**kw):
    base = dict(rid="r", title="t", source_uri="default:docs/a.md",
                hash="h", hold=False, by_hash=True, by_title=True, by_path=True)
    base.update(kw)
    return base


def test_all_three_correspondences_pass_quietly():
    cut._refuse_unless_every_copy_has_its_source([_row(), _row(rid="r2")])


@pytest.mark.parametrize("missing", ["by_hash", "by_title", "by_path"])
def test_any_single_missing_correspondence_stops_everything(missing):
    """⛔ **하나만 어긋나도 멈춘다.** 두 개가 맞으니 괜찮다고 넘어가면, 그 하나가 바로
    '사본이 아닌 문서' 인 경우를 지나친다."""
    with pytest.raises(SystemExit) as e:
        cut._refuse_unless_every_copy_has_its_source([_row(), _row(rid="bad", **{missing: False})])
    assert "정본 대응에 실패" in str(e.value)


def test_the_refusal_names_how_many_failed():
    """운영자가 몇 건인지 알아야 손으로 볼지 술어를 고칠지 정한다."""
    rows = [_row(rid=f"r{i}", by_hash=False) for i in range(3)]
    with pytest.raises(SystemExit) as e:
        cut._refuse_unless_every_copy_has_its_source(rows)
    assert "3건" in str(e.value)


def test_the_predicate_lives_in_exactly_one_place():
    """⛔ 사본의 정의가 두 곳에 있으면 한쪽만 고쳐지고, 그때 지워지는 것은 문서다."""
    assert "^default:(docs|modules|repo)/" in cut.COPY_PREDICATE
    assert "tenant = 'default'" in cut.COPY_PREDICATE
