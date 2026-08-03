"""한국어 평가 라벨 게이트 (SPEC-nexus-korean-retrieval-eval §4.2, §6).

**자가 틀린 측정은 약한 측정이 아니라 허구다.** 그래서 여기 테스트는 라벨이 통과하는지만이
아니라, **각 게이트가 실제로 이빨을 갖는지**를 하나씩 깨뜨려 확인한다. 통과만 확인하는 게이트는
있으나 마나다.
"""

from __future__ import annotations

import copy

import pytest

from scripts.ko_eval_labels import DEFAULT_LABELS, PER_STRATUM, STRATA, answerable, check, load
from scripts.ko_eval_pack import DEFAULT_PACK_DIR


@pytest.fixture
def labels():
    return load(DEFAULT_LABELS)


def _check(labels):
    return check(labels, DEFAULT_PACK_DIR)


def _first_answerable(labels):
    return next(q for q in labels["queries"] if q["answerable"])


# ── 커밋된 라벨 ───────────────────────────────────────────────────────────────


def test_committed_labels_pass_every_gate(labels):
    assert _check(labels) == []


def test_adjudicated_records_are_marked_as_such(labels):
    """풀 판정으로 gold 가 늘어난 질의는 provenance 가 바뀐다 — 어떤 라벨이 어디서 왔는지 남는다."""
    adjudicated = [q for q in labels["queries"] if q["provenance"] == "adjudicated"]
    assert adjudicated, "풀 판정 기록이 없다"
    assert all(len(q["gold"]) >= 1 for q in adjudicated)


def test_the_working_set_is_forty_not_forty_five(labels):
    """§4.3 의 분모. 답변불가 5건은 어떤 집계에도 들어가지 않는다."""
    assert len(labels["queries"]) == 45
    assert len(answerable(labels)) == 40


def test_every_stratum_carries_exactly_eight(labels):
    for stratum in STRATA:
        assert sum(1 for q in answerable(labels) if q["stratum"] == stratum) == PER_STRATUM


def test_labels_declare_a_revision_and_a_pack(labels):
    """리비전은 바닥값이 어느 라벨판에 박혔는지를 말한다 — 풀 판정으로 gold 가 늘면 올라간다."""
    assert labels["revision"] == 2          # rev1 → rev2: mecab·nori 풀 판정으로 gold 24건 추가
    assert labels["pack"] == "ko-k8s-2026-08-01"


# ── 게이트마다 이빨이 있는가 ─────────────────────────────────────────────────


def test_an_expected_lexeme_field_cannot_be_smuggled_in(labels):
    """기존 스위트를 토크나이저 비교 불가로 만든 그 칸. 어느 깊이에서도 못 들어온다."""
    bad = copy.deepcopy(labels)
    _first_answerable(bad)["expected_lexeme"] = "식별"
    assert any("금지된 키" in p for p in _check(bad))

    nested = copy.deepcopy(labels)
    _first_answerable(nested)["notes"] = {"match_term": "식별"}
    assert any("금지된 키" in p for p in _check(nested))


def test_a_duplicate_id_fails(labels):
    bad = copy.deepcopy(labels)
    bad["queries"].append(copy.deepcopy(bad["queries"][0]))
    assert any("중복 id" in p for p in _check(bad))


def test_a_gold_path_that_is_not_in_the_pack_fails(labels):
    bad = copy.deepcopy(labels)
    _first_answerable(bad)["gold"] = ["concepts/does-not-exist.md"]
    assert any("팩에 없는 gold" in p for p in _check(bad))


def test_a_prefix_instead_of_a_path_fails(labels):
    """8자 접두사가 서로 다른 두 페이지에 걸려 정답을 '회귀' 로 적은 적이 있다."""
    bad = copy.deepcopy(labels)
    _first_answerable(bad)["gold"] = ["concepts/work"]
    assert any("팩 상대 경로" in p for p in _check(bad))


def test_a_query_that_restates_the_gold_title_fails(labels):
    bad = copy.deepcopy(labels)
    q = _first_answerable(bad)
    q["gold"] = ["concepts/services-networking/ingress-controllers.md"]
    q["query"] = "인그레스 컨트롤러 고르는 법"          # 제목을 그대로 품는다
    assert any("제목을 그대로" in p for p in _check(bad))


def test_a_short_title_is_not_policed(labels):
    """`파드`·`노드` 같은 짧은 제목까지 막으면 외래어·복합명사 층이 쓸 어휘가 없어진다."""
    ok = copy.deepcopy(labels)
    q = _first_answerable(ok)
    q["gold"] = ["concepts/architecture/nodes.md"]                 # 제목: '노드'
    q["query"] = "노드가 준비 상태가 아닐 때 무엇을 보나"
    assert not any("제목을 그대로" in p for p in _check(ok))


def test_an_agent_label_without_a_reviewer_fails(labels):
    bad = copy.deepcopy(labels)
    _first_answerable(bad)["reviewed_by"] = ""
    assert any("reviewed_by" in p for p in _check(bad))


def test_a_human_label_needs_no_reviewer(labels):
    ok = copy.deepcopy(labels)
    q = _first_answerable(ok)
    q["authored_by"] = "human"
    q["reviewed_by"] = ""
    assert _check(ok) == []


def test_an_unbalanced_stratum_fails(labels):
    bad = copy.deepcopy(labels)
    _first_answerable(bad)["stratum"] = "spacing"
    problems = _check(bad)
    assert any("정확히 8건" in p for p in problems)


def test_answerable_without_gold_fails(labels):
    bad = copy.deepcopy(labels)
    _first_answerable(bad)["gold"] = []
    assert any("gold 가 비었다" in p for p in _check(bad))


def test_unanswerable_with_gold_fails(labels):
    bad = copy.deepcopy(labels)
    q = next(q for q in bad["queries"] if not q["answerable"])
    q["gold"] = ["concepts/architecture/nodes.md"]
    assert any("gold 가 있다" in p for p in _check(bad))


def test_a_missing_required_field_fails(labels):
    bad = copy.deepcopy(labels)
    del _first_answerable(bad)["rationale"]
    assert any("필드 없음 — rationale" in p for p in _check(bad))


def test_a_missing_revision_fails(labels):
    bad = copy.deepcopy(labels)
    del bad["revision"]
    assert any("revision 없음" in p for p in _check(bad))
