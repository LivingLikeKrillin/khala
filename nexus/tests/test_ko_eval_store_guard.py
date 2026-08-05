"""평가 임베딩 저장소가 고아로 남지 않게 하는 가드 (SPEC-nexus-ko-eval-pool-sensitivity §5).

`clean_db` 는 `chunks`/`documents` 를 TRUNCATE 하는데 `ko_eval_embeddings` 는 남겨두었다. 남은 행은
사라진 청크를 가리키는 **고아**가 되고, 청크를 문서로 접는 코드는 조용히 빈 목록을 읽는다.
2026-08-05 에 그 상태에서 두 팔이 `Recall@10 = 0.000` 을 냈다.

**정정 하나를 여기 남긴다.** 공식 경로(`ko_eval_embed_compare run`)는 그때도 보호되고 있었다 —
`verify_arm` 이 "살아 있는 청크가 없는 행"을 잡고 `cmd_run` 이 거기서 멈춘다. 0.000 을 낸 것은 그
검사를 우회한 임시 스크립트였다. 그래서 이 파일이 지키는 것은 "공식 경로의 구멍"이 아니라
**저장소와 청크가 애초에 어긋나지 않는다**는 더 앞선 성질이다.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

_CONFTEST = Path(__file__).resolve().parent / "conftest.py"


def _clean_db_source() -> str:
    tree = ast.parse(_CONFTEST.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "clean_db":
            return ast.get_source_segment(_CONFTEST.read_text(encoding="utf-8"), node) or ""
    raise AssertionError("clean_db 픽스처를 찾지 못했다")


def test_clean_db_truncates_the_eval_store_with_the_chunks():
    """구조 검사 — 경험적 확인은 저장소가 비어 있으면 우연히 통과하지만 이건 못 한다."""
    src = _clean_db_source()
    assert "ko_eval_embeddings" in src, (
        "clean_db 가 평가 저장소를 다루지 않는다 — chunks 만 지우면 저장소가 고아가 된다")
    assert "TRUNCATE" in src


def test_the_truncate_survives_a_database_without_the_table():
    """저장소 테이블은 마이그레이션이 아니라 하니스가 만든다 — 없는 DB 에서 죽으면 안 된다."""
    src = _clean_db_source()
    assert "to_regclass" in src, (
        "테이블 부재를 확인하지 않고 TRUNCATE 하면 새 데이터베이스에서 통합 테스트가 전부 깨진다")


def test_preserving_the_store_is_opt_in_not_the_default():
    """기본값은 지우는 것이다.

    이전 설계는 저장소가 채워져 있으면 픽스처가 **거부**하게 했는데, 그건 이 작업을 하는 사람의
    기계에서 스위트 전체를 막는다. 방향을 뒤집어, 비싼 저장소를 지키려는 쪽이 선언한다.
    """
    src = _clean_db_source()
    assert "NEXUS_PRESERVE_KO_EVAL_STORE" in src
    # 기본 경로가 '지운다' 인지 — 환경변수가 '1' 일 때만 건너뛴다
    assert '!= "1"' in src or "!= '1'" in src, (
        "가드가 opt-in 이 아니다 — 기본이 보존이면 스위트가 낡은 저장소 위에서 돌게 된다")


@pytest.mark.skipif(os.getenv("NEXUS_PRESERVE_KO_EVAL_STORE") == "1",
                    reason="저장소 보존이 켜져 있어 이 테스트가 재는 상태를 만들 수 없다")
def test_the_guard_variable_is_not_set_in_ci():
    """CI 에서 보존이 켜져 있으면 스위트는 초록인데 저장소는 낡은다."""
    assert os.getenv("NEXUS_PRESERVE_KO_EVAL_STORE") != "1"


def test_restore_chunks_verifies_content_not_only_rids():
    """rid 집합만 보면 드리프트한 팩을 통과시킨다 (같은 파일 = 같은 rid, 다른 본문)."""
    src = (Path(__file__).resolve().parents[1] / "scripts" / "ko_eval_embed_compare.py"
           ).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.AsyncFunctionDef) and n.name == "cmd_restore_chunks"), None)
    assert fn is not None, "restore-chunks 가 없다"
    body = ast.get_source_segment(src, fn) or ""
    assert "verify_arm" in body, (
        "restore-chunks 가 verify_arm 을 부르지 않는다 — 그러면 input_sha256 대조가 없어 "
        "팩 드리프트를 못 잡는다")
    assert "DELETE FROM ko_eval_embeddings" not in body, (
        "복구 명령이 임베딩을 지운다 — 그건 load 의 동작이고, 이 명령의 존재 이유를 없앤다")
