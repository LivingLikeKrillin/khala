"""Notion importer (S4) — Notion 페이지를 CSF로 변환해 S3 타입-인지 intake로 적재.

순수 오케스트레이터: ingest_fn 을 주입받아 a2a/DB에 무의존. 구체 ingest_fn(프로덕션
_default_external_ingest_fn) 와이어링은 CLI(합성 루트)가 한다. build_csf 는 S3 서버측
validate_external_spec 을 통과하는 형태를 구성으로 보장(id 형식 + source_hash=sha256(body)).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from nexus.ingest.sources.base import ConvertedDoc
from nexus.ingest.sources.notion_reconcile import notion_doc_rid

# 제목 첫 토큰 → 축-A 타입(결정론적 휴리스틱; LLM 미사용 — nexus 규율). 미매치 NOTE.
_KEYWORD_TO_TYPE = {
    "adr": "ADR", "rfc": "RFC", "prd": "PRD", "design": "DESIGN",
    "spec": "DESIGN", "runbook": "RUNBOOK", "postmortem": "POSTMORTEM",
}


def classify_kind(title: str) -> str:
    """제목 첫 토큰으로 축-A 타입 추론(결정론). 미매치→NOTE(default-memo 정합)."""
    tokens = re.split(r"[^a-z0-9]+", (title or "").strip().lower(), maxsplit=1)
    return _KEYWORD_TO_TYPE.get(tokens[0] if tokens else "", "NOTE")


def build_csf(
    conv: ConvertedDoc,
    page_id: str,
    roots: set[str] | None = None,
    walked_roots: set[str] | None = None,
) -> dict:
    """ConvertedDoc(markdown+frontmatter) → CSF dict. kind=제목 분류(미매치 NOTE).

    roots(=이 페이지에 닿은 root)를 주면 provenance.source_roots 로 실어 보낸다. walked_roots
    (=이번 실행이 걸은 root 전체)도 함께 보낸다 — sink 가 `prov_inputs := (기존 − walked) ∪ reached`
    로 갱신해야, 부분 root 실행이 걷지 않은 root 의 귀속을 지우지 않는다(SPEC §3.1).
    정렬해 담는다: 같은 입력이 같은 prov_inputs 를 낳아야 재실행이 멱등하다.
    """
    body = conv.markdown
    provenance = {
        "source_tool": "notion",
        "source_id": page_id,
        "source_url": conv.frontmatter.get("origin_url", ""),
        "source_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }
    if roots:
        provenance["source_roots"] = sorted(roots)
        provenance["walked_roots"] = sorted(walked_roots or roots)
    return {
        "id": f"ext-notion-{page_id}",
        "kind": classify_kind(conv.frontmatter.get("title", "") or ""),
        "title": conv.frontmatter.get("title") or page_id,
        "body": body,
        "provenance": provenance,
    }


@dataclass
class ImportReport:
    ingested: int = 0
    idempotent: int = 0
    skipped: int = 0
    empty: int = 0
    watermark: str | None = None
    results: list[dict] = field(default_factory=list)
    # 재조정(reconcile_fn 을 준 경우에만 채워진다)
    pruned: int = 0
    revived: int = 0
    refused: bool = False
    reason: str = ""
    #: 그림에서 읽어 본문에 넣은 장수 (SPEC-nexus-screenshot-text-extraction).
    images_extracted: int = 0


async def _fill_images(conv, tenant: str) -> tuple[str, int]:
    """그림 자리 표식을 추출 블록으로 바꾼다. 꺼져 있으면 표식만 지운다.

    **기본은 꺼짐.** 켜는 것은 원문 질의가 아니라 **문서 이미지**가 공급자로 나가는 것을
    받아들이는 행위이고, 그 판단은 코퍼스를 가진 배포가 한다.
    """
    import os

    from nexus.ingest import vision_store

    if (os.getenv("NEXUS_VISION") or "off").strip().lower() != "on":
        md = conv.markdown
        for im in conv.images:
            md = md.replace(f"<!-- khala:vision:slot:{im['block_id']} -->", "![]()")
        return md, 0

    from nexus.ingest.pipeline import _load_config
    from nexus.providers.llm import LLMService

    cfg = _load_config()
    return await vision_store.apply(
        conv.markdown, conv.images, tenant=tenant, llm_svc=LLMService(),
        pii_patterns=(cfg.get("pii_patterns") or {}))


# IngestFn: (csf, tenant, *, force) -> outcome(awaitable). 프로덕션은 _default_external_ingest_fn.
# `force` 를 계약에 넣는다 — 콘솔의 force 는 적재까지 닿아야 강제가 된다.
IngestFn = Callable[..., Awaitable]

# ReconcileFn: (tenant, walked_roots, live_rids) -> outcome(awaitable).
# 프로덕션은 notion_reconcile.default_reconcile_fn. 미주입 시 재조정을 하지 않는다(기존 동작).
ReconcileFn = Callable[[str, set, set], Awaitable]


async def import_notion(
    source,
    tenant: str,
    ingest_fn: IngestFn,
    since: str | None = None,
    reconcile_fn: ReconcileFn | None = None,
    force: bool = False,
) -> ImportReport:
    """live_index 페이지를 fetch→csf→ingest. since 이후 변경분만(증분). per-page skip.

    watermark: 본 run 에서 본 ref 의 최대 last_edited(다음 since). 주의(한계): since 범위 내에서
    실패한 변경 페이지는 watermark 가 앞서가 다음 since 로 건너뛸 수 있다 — 복구는 since 없이 재실행.

    reconcile_fn 을 주면 **적재가 끝난 뒤** 재조정한다(SPEC §3.3 — 순서가 중요하다: soft_deleted
    문서는 collector 의 active-only dedup 에 안 걸려 먼저 재적재되고, 그 다음 상태가 뒤집힌다).
    live 집합은 `since` 와 무관하게 열거 전체다 — since 는 무엇을 '적재'할지만 좁힌다.
    """
    index = source.live_index()
    walked_roots: set[str] = set()
    for roots in index.values():
        walked_roots |= roots

    report = ImportReport()
    max_seen = since or ""

    for page_id in sorted(index):
        try:
            ref = source.page_ref(page_id)
            le = getattr(ref, "last_edited", "") or ""
            if le > max_seen:
                max_seen = le
            if since and le <= since:
                continue
            conv = source.fetch_markdown(ref)
            # ── 2패스: 그림 자리를 추출 블록으로 채운다 ────────────────────────
            # 순회(동기)와 추출(HTTP+LLM, 비동기)을 갈라 둔 이음매다. 꺼져 있으면 자리 표식만
            # 지우고 예전 `![]()` 로 돌아간다 — 추출이 안 도는 배포에서 본문이 표식으로
            # 오염되면 청커가 거기서 갈린다.
            if conv.images:
                conv.markdown, n_extracted = await _fill_images(conv, tenant)
                conv.vision_extracted = n_extracted > 0
                report.images_extracted += n_extracted
            # 빈 본문(블록 없는 컨테이너/DB행)은 인덱스 오염 — 적재 안 함(라이브 검증 신호).
            if not conv.markdown.strip():
                report.empty += 1
                report.results.append({"page_id": page_id, "skipped": "empty body"})
                continue
            # force 를 여기서 흘리지 않으면 (tenant, source_uri, content_hash) dedup 이 이기고,
            # 본문이 안 바뀐 페이지는 제목·메타데이터 수정이 있어도 영원히 idempotent 다.
            outcome = await ingest_fn(
                build_csf(conv, page_id, index[page_id], walked_roots), tenant, force=force
            )
            if getattr(outcome, "idempotent_hit", False):
                report.idempotent += 1
            else:
                report.ingested += 1
            report.results.append({"page_id": page_id, "rid": outcome.resource_rid})
        except Exception as e:  # noqa: BLE001 — per-page 격리(기존 ingest 에러 규칙)
            report.skipped += 1
            report.results.append({"page_id": page_id, "error": str(e)})
    report.watermark = max_seen or None

    if reconcile_fn is not None:
        # rid → 이 페이지에 닿은 root 들. 재조정이 **적재를 거쳤든 아니든** 모든 live 페이지의
        # prov_inputs 를 갱신할 수 있어야 한다 — 그래야 `--since` 가 백필을 막지 못한다
        # (SPEC-nexus-notion-source-console §4.5). live 집합 자체는 since 와 무관하다.
        live_by_rid = {notion_doc_rid(tenant, pid): sorted(roots) for pid, roots in index.items()}
        outcome = await reconcile_fn(tenant, walked_roots, live_by_rid)
        report.pruned = outcome.pruned
        report.revived = outcome.revived
        report.refused = outcome.refused
        report.reason = outcome.reason
    return report
