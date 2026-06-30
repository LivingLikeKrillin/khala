from __future__ import annotations

from khala.arbiter.guidelines import guidance_for


def test_guidance_for_known_types_carries_research_anchors():
    adr = guidance_for("ADR")
    assert "supersede" in adr and "불변" in adr
    rfc = guidance_for("RFC")
    assert "계층" in rfc or "substantial" in rfc
    pm = guidance_for("POSTMORTEM")
    assert "blameless" in pm or "비난" in pm


def test_guidance_for_normalizes_legacy_token():
    # 레거시 SPEC → DESIGN 가이드(doctypes.normalize_kind 재사용)
    assert guidance_for("SPEC") == guidance_for("DESIGN")


def test_guidance_for_includes_cross_cutting_footer():
    assert "owner" in guidance_for("NOTE")          # 공통 푸터(docs-as-code)


def test_guidance_for_unknown_returns_none():
    assert guidance_for("MYSTERY") is None
