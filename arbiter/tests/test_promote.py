from __future__ import annotations

import hashlib

import pytest

from khala.arbiter.artifacts import Artifact
from khala.arbiter.ledger import Ledger
from khala.arbiter.promote import PromoteError, promote_external


def _csf(body="# Payment\n\n결제 서비스 명세", tool="manifest", sid="p-1", title="Payment PRD"):
    return {
        "id": f"ext-{tool}-{sid}",
        "kind": "PRD",
        "title": title,
        "provenance": {
            "source_tool": tool,
            "source_id": sid,
            "source_url": "https://manifest.app/p-1",
            "source_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        },
        "body": body,
    }


def _led(tmp_path):
    return Ledger(tmp_path, now=lambda: "2026-06-24T00:00:00Z")


def test_promote_creates_draft_spec_with_body(tmp_path):
    led = _led(tmp_path)
    csf = _csf()
    out = promote_external(led, csf, "SPEC")

    assert out["status"] == "DRAFT"
    assert out["provenance_carried"] is True
    art = Artifact.load(led._resolve(out["artifact_id"]))
    assert "결제 서비스 명세" in art.body


def test_promote_preserves_provenance_in_frontmatter(tmp_path):
    led = _led(tmp_path)
    csf = _csf()
    out = promote_external(led, csf, "SPEC")
    art = Artifact.load(led._resolve(out["artifact_id"]))

    assert art.meta["source_tool"] == "manifest"
    assert art.meta["source_url"] == "https://manifest.app/p-1"
    assert art.meta["source_hash"] == csf["provenance"]["source_hash"]
    assert art.meta["promoted_from_source_hash"] == csf["provenance"]["source_hash"]


def test_promote_adr_returns_proposed_and_carries_provenance(tmp_path):
    # ADR 은 record() 에서 PROPOSED 로 시작한다(SPEC 은 DRAFT).
    # 공개 계약은 실제 상태를 대문자로 반환.
    led = _led(tmp_path)
    csf = _csf()
    out = promote_external(led, csf, "ADR")

    assert out["status"] == "PROPOSED"
    assert out["provenance_carried"] is True
    art = Artifact.load(led._resolve(out["artifact_id"]))
    assert art.meta["source_tool"] == "manifest"
    assert art.meta["promoted_from_source_hash"] == csf["provenance"]["source_hash"]


def test_promote_rejects_unknown_type(tmp_path):
    with pytest.raises(PromoteError):
        promote_external(_led(tmp_path), _csf(), "PRD")  # PRD 는 Arbiter 어휘가 아님


def test_promote_rejects_csf_missing_provenance(tmp_path):
    csf = _csf()
    del csf["provenance"]["source_hash"]
    with pytest.raises(PromoteError):
        promote_external(_led(tmp_path), csf, "SPEC")


def test_promote_rejects_source_hash_not_matching_body(tmp_path):
    # promote 는 CSF 를 인라인으로 받으므로 body↔source_hash 정합을 자체 보장한다(deposit 과 대칭).
    csf = _csf()
    csf["body"] = "tampered body"  # source_hash 는 원래 body 의 것 → 불일치
    with pytest.raises(PromoteError):
        promote_external(_led(tmp_path), csf, "SPEC")


def test_promote_rejects_id_not_matching_provenance(tmp_path):
    # spec §5.1: promote 도 §3 id 형식 규칙을 재검증해야 한다(deposit 과 대칭). deposit 으로는 절대
    # 들어올 수 없는 malformed-id CSF 가 promote 로는 통과하던 비대칭을 닫는다.
    csf = _csf()
    csf["id"] = "ext-wrong-id"  # ext-<tool>-<id> 와 불일치
    with pytest.raises(PromoteError):
        promote_external(_led(tmp_path), csf, "SPEC")


def test_promote_rejects_id_with_path_separator(tmp_path):
    # deposit 측 식별자 충돌 방어(path separator 거부)와 동일 규칙을 promote 에도 적용.
    csf = _csf(sid="a/x")
    with pytest.raises(PromoteError):
        promote_external(_led(tmp_path), csf, "SPEC")


def test_promote_design_axis_a_type_creates_draft(tmp_path):
    # 신규 축-A 타입 DESIGN → Arbiter spec 어휘 → DRAFT.
    out = promote_external(_led(tmp_path), _csf(), "DESIGN")
    assert out["status"] == "DRAFT"
    assert out["provenance_carried"] is True


def test_promote_rfc_axis_a_type_creates_draft(tmp_path):
    out = promote_external(_led(tmp_path), _csf(), "RFC")
    assert out["status"] == "DRAFT"


def test_promote_legacy_spec_token_still_works(tmp_path):
    # 레거시 CSF 토큰 SPEC 은 정규화(→DESIGN)되어 회귀 없이 DRAFT.
    out = promote_external(_led(tmp_path), _csf(), "SPEC")
    assert out["status"] == "DRAFT"


def test_promote_rejects_tracked_tier_type(tmp_path):
    # PRD 는 T2(추적) — 거버넌스 원장으로 승격 불가.
    with pytest.raises(PromoteError):
        promote_external(_led(tmp_path), _csf(), "PRD")


def test_promote_returns_type_guidance(tmp_path):
    out = promote_external(_led(tmp_path), _csf(), "ADR")
    assert "guidance" in out
    assert "supersede" in out["guidance"]   # ADR 가이드
    # 기존 키 회귀 없음
    assert out["status"] == "PROPOSED" and out["provenance_carried"] is True
