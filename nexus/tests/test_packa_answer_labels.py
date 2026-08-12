"""Pack A 답변 라벨 — 커밋된 자가 스스로 성립하는지 지킨다.

이 파일이 존재하는 이유는 `answer-labels.yaml` 이 **리포에 들어간 첫 답변 라벨**이기 때문이다.
Pack B 라벨은 gitignore 라 CI 가 볼 수 없고, 그래서 지금까지 "요구가 gold 본문에서 성립한다" 는
사람이 한 번 확인하고 기억하는 사실이었다. 여기서는 검사가 그 자리를 대신한다 — 요구를 고치는
사람은 그 요구가 여전히 문서에서 성립함을 같이 증명해야 한다.

**대조군을 함께 건다.** 요구가 무엇에 대해서도 통과한다면 검사는 아무것도 재지 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ko_eval_answer_quality import facts_present  # noqa: E402
from scripts.ko_eval_labels import DiskPack, answerable, check, load  # noqa: E402
from scripts.ko_eval_pack import DEFAULT_PACK_DIR  # noqa: E402

LABELS = ROOT / "tests" / "eval" / "ko" / "answer-labels.yaml"
DOCS = DEFAULT_PACK_DIR / "docs"


@pytest.fixture(scope="module")
def labels():
    return load(LABELS)


def _body(q) -> str:
    return "\n".join((DOCS / g).read_text(encoding="utf-8") for g in q["gold"])


def test_the_label_file_passes_its_own_gate(labels):
    assert check(labels, DiskPack(DEFAULT_PACK_DIR)) == []


def test_every_answerable_query_says_what_the_answer_must_contain(labels):
    """`must_contain` 이 없으면 `has_facts` 가 잴 것이 없다 — 검색 라벨과 같아진다."""
    missing = [q["id"] for q in answerable(labels) if not q.get("must_contain")]
    assert missing == []


def test_every_requirement_holds_in_its_own_gold_document(labels):
    """문서가 담지 않은 것을 요구하는 라벨은 첫 실행부터 거짓말하는 자다."""
    broken = []
    for q in answerable(labels):
        ok = facts_present(q["must_contain"], _body(q))
        broken += [(q["id"], " | ".join(g)) for g, o in zip(q["must_contain"], ok) if not o]
    assert broken == []


def test_the_requirements_do_not_pass_against_the_wrong_document(labels):
    """대조군 — 옆 질의의 gold 에 대면 떨어져야 한다. 안 떨어지면 이 검사는 눈금이 없다."""
    qs = [q for q in answerable(labels) if q["gold"]]
    survived = []
    for i, q in enumerate(qs):
        other = qs[(i + 1) % len(qs)]
        if set(q["gold"]) & set(other["gold"]):
            continue                      # 같은 문서를 공유하면 대조가 성립하지 않는다
        if all(facts_present(q["must_contain"], _body(other))):
            survived.append((q["id"], other["id"]))
    # 어휘가 겹치는 쿠버네티스 문서들이라 일부는 통과할 수 있다. 대다수가 통과하면 눈금이 없는 것.
    assert len(survived) <= len(qs) // 4, f"요구가 남의 문서에서도 통과한다: {survived}"


def test_the_controls_have_no_gold_and_no_requirement(labels):
    """답변불가 라벨은 **거절했는가** 하나만 본다. 요구를 달면 거절이 실패로 세어진다."""
    for q in labels["queries"]:
        if not q.get("answerable"):
            assert not q["gold"]
            assert not q.get("must_contain")


def test_no_query_here_came_from_a_real_user(labels):
    """천장의 조건은 "전부 authored_from_doc" 이 아니라 **"from_user_query 가 없다"** 이다.

    이 파일에는 `adjudicated` 가 20건 있다 — 판정 과정에서 고쳐 박은 질의들이고, 고쳐졌을 뿐
    여전히 문서를 보고 지은 것이라 천장은 그대로다. 첫 단언은 그 구분을 몰라서 틀렸고,
    파일이 아니라 단언이 고쳐졌다.

    실사용 질문이 섞여 들어오는 날 이 검사가 깨진다. 그때는 깨지는 것이 맞다 — 두 모집단이
    한 파일에 있다는 사실을 사람이 보고 결정해야 한다(SPEC-nexus-query-text-retention §4).
    """
    from scripts.ko_eval_labels import PROVENANCE

    seen = {q["provenance"] for q in labels["queries"]}
    assert seen <= set(PROVENANCE)
    assert "from_user_query" not in seen


# ── 커밋된 두 아티팩트가 서로 맞는가 ──────────────────────────────────────────
#
# 라벨과 매니페스트가 **둘 다 리포에 있다**. 그래서 "서명된 본문" 과 "얼린 본문" 이 같은지는
# DB 없이, CI 에서, 누구나 확인할 수 있다 — Pack B 에서는 원리적으로 불가능했던 검사다.

MANIFEST = ROOT / "tests" / "eval" / "ko" / "answer-manifest.json"


@pytest.fixture(scope="module")
def manifest():
    import json
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_the_binding_matches_the_frozen_manifest(labels, manifest):
    """서명한 해시와 매니페스트의 해시가 다르면, 둘 중 하나는 이미 다른 코퍼스를 말하고 있다."""
    frozen = {d["key"]: d["body_sha256"] for d in manifest["docs"]}
    signed = labels["corpus"]["bodies"]
    mismatched = [k for k, v in signed.items()
                  if frozen.get(k) != v.removeprefix("sha256:")]
    assert mismatched == []


def test_every_judged_document_is_bound(labels):
    """gold 인데 결속에 없으면, 그 문서는 바뀌어도 아무도 모른다."""
    from scripts.ko_eval_labels import judged_keys

    signed = set(labels["corpus"]["bodies"])
    judged = {k for q in answerable(labels) for k in judged_keys(q)}
    assert judged - signed == set()


def test_the_binding_names_the_tenant_it_was_signed_against(labels):
    """다른 테넌트의 해시는 이 라벨에 대해 아무것도 말하지 않는다 — 실행이 거부해야 한다."""
    assert labels["corpus"]["tenant"] == "ko_eval_packa"


def test_the_manifest_covers_the_whole_pack_not_just_the_gold(manifest):
    """경쟁 문서가 빠지면 `cites_gold` 와 미판정 판정이 쉬워진다 — 재는 대상이 바뀐다."""
    assert manifest["documents"] > 200


# ── CI 가 실제로 덮는 범위 ────────────────────────────────────────────────────
#
# 답변 하니스는 CI 에서 못 돈다: 임베딩 사이드카(KURE, CPU 로 시간당 500청크)와 LLM 이 필요하다.
# CI 가 도는 것은 **키워드 다리 회귀**(`test_ko_eval_run_db.py`, mecab 강제)이고, 그것은
# `labels.yaml` 을 읽는다. 답변 라벨은 별도 파일이다.
#
# 그래서 두 파일이 어긋나는 순간 CI 의 바닥값은 답변 세트가 재는 것을 더 이상 안 덮는다 —
# 그리고 답변 하니스가 CI 에 없으니 **아무도 모른다**. 그 침묵을 이 검사가 깬다.

RETRIEVAL_LABELS = ROOT / "tests" / "eval" / "ko" / "labels.yaml"


@pytest.fixture(scope="module")
def retrieval_labels():
    from scripts.ko_eval_labels import load
    return load(RETRIEVAL_LABELS)


def test_the_answer_set_inherits_the_retrieval_set(labels, retrieval_labels):
    """질의·gold·층이 검색 라벨과 같아야 CI 의 키워드 바닥값이 이 세트를 덮는다."""
    a = {q["id"]: q for q in retrieval_labels["queries"]}
    b = {q["id"]: q for q in labels["queries"]}
    assert set(a) == set(b), "질의 id 가 갈라졌다 — 한쪽에만 있는 질의는 CI 가 못 본다"
    for qid in sorted(a):
        assert a[qid]["query"] == b[qid]["query"], f"{qid}: 질의문이 갈라졌다"
        assert (a[qid].get("gold") or []) == (b[qid].get("gold") or []), f"{qid}: gold 가 갈라졌다"
        assert a[qid]["stratum"] == b[qid]["stratum"], f"{qid}: 층이 갈라졌다"
        assert a[qid]["answerable"] == b[qid]["answerable"], f"{qid}: 답변가능 여부가 갈라졌다"


def test_what_the_answer_set_adds_is_only_judgement(labels, retrieval_labels):
    """답변 라벨이 더하는 것은 **판단**뿐이다 — 요구·음성판정·결속. 질의 자체는 안 건드린다.

    이 경계가 무너지면 두 세트가 서로 다른 질문을 재면서 같은 이름으로 불리게 된다.
    """
    extra = set()
    for q in labels["queries"]:
        extra |= set(q) - set(next(x for x in retrieval_labels["queries"] if x["id"] == q["id"]))
    assert extra <= {"must_contain", "not_gold"}, f"예상 밖 필드: {extra}"
