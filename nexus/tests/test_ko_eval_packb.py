"""Pack B 동결·검증 (SPEC-nexus-korean-retrieval-eval §4.1).

§4.1 이 라이브 테넌트를 실격시킨 이유는 **움직이기 때문**이다. 그래서 Pack B 는 이름 붙인 시점의
스냅샷이어야 하고, **매니페스트가 검증되지 않는 실행은 결과가 아니다.**

여기서 재는 것은 "검증이 통과한다" 가 아니라 **"검증이 실패할 수 있다"** 이다. 통과만 확인하는
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
    """창이 상위 10문서다. 코퍼스가 그보다 크지 않으면 두 팔이 바닥 위에 붙어 무승부만 쌓이고,
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
def test_enough_documents_can_actually_carry_a_query():
    """**바닥값과 다른 조건이다.** 짧은 문서도 창 경쟁에는 참가하므로 바닥값은 통과시키지만,
    본문이 없는 문서는 gold 가 못 된다.

    2026-08-07 에 이 구분이 없어서 걸렸다: 116문서 · 바닥값 0.086(통과)인데 본문 800자 이상은
    19건이었다. 40개 질의를 19개 문서에 걸면 층별 8건을 서로 다른 문서에서 뽑을 수 없고, 두
    토크나이저가 같은 소수 문서를 두고 겨뤄 무승부만 쌓인다 — 결과는 '검정력 부족' 이고 그것은
    ADR-0008 §5(b) 를 갚지 못한다.
    """
    from nexus.sources.corpus import PACK_B_MIN_SUBSTANTIVE, PACK_B_SUBSTANTIVE_CHARS

    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if "body_chars" not in m["docs"][0]:
        pytest.skip("매니페스트가 body_chars 이전 형식이다 — 다시 얼려라")
    substantive = [d for d in m["docs"] if d["body_chars"] >= PACK_B_SUBSTANTIVE_CHARS]
    assert len(substantive) >= PACK_B_MIN_SUBSTANTIVE, (
        f"gold 가 될 수 있는 문서 {len(substantive)}건 (본문 {PACK_B_SUBSTANTIVE_CHARS}자 이상) — "
        f"{PACK_B_MIN_SUBSTANTIVE}건이 필요하다. 라벨을 쓰기 전에 코퍼스를 키워라")
