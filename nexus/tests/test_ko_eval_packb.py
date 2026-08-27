"""Pack B 동결·검증 (SPEC-nexus-korean-retrieval-eval §4.1).

§4.1 이 라이브 테넌트를 실격시킨 이유는 **움직이기 때문**이다. 그래서 Pack B 는 이름 붙인 시점의
스냅샷이어야 하고, **매니페스트가 검증되지 않는 실행은 결과가 아니다.**

여기서 측정하는 것은 "검증이 통과한다" 가 아니라 **"검증이 실패할 수 있다"** 이다. 통과만 확인하는
검사는 이 리포가 반복해서 잡아낸 무효 대조군이다.
"""

from __future__ import annotations

import json

import pytest

from scripts.ko_eval_packb import LOCAL_DIR, MANIFEST, SNAPSHOT_TENANT, _body_hash, _doc_key


def test_the_document_key_survives_a_change_of_tenant():
    """gold 는 문서를 가리켜야지 테넌트를 가리키면 안 된다 — 스냅샷은 테넌트가 다르다."""
    assert _doc_key("default:ext-notion-abc.md") == "ext-notion-abc.md"
    assert _doc_key("ko_eval_packb:ext-notion-abc.md") == "ext-notion-abc.md"
    assert _doc_key("no-colon.md") == "no-colon.md"


def test_the_body_hash_notices_a_changed_document():
    """이 해시가 곧 '얼렸다' 의 의미다. 안 바뀌면 얼린 것이 아니다."""
    base = _body_hash(["첫 청크", "둘째 청크"])
    assert base == _body_hash(["첫 청크", "둘째 청크"])
    assert base != _body_hash(["첫 청크", "둘째 청크 수정"])
    assert base != _body_hash(["첫 청크"]), "청크가 빠지면 다른 문서다"
    # 경계가 옮겨간 경우도 잡아야 한다 — 이어 붙이면 같아지는 해시는 쓸모없다
    assert base != _body_hash(["첫 청크둘째 청크"])


def test_chunk_order_is_part_of_the_frozen_identity():
    assert _body_hash(["a", "b"]) != _body_hash(["b", "a"])


def test_pack_b_lives_only_in_the_gitignored_local_directory():
    """내부 문서다. 다른 조직의 정책 문서이기까지 하다 — 리포는 public 이다.

    `.gitignore` 는 **위로 걸어 찾는다.** 고정 깊이(`parents[3]`)로 짚으면 리포를 다른 깊이에
    마운트했을 때(컨테이너는 nexus/ 를 /app 에 건다) 검사가 무너진다 — 유출을 막는 검사가
    환경 때문에 못 도는 것은 없는 검사와 같다.
    """
    assert LOCAL_DIR.name == "local"
    assert MANIFEST.parent == LOCAL_DIR

    for parent in LOCAL_DIR.parents:
        gi = parent / ".gitignore"
        if gi.exists() and "nexus/tests/eval/local/" in gi.read_text(encoding="utf-8"):
            return
        if (parent / ".git").exists():
            pytest.fail("Pack B 가 커밋될 수 있는 상태다 — 내부 문서가 public 리포로 나간다")
    # 체크아웃이 아니다(리포를 부분 마운트한 컨테이너 등). **규칙이 없는 것과 다르다** — 위에서
    # 리포 루트를 만났는데 규칙이 없으면 이미 실패했다.
    pytest.skip("체크아웃이 아니라 무시 규칙을 확인할 수 없다")


@pytest.mark.skipif(not MANIFEST.exists(), reason="Pack B 가 아직 얼려지지 않았다(로컬 전용)")
def test_the_frozen_manifest_is_self_consistent():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert m["snapshot_tenant"] == SNAPSHOT_TENANT
    assert m["documents"] == len(m["docs"])
    assert m["chunks"] == sum(d["chunks"] for d in m["docs"])
    assert len({d["key"] for d in m["docs"]}) == len(m["docs"]), "문서 키가 중복이면 gold 가 모호해진다"
    assert m["frozen_at"], "이름 붙인 시점이 없으면 얼린 것이 아니다"


@pytest.mark.skipif(not MANIFEST.exists(), reason="Pack B 가 아직 얼려지지 않았다(로컬 전용)")
def test_the_corpus_is_large_enough_for_the_window():
    """창이 상위 10문서다. 코퍼스가 그보다 크지 않으면 두 실험군이 바닥 위에 붙어 무승부만 쌓이고,
    판정 규칙이 '검정력 부족' 을 돌려준다 (KOREAN_SEARCH_QUALITY.md §6.1)."""
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    floor = 10 / m["documents"]
    assert floor <= 0.10, f"바닥값 {floor:.3f} — 이 코퍼스로는 토크나이저를 가릴 수 없다"


def test_the_manifest_records_what_each_document_weighs():
    """실질 판정을 매니페스트만으로 할 수 있어야 한다 — DB 없이도 재현되는 사실이어야 한다."""
    from scripts.ko_eval_packb import _manifest_doc

    doc = {"title": "t", "chunks": [("root", 0, "가" * 500), ("root", 1, "나" * 400)]}
    rec = _manifest_doc("k.md", doc)
    assert rec["body_chars"] == 900, "본문 길이가 없으면 실질 문서를 셀 수 없다"


@pytest.mark.skipif(not MANIFEST.exists(), reason="Pack B 가 아직 얼려지지 않았다(로컬 전용)")
def test_the_manifest_still_records_body_size():
    """본문 길이는 게이트가 아니지만 **코퍼스 구성**을 아는 유일한 길이다.

    2026-08-07 오전에 이것이 게이트였다("실질 문서 ≥ 60"). 그 60 은 측정해 보지 않고 만든 어림수였고,
    근거였던 "gold 가 19건뿐이면 무승부만 쌓인다" 는 같은 날 오후에 **라벨 없이 측정해서 반증됐다**
    (§6.3). 게이트는 순위가 갈리는 자리로 옮겼다. 수치는 남긴다 — 116문서 중 19건만 본문이 있다는
    사실은 게이트와 무관하게 알아야 한다.
    """
    from nexus.sources.corpus import PACK_B_SUBSTANTIVE_CHARS

    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert "body_chars" in m["docs"][0], "본문 길이가 없으면 코퍼스 구성을 못 본다"
    substantive = [d for d in m["docs"] if d["body_chars"] >= PACK_B_SUBSTANTIVE_CHARS]
    assert 0 <= len(substantive) <= m["documents"]


def test_the_gate_is_the_measured_disagreement_not_a_document_count():
    """게이트가 무엇을 측정하는지 못박는다.

    검정력을 예고하는 것은 문서 수가 아니라 **두 실험군의 순위가 갈리는 자리**다. 문서 수는 구하기
    쉬운 양이었고, 갈리는 자리는 한 번 더 물어야 나오는 양이었다 — §6.2 가 지적한 실수를 그
    처방에서 그대로 반복했다.
    """
    from scripts.ko_eval_packb import SHALLOW_MIN

    # 판정 규칙의 MIN_DISCORDANT 와 같은 수여야 한다. 필요조건이 최소 요구치보다 느슨하면
    # 게이트를 통과하고도 확실히 검정력 부족인 구간이 생긴다.
    from scripts.ko_eval_harness import MIN_DISCORDANT
    assert SHALLOW_MIN == MIN_DISCORDANT

    import nexus.sources.corpus as corpus
    assert not hasattr(corpus, "PACK_B_MIN_SUBSTANTIVE"), \
        "측정해 보지 않은 문서 수 문턱이 되살아났다 — §6.3 을 읽어라"


@pytest.mark.skipif(not (LOCAL_DIR / "packb-disagreement.json").exists(),
                    reason="탐침을 아직 안 돌렸다(로컬 전용)")
def test_the_recorded_probe_clears_the_bar():
    from scripts.ko_eval_packb import SHALLOW_MIN, _load_probe

    p = _load_probe()
    assert p["shallow"] >= SHALLOW_MIN, (
        f"상위 3위 안에서 갈리는 질의 {p['shallow']}건 — {SHALLOW_MIN}건이 필요하다. "
        "이 아래면 불일치쌍의 필요조건이 이미 안 선다")
