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
    """내부 문서다. 다른 조직의 정책 문서이기까지 하다 — 리포는 public 이다."""
    assert LOCAL_DIR.name == "local"
    assert MANIFEST.parent == LOCAL_DIR
    gitignore = (LOCAL_DIR.parents[3] / ".gitignore").read_text(encoding="utf-8")
    assert "nexus/tests/eval/local/" in gitignore, \
        "Pack B 가 커밋될 수 있는 상태다 — 내부 문서가 public 리포로 나간다"


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
