"""얼린 팩에 문서를 **더하는** 것과 다시 **얼리는** 것은 다른 일이다.

⛔ 왜 이 검사가 있나 (2026-09-03). `freeze` 는 스냅샷 테넌트를 지우고 다시 만든다 — 두 시점이
한 테넌트에 섞이는 것을 막는 옳은 설계다. 그런데 새 gold 문서 하나를 팩에 넣으려고 그것을
부르면, 이미 얼린 문서 전부의 본문이 함께 지금 것으로 바뀐다. 그 본문은 재서명 워크시트가
*"무엇이 달라졌나"* 를 보여 주는 유일한 재료다(`OPEN.md` A55). 하나를 더하려다 남이 서명할
근거를 지우게 된다.
"""

from __future__ import annotations

from scripts.ko_eval_packb import extended_manifest, extension_problems

LIVE = {"a.md": {}, "b.md": {}, "c.md": {}}
FROZEN = {"a.md": {}}


def test_a_new_document_can_be_added():
    assert extension_problems(["b.md"], LIVE, FROZEN) == []


def test_a_document_missing_from_live_is_refused():
    """라이브에 없는 것을 더하면 팩이 없는 문서를 가리킨다."""
    got = extension_problems(["z.md"], LIVE, FROZEN)
    assert got and "라이브" in got[0]


def test_an_already_frozen_document_is_refused_not_refreshed():
    """⛔ 이게 이 명령의 존재 이유다 — 조용히 갱신하면 남의 서명 근거가 사라진다."""
    got = extension_problems(["a.md"], LIVE, FROZEN)
    assert got and "이미 얼려 있다" in got[0]


def test_the_refusal_names_what_must_happen_first():
    """거부 문구가 처방을 담아야 한다 — 담지 않으면 다음 사람이 freeze 를 부른다."""
    assert "재서명" in extension_problems(["a.md"], LIVE, FROZEN)[0]


def test_every_bad_key_is_named_not_just_the_first():
    got = extension_problems(["z.md", "a.md", "b.md"], LIVE, FROZEN)
    assert len(got) == 2 and any("z.md" in g for g in got) and any("a.md" in g for g in got)


# ── 매니페스트 ───────────────────────────────────────────────────────────────

OLD = {"pack": "packb-2026-08-07", "frozen_at": "2026-08-07T00:00:00+00:00",
       "documents": 1, "chunks": 3,
       "docs": [{"key": "a.md", "chunks": 3, "body_chars": 100}]}
ADD = [{"key": "b.md", "chunks": 5, "body_chars": 200}]


def test_counts_are_recomputed_not_incremented():
    m = extended_manifest(OLD, ADD, "2026-09-03T00:00:00+00:00")
    assert m["documents"] == 2 and m["chunks"] == 8


def test_frozen_at_is_not_touched():
    """그날 얼린 것은 그날 얼린 것이다 — 더했다고 팩의 나이를 젊게 적지 않는다."""
    m = extended_manifest(OLD, ADD, "2026-09-03T00:00:00+00:00")
    assert m["frozen_at"] == OLD["frozen_at"]
    assert m["extended_at"] == "2026-09-03T00:00:00+00:00"


def test_the_existing_documents_survive_in_order():
    m = extended_manifest(OLD, ADD, "2026-09-03T00:00:00+00:00")
    assert [d["key"] for d in m["docs"]] == ["a.md", "b.md"]


def test_unrelated_manifest_fields_are_carried_over():
    """`note`·`source_tenant` 같은 칸을 떨어뜨리면 팩이 자기 유래를 잃는다."""
    assert extended_manifest(OLD, ADD, "x")["pack"] == "packb-2026-08-07"
