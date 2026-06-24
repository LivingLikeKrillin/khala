"""Notion importer (S4) — Notion 페이지를 CSF로 변환해 S3 타입-인지 intake로 적재.

순수 오케스트레이터: ingest_fn 을 주입받아 a2a/DB에 무의존. 구체 ingest_fn(프로덕션
_default_external_ingest_fn) 와이어링은 CLI(합성 루트)가 한다. build_csf 는 S3 서버측
validate_external_spec 을 통과하는 형태를 구성으로 보장(id 형식 + source_hash=sha256(body)).
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from nexus.ingest.sources.base import ConvertedDoc


def build_csf(conv: ConvertedDoc, page_id: str) -> dict:
    """ConvertedDoc(markdown+frontmatter) → CSF dict. kind=NOTE(default-memo)."""
    body = conv.markdown
    return {
        "id": f"ext-notion-{page_id}",
        "kind": "NOTE",
        "title": conv.frontmatter.get("title") or page_id,
        "body": body,
        "provenance": {
            "source_tool": "notion",
            "source_id": page_id,
            "source_url": conv.frontmatter.get("origin_url", ""),
            "source_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        },
    }


@dataclass
class ImportReport:
    ingested: int = 0
    idempotent: int = 0
    skipped: int = 0
    results: list[dict] = field(default_factory=list)


# IngestFn: (csf, tenant) -> outcome(awaitable). 프로덕션은 _default_external_ingest_fn.
IngestFn = Callable[[dict, str], Awaitable]


async def import_notion(source, tenant: str, ingest_fn: IngestFn) -> ImportReport:
    """source.live_ids() 페이지를 fetch→csf→ingest. per-page skip(1건 실패가 전체 중단 금지)."""
    report = ImportReport()
    for page_id in sorted(source.live_ids()):
        try:
            ref = source.page_ref(page_id)
            conv = source.fetch_markdown(ref)
            outcome = await ingest_fn(build_csf(conv, page_id), tenant)
            if getattr(outcome, "idempotent_hit", False):
                report.idempotent += 1
            else:
                report.ingested += 1
            report.results.append({"page_id": page_id, "rid": outcome.resource_rid})
        except Exception as e:  # noqa: BLE001 — per-page 격리(기존 ingest 에러 규칙)
            report.skipped += 1
            report.results.append({"page_id": page_id, "error": str(e)})
    return report
