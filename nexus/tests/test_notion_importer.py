from __future__ import annotations

import hashlib

from nexus.ingest.sources.base import ConvertedDoc
from nexus.ingest.sources.notion_importer import ImportReport, build_csf, import_notion


def _conv(body="# 제목\n\n본문", title="결제 기획", url="https://notion.so/p1"):
    return ConvertedDoc(
        page_id="p1", markdown=body,
        frontmatter={"title": title, "origin_url": url}, image_count=0,
    )


def test_build_csf_produces_deterministic_id_and_hash():
    csf = build_csf(_conv(), "p1")
    assert csf["id"] == "ext-notion-p1"
    assert csf["kind"] == "NOTE"
    assert csf["title"] == "결제 기획"
    prov = csf["provenance"]
    assert prov["source_tool"] == "notion"
    assert prov["source_id"] == "p1"
    assert prov["source_url"] == "https://notion.so/p1"
    assert prov["source_hash"] == hashlib.sha256(csf["body"].encode("utf-8")).hexdigest()


def test_build_csf_passes_server_side_validation():
    # importer 구성 CSF는 S3 서버측 검증을 통과하는 형태여야 한다(대칭).
    from nexus.a2a.external_ingest_skill import validate_external_spec
    assert validate_external_spec(build_csf(_conv(), "p1")) is None


class _FakeSource:
    def __init__(self, ids, convs):
        self._ids, self._convs = ids, convs

    def live_ids(self):
        return set(self._ids)

    def page_ref(self, pid):
        return type("R", (), {"id": pid, "url": f"u/{pid}", "last_edited": "t"})()

    def fetch_markdown(self, ref):
        return self._convs[ref.id]


class _Outcome:
    def __init__(self, rid, idempotent=False):
        self.resource_rid, self.idempotent_hit = rid, idempotent


async def test_import_notion_ingests_all_pages():
    convs = {"a": _conv(title="A"), "b": _conv(title="B")}
    calls = []

    async def fake_ingest(csf, tenant):
        calls.append(csf["id"])
        return _Outcome(rid=f"doc_{csf['provenance']['source_id']}")

    report = await import_notion(_FakeSource(["a", "b"], convs), "acme", fake_ingest)
    assert report.ingested == 2 and report.skipped == 0
    assert set(calls) == {"ext-notion-a", "ext-notion-b"}


async def test_import_notion_skips_failing_page_without_aborting():
    convs = {"a": _conv(), "b": _conv()}

    async def fake_ingest(csf, tenant):
        if csf["provenance"]["source_id"] == "a":
            raise RuntimeError("boom")
        return _Outcome(rid="doc_b")

    report = await import_notion(_FakeSource(["a", "b"], convs), "acme", fake_ingest)
    assert report.ingested == 1 and report.skipped == 1


async def test_import_notion_counts_idempotent():
    async def fake_ingest(csf, tenant):
        return _Outcome(rid="doc_a", idempotent=True)

    report = await import_notion(_FakeSource(["a"], {"a": _conv()}), "acme", fake_ingest)
    assert report.idempotent == 1 and report.ingested == 0
