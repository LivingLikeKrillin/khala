"""Vendored content_hash — byte-identical to specledger.hashing.content_hash.

Vendored (not imported) to avoid cross-module path coupling in the monorepo;
tests/test_hashing_parity.py asserts byte-identical output to specledger to
catch drift.
"""

import hashlib


def _normalize(body: str) -> str:
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.split("\n")]
    return "\n".join(lines).strip("\n")


def content_hash(body: str) -> str:
    digest = hashlib.sha256(_normalize(body).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
