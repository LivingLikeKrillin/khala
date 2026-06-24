from __future__ import annotations

import hashlib

import pytest

from specledger.artifacts import Artifact
from specledger.ledger import Ledger
from specledger.promote import PromoteError, promote_external


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


def test_promote_rejects_unknown_type(tmp_path):
    with pytest.raises(PromoteError):
        promote_external(_led(tmp_path), _csf(), "PRD")  # PRD 는 specledger 어휘가 아님


def test_promote_rejects_csf_missing_provenance(tmp_path):
    csf = _csf()
    del csf["provenance"]["source_hash"]
    with pytest.raises(PromoteError):
        promote_external(_led(tmp_path), csf, "SPEC")
