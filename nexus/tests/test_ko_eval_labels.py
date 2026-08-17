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


# ── 라벨은 서명된 본문에 묶인다 (SPEC-nexus-answer-quality-ruler §3.3) ────────
#
# **이 게이트가 없어서 이틀치 판독이 만료된 라벨 위에 얹혀 있었다.** 옛 게이트는 gold 가
# 매니페스트에 *존재하는지*만 봤고, 실행은 라이브 테넌트를 쟀다. 그 사이 116문서 중 8건의 본문이
# 바뀌었고 — 그 8건이 답변가능 40건 중 21건의 gold 였다.


def _bound(labels, bodies=None):
    """검사용 라벨 사본에 corpus 결속 블록을 달아 준다."""
    import copy
    out = copy.deepcopy(labels)
    keys = {k for q in out["queries"] if q.get("answerable")
            for k in (list(q.get("gold") or []) + list(q.get("not_gold") or []))}
    out["corpus"] = {"tenant": "default", "signed_at": "2026-08-12",
                     "bodies": bodies if bodies is not None else {k: f"sha256:{k}" for k in keys}}
    return out


def test_a_gold_body_that_moved_expires_its_query(labels):
    from scripts.ko_eval_labels import expired

    bound = _bound(labels)
    live = dict(bound["corpus"]["bodies"])
    q = _first_answerable(bound)
    live[q["gold"][0]] = "sha256:다른 본문"
    assert expired(bound, live).get(q["id"]) == [q["gold"][0]]


def test_a_body_that_still_matches_does_not_expire(labels):
    from scripts.ko_eval_labels import expired

    bound = _bound(labels)
    assert expired(bound, dict(bound["corpus"]["bodies"])) == {}


def test_a_not_gold_body_that_moved_expires_too(labels):
    """판정의 음성 절반도 텍스트에 묶인다 — 안 그러면 기계가 그림에서 읽은 텍스트가 들어와
    답을 담게 된 문서가 영원히 not_gold 로 남는다."""
    from scripts.ko_eval_labels import expired

    import copy
    src = copy.deepcopy(labels)
    q = _first_answerable(src)
    other = next(o["gold"][0] for o in src["queries"]
                 if o.get("answerable") and o["gold"] and o["gold"][0] not in q["gold"])
    q["not_gold"] = [other]
    bound = _bound(src)
    live = dict(bound["corpus"]["bodies"])
    live[other] = "sha256:바뀐 본문"
    assert expired(bound, live).get(q["id"]) == [other]


def test_the_signed_form_in_the_spec_matches_what_the_run_computes(labels):
    """서명 파일은 `sha256:<hex>`, 실행이 넘기는 것은 맨 `<hex>` — 둘은 같은 값이어야 한다.

    **이 테스트가 없어서 자를 실제로 서명하는 순간 40질의가 전부 만료됐다.** 옛 테스트들은 서명
    쪽과 라이브 쪽을 같은 가짜 문자열로 만들어 비교해, 두 형식이 만나는 지점을 한 번도 재지
    않았다. 여기서는 양쪽을 **다른 형식으로** 준다.
    """
    from scripts.ko_eval_labels import expired

    hexes = {k: f"{i:064x}" for i, k in enumerate(
        {k for q in labels["queries"] if q.get("answerable") for k in (q.get("gold") or [])})}
    bound = _bound(labels, bodies={k: f"sha256:{v}" for k, v in hexes.items()})
    assert expired(bound, hexes) == {}

    # 이빨 확인: 형식을 넘어 **값**이 다르면 그 질의는 만료돼야 한다.
    q = _first_answerable(bound)
    moved = dict(hexes)
    moved[q["gold"][0]] = "f" * 64
    assert expired(bound, moved).get(q["id"]) == [q["gold"][0]]


def test_a_disappeared_document_expires_its_query(labels):
    from scripts.ko_eval_labels import expired

    bound = _bound(labels)
    live = dict(bound["corpus"]["bodies"])
    q = _first_answerable(bound)
    del live[q["gold"][0]]
    assert q["id"] in expired(bound, live)


def test_a_live_run_needs_the_labels_to_say_what_they_were_signed_against(labels):
    """테넌트를 재는 실행은 결속을 요구한다. 얼어 있는 디스크 팩(Pack A)은 매니페스트 해시
    가드가 같은 일을 하므로 요구하지 않는다 — 움직이는 것은 테넌트다."""
    unbound = check(labels, DEFAULT_PACK_DIR, require_corpus_binding=True)
    assert any("corpus.tenant 없음" in p for p in unbound)
    assert any("corpus.bodies 없음" in p for p in unbound)
    assert check(labels, DEFAULT_PACK_DIR) == [], "팩 경로 검사는 결속을 요구하면 안 된다"
    assert check(_bound(labels), DEFAULT_PACK_DIR, require_corpus_binding=True) == []


def test_a_judged_document_with_no_signed_hash_fails(labels):
    bound = _bound(labels)
    dropped = next(iter(bound["corpus"]["bodies"]))
    del bound["corpus"]["bodies"][dropped]
    assert any("서명된 본문 해시가 없다" in p
               for p in check(bound, DEFAULT_PACK_DIR, require_corpus_binding=True))


# ── 층 검사는 선언한 팩에만 (2026-08-18) ────────────────────────────────────
#
# 5층×8건 균형은 **한국어 형태소 비교 설계**의 규칙이다(SPEC-nexus-korean-embedding-comparison).
# 라이브 코퍼스의 답변 회귀용 라벨처럼 다른 목적의 자를 그 틀에 밀어 넣으면 `stratum` 이 뜻을
# 잃는다 — 없는 성질을 적어야 통과하기 때문이다. 그래서 **선언으로 켠다.**


def _pack(**over):
    q = {"id": "x1", "query": "질문", "stratum": "policy", "answerable": True,
         "gold": ["a.md"], "rationale": "왜", "must_contain": [["토큰"]],
         "provenance": "authored_from_doc", "authored_by": "agent",
         "reviewed_by": "사람", "reviewed_revision": 1}
    d = {"revision": 1, "pack": "p", "queries": [q]}
    d.update(over)
    return d


class _Corpus:
    def has(self, rel): return True
    def title(self, rel): return "제목"


def test_a_pack_without_the_declaration_is_not_held_to_the_strata_balance():
    problems = check(_pack(), _Corpus())

    assert not [p for p in problems if "층" in p], problems


def test_a_pack_that_declares_the_design_is_held_to_it():
    problems = check(_pack(strata_design="ko-morphology"), _Corpus())

    assert [p for p in problems if "층" in p], "선언했는데 균형 검사가 안 걸렸다"


def test_the_shipped_ko_packs_still_declare_it():
    """실수로 선언이 빠지면 그 팩의 균형 검사가 조용히 꺼진다 — 그게 이 검사의 이유다."""
    import pathlib

    import yaml

    for name in ("answer-labels.yaml", "labels.yaml"):
        p = pathlib.Path(__file__).resolve().parents[1] / "tests" / "eval" / "ko" / name
        assert yaml.safe_load(p.read_text(encoding="utf-8")).get("strata_design") == "ko-morphology", name
