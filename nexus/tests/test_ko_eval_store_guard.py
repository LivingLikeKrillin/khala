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


def test_clean_db_leaves_the_expensive_store_alone_by_default():
    """기본은 **보존**이다. 파괴가 opt-in 인 이유는 §5.3 을 뒤집은 근거와 같다.

    저장소는 두 팔 × 1906 청크이고 KURE 팔은 CPU sentence-transformers 라 시간이 든다.
    2026-08-05 에 이 픽스처를 검증하다가 정확히 그렇게 날렸다.
    """
    src = _clean_db_source()
    assert "ko_eval_embeddings" in src, "clean_db 가 평가 저장소를 언급조차 하지 않는다"
    assert "NEXUS_TRUNCATE_KO_EVAL_STORE" in src
    assert '== "1"' in src or "== '1'" in src, (
        "파괴가 opt-in 이 아니다 — 통합 테스트 한 번에 시간짜리 저장소가 사라진다")


def test_the_truncate_survives_a_database_without_the_table():
    """저장소 테이블은 마이그레이션이 아니라 하니스가 만든다 — 없는 DB 에서 죽으면 안 된다."""
    src = _clean_db_source()
    assert "to_regclass" in src, (
        "테이블 부재를 확인하지 않고 TRUNCATE 하면 새 데이터베이스에서 통합 테스트가 전부 깨진다")


def test_the_fold_refuses_an_orphaned_store_instead_of_scoring_zero():
    """보존이 기본이면 저장소는 고아로 남는다. 그 상태를 0 점이 아니라 **중단**으로 만든다."""
    from scripts.ko_eval_harness import OrphanedStoreError, collapse_to_documents

    with pytest.raises(OrphanedStoreError):
        collapse_to_documents([("chunk_a", 1), ("chunk_b", 2)], {})
    with pytest.raises(OrphanedStoreError):
        collapse_to_documents([("chunk_a", 1)], {"chunk_zzz": "doc.md"})
    # 정상 경로는 그대로여야 한다
    assert collapse_to_documents([("c1", 1), ("c2", 2)], {"c1": "a.md", "c2": "a.md"}) == ["a.md"]
    # 빈 결과(그냥 아무것도 못 찾은 질의)는 중단이 아니다
    assert collapse_to_documents([], {"c1": "a.md"}) == []


def test_ci_does_not_silently_enable_destruction():
    """CI 에서 파괴가 켜져 있으면 저장소는 사라지고 스위트는 초록이다."""
    assert os.getenv("NEXUS_TRUNCATE_KO_EVAL_STORE") != "1", (
        "파괴 플래그가 환경에 켜져 있다 — 의도한 것이 아니라면 끄고 돌려라")


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


# ── 게이트 프로비넌스 (I-001) ────────────────────────────────────────────────


def test_a_report_says_whether_it_was_produced_under_an_armed_gate(tmp_path, monkeypatch):
    """ADR-0009 §3(ii) 와 SPEC §0 이 같은 결함을 기록했다: 측정이 승인보다 먼저 이뤄지고 SPEC 이
    나중에 그 숫자를 인용한다. 게이트는 편집을 막지 측정을 막지 않으므로 **예방은 못 한다.**
    대신 리포트가 자기 출처를 달고 나오게 해 **인용하는 순간 보이게** 한다.
    """
    from scripts.ko_eval_harness import gate_provenance

    monkeypatch.delenv("ARBITER_ACTIVE_SPEC", raising=False)

    # 마커 디렉터리 자체가 없다 — '게이트 밖' 이 아니라 '확인 불가'
    assert gate_provenance(tmp_path)["active_spec"] == "unknown"

    # 디렉터리는 있는데 활성 spec 이 없다 — 게이트 밖
    (tmp_path / ".arbiter").mkdir()
    assert gate_provenance(tmp_path)["active_spec"] == "none"

    # 무장된 게이트 — 유일한 양성 신호
    (tmp_path / ".arbiter" / "active.json").write_text(
        '{"spec_id": "SPEC-x", "set_at": "t", "set_by": "agent"}', encoding="utf-8")
    assert gate_provenance(tmp_path)["active_spec"] == "SPEC-x"

    # 읽을 수 없는 마커는 '없음' 이 아니다
    (tmp_path / ".arbiter" / "active.json").write_text("{ broken", encoding="utf-8")
    assert gate_provenance(tmp_path)["active_spec"] == "unknown"


def test_the_declared_override_wins_and_is_labelled_as_declared(monkeypatch):
    """컨테이너에서 도는 실행은 리포를 못 보므로 선언값을 받는다 — 다만 **선언값이라고 적힌다.**"""
    from scripts.ko_eval_harness import gate_provenance

    monkeypatch.setenv("ARBITER_ACTIVE_SPEC", "SPEC-declared")
    got = gate_provenance()
    assert got["active_spec"] == "SPEC-declared"
    assert "선언" in got["source"]


def test_every_rendered_report_carries_the_gate_line():
    """빠뜨릴 수 없게 `render_report` 안에서 붙인다 — 호출자가 meta 에 넣기를 기대하지 않는다."""
    from scripts.ko_eval_harness import LegResult, render_report

    body = render_report({"팩": "ko-k8s"}, [LegResult(leg="keyword")], {})
    assert "**게이트**:" in body
