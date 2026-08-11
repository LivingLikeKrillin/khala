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


def test_a_not_gold_outside_the_pack_fails(labels):
    """판정의 음성 절반도 실재하는 문서를 가리켜야 한다 — 아니면 아무것도 판정하지 않은 것이다."""
    bad = copy.deepcopy(labels)
    _first_answerable(bad)["not_gold"] = ["concepts/does-not-exist.md"]
    assert any("팩에 없는 not_gold" in p for p in _check(bad))


def test_a_document_cannot_be_gold_and_not_gold_at_once(labels):
    bad = copy.deepcopy(labels)
    q = _first_answerable(bad)
    q["not_gold"] = list(q["gold"])
    assert any("gold 이자 not_gold" in p for p in _check(bad))


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


# ── 코퍼스가 디스크에 없을 때 (Pack B) ───────────────────────────────────────
#
# Pack B 는 테넌트 스냅샷이라 `docs/` 디렉터리가 없다. 게이트가 gold 를 파일 존재로만 검사하면
# Pack B 라벨은 **검사 자체가 불가능**해진다 — 규칙이 없는 것과 같다. 출처만 바꾸고 규칙은 같게.


def _manifest(tmp_path, docs):
    import json
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"docs": docs}, ensure_ascii=False), encoding="utf-8")
    return p


def test_a_manifest_pack_answers_the_same_two_questions(tmp_path):
    from scripts.ko_eval_labels import ManifestPack

    c = ManifestPack(_manifest(tmp_path, [{"key": "a.md", "title": "어떤 문서"}]))
    assert c.has("a.md") and not c.has("b.md")
    assert c.title("a.md") == "어떤 문서"
    assert c.title("b.md") is None


def test_a_gold_outside_the_manifest_is_rejected(tmp_path, labels):
    """디스크 팩에서 '팩에 없는 gold' 를 막던 규칙이 매니페스트에서도 살아 있어야 한다."""
    import copy

    from scripts.ko_eval_labels import ManifestPack, check

    bad = copy.deepcopy(labels)
    q = _first_answerable(bad)
    q["gold"] = ["not-in-the-manifest.md"]
    corpus = ManifestPack(_manifest(tmp_path, [{"key": "a.md", "title": "t"}]))
    assert any("팩에 없는 gold" in p for p in check(bad, corpus))


def test_the_title_copying_ban_still_applies_through_a_manifest(tmp_path, labels):
    """제목 베끼기 금지가 코퍼스 종류에 따라 갈리면, 한쪽 팩만 조여진다."""
    import copy

    from scripts.ko_eval_labels import ManifestPack, check

    bad = copy.deepcopy(labels)
    q = _first_answerable(bad)
    q["gold"] = ["a.md"]
    q["query"] = "긴 제목을 그대로 품은 질의"
    corpus = ManifestPack(_manifest(tmp_path, [{"key": "a.md", "title": "긴 제목을 그대로 품은"}]))
    assert any("제목을 그대로 품고" in p for p in check(bad, corpus))


# ── 서명은 리비전에 묶인다 ───────────────────────────────────────────────────
#
# 예전 게이트는 `reviewed_by` 가 있으면 통과시켰다. 검토가 끝난 **뒤** 판단 재료가 한 줄 더 붙어도
# 아무것도 안 막았다. 2026-08-08 에 실제로 그럴 뻔했다 — 서명 뒤에 `must_contain`(이 답에 이 사실이
# 있어야 한다)을 40건에 추가했다.


def test_a_review_signed_at_an_older_revision_no_longer_counts(labels):
    import copy
    bad = copy.deepcopy(labels)
    bad["revision"] = (bad["revision"] or 1) + 1        # 판단 재료가 바뀌었다는 뜻
    problems = _check(bad)
    assert any("검토 리비전" in p for p in problems), "서명 이후 변경이 그대로 통과했다"


def test_a_review_at_the_current_revision_passes(labels):
    """반대 방향 — 리비전이 맞으면 막으면 안 된다. 아니면 아무도 이 게이트를 못 넘는다."""
    assert not any("검토 리비전" in p for p in _check(labels))


def test_the_revision_check_only_applies_to_agent_authored_labels(labels):
    """사람이 직접 쓴 라벨에는 검토자가 따로 필요 없고, 리비전 묶기도 해당 없다."""
    import copy
    human = copy.deepcopy(labels)
    human["revision"] = (human["revision"] or 1) + 1
    for q in human["queries"]:
        q["authored_by"] = "LivingLikeKrillin"
        q.pop("reviewed_by", None)
        q.pop("reviewed_revision", None)
    assert not any("검토 리비전" in p or "reviewed_by 가 없다" in p for p in _check(human))
