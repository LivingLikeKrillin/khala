from __future__ import annotations

import hashlib

from nexus.ingest.sources.base import ConvertedDoc
from nexus.ingest.sources.notion_importer import build_csf, classify_kind, import_notion


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
    def __init__(self, ids, convs, edits=None):
        self._ids, self._convs, self._edits = ids, convs, edits or {}

    def live_ids(self):
        return set(self._ids)

    def page_ref(self, pid):
        le = self._edits.get(pid, "t")
        return type("R", (), {"id": pid, "url": f"u/{pid}", "last_edited": le})()

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


async def test_import_notion_skips_empty_body_pages():
    # 라이브 검증서 드러난 진짜 문제: 블록 없는 컨테이너/DB행 = 빈 본문 → 인덱스 오염.
    convs = {"a": _conv(body="# 실내용\n\n본문 있음"), "b": _conv(body="  \n  ")}
    ingested_ids = []

    async def fake_ingest(csf, tenant):
        ingested_ids.append(csf["provenance"]["source_id"])
        return _Outcome(rid="x")

    report = await import_notion(_FakeSource(["a", "b"], convs), "acme", fake_ingest)
    assert ingested_ids == ["a"]   # b(빈 본문)는 ingest 안 함
    assert report.ingested == 1
    assert report.empty == 1


async def test_import_notion_counts_idempotent():
    async def fake_ingest(csf, tenant):
        return _Outcome(rid="doc_a", idempotent=True)

    report = await import_notion(_FakeSource(["a"], {"a": _conv()}), "acme", fake_ingest)
    assert report.idempotent == 1 and report.ingested == 0


async def test_import_notion_since_skips_unchanged():
    convs = {"a": _conv(), "b": _conv()}
    edits = {"a": "2026-06-01", "b": "2026-06-10"}
    seen = []

    async def fake_ingest(csf, tenant):
        seen.append(csf["provenance"]["source_id"])
        return _Outcome(rid="x")

    report = await import_notion(
        _FakeSource(["a", "b"], convs, edits), "acme", fake_ingest, since="2026-06-05"
    )
    assert seen == ["b"]              # a(06-01)는 since 이전 → skip
    assert report.ingested == 1
    assert report.watermark == "2026-06-10"   # 본 run 최대 last_edited


async def test_import_notion_no_since_processes_all():
    convs = {"a": _conv(), "b": _conv()}

    async def fake_ingest(csf, tenant):
        return _Outcome(rid="x")

    report = await import_notion(_FakeSource(["a", "b"], convs), "acme", fake_ingest)
    assert report.ingested == 2


def test_classify_kind_maps_title_keywords():
    assert classify_kind("ADR-001: 결제 DB 선택") == "ADR"
    assert classify_kind("RFC: A2A 도입") == "RFC"
    assert classify_kind("Design Doc — 결제") == "DESIGN"
    assert classify_kind("Spec for payment") == "DESIGN"   # spec→DESIGN 정규화
    assert classify_kind("Runbook: 장애 대응") == "RUNBOOK"
    assert classify_kind("Postmortem 2026-06") == "POSTMORTEM"


def test_classify_kind_defaults_to_note():
    assert classify_kind("결제 기획") == "NOTE"          # 비키워드
    assert classify_kind("Payment PRD") == "NOTE"        # 첫 토큰만 본다(보수적)
    assert classify_kind("") == "NOTE"


def test_build_csf_uses_classification():
    csf = build_csf(_conv(title="ADR: 결제"), "p1")
    assert csf["kind"] == "ADR"
    # 비키워드 제목은 기존대로 NOTE(회귀 없음)
    assert build_csf(_conv(title="결제 기획"), "p1")["kind"] == "NOTE"


def test_cli_ingest_notion_registered():
    from nexus.cli import app
    names = {c.name for c in app.registered_commands}
    assert "ingest-notion" in names
