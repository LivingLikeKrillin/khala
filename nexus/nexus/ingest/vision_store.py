"""추출 결과의 durable 저장 + 2패스 채우기 — SPEC-nexus-screenshot-text-extraction §4.4.

**캐시가 아니다.** [[ADR-0010]] §5 의 불변식은 저장된 텍스트에 걸려 있다: 같은
`(tenant, bytes, extractor_identity)` 에 대해 한 번 저장된 결과는 다시 읽어서 교체되지 않는다.
캐시라고 부르고 불변식을 그 위에 세우면 척추가 보존 정책에 걸린다 — 미스 한 번이 비결정적
판독기를 다시 돌리고, 드리프트한 텍스트가 **바뀌지 않은 신원** 아래로 들어간다. 신원이 안
움직였기 때문에 정확히 안 보인다.

순서도 여기서 지킨다: **추출 → 스캔/격리 → 저장 → 본문 조립 → content_hash.** 스캐너가 먼저
도는 이유는 그림 속 텍스트가 스캐너가 읽을 수 있는 유일한 형태가 추출물이기 때문이고, 저장보다
먼저인 이유는 격리될 텍스트를 durable 저장에 넣지 않기 위해서다.
"""

from __future__ import annotations

import asyncio
import os

import structlog

from nexus import db
from nexus.ingest import vision

log = structlog.get_logger(__name__)


async def load(tenant: str, sha: str, identity: str) -> dict | None:
    """저장된 결과. 없으면 None."""
    row = await db.fetch_one(
        "SELECT text, error, truncated FROM vision_extractions "
        "WHERE tenant=$1 AND image_sha256=$2 AND extractor_identity=$3",
        tenant, sha, identity)
    return dict(row) if row else None


async def save(tenant: str, e: vision.Extraction) -> dict:
    """결과를 저장하고 **실제로 저장된 것**을 돌려준다.

    `ON CONFLICT DO NOTHING` 이고, 진 쪽은 자기 추출을 **버리고 저장된 행을 읽어 간다.**
    자기 것을 쓰면 같은 이미지에 대해 두 적재가 서로 다른 본문을 만들고, `content_hash` 가
    어느 프로세스가 경쟁에서 이겼는지에 따라 달라진다.
    """
    await db.execute(
        "INSERT INTO vision_extractions (tenant, image_sha256, extractor_identity, "
        "                                text, error, truncated) "
        "VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING",
        tenant, e.sha, e.identity, e.text or None, e.error or None, e.truncated)
    stored = await load(tenant, e.sha, e.identity)
    return stored or {"text": e.text, "error": e.error, "truncated": e.truncated}


async def _fetch_bytes(url: str) -> tuple[bytes, str]:
    import httpx

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.content, (r.headers.get("content-type") or "image/png").split(";")[0]


async def _one(image: dict, tenant: str, llm_svc, pii_patterns: dict) -> tuple[str, str]:
    """이미지 하나 → (slot, 본문에 넣을 markdown)."""
    block_id, url = image["block_id"], image.get("url") or ""
    slot = f"<!-- khala:vision:slot:{block_id} -->"
    alt = image.get("caption") or ""
    bare = f"![{alt}]()" if alt else "![]()"

    if not url:
        return slot, bare

    # ── 가져오기. 실패해도 **기록**한다 ─────────────────────────────────────
    try:
        data, media_type = await _fetch_bytes(url)
    except Exception as exc:  # noqa: BLE001
        e = vision.fetch_failure(block_id, f"{type(exc).__name__}: {exc}")
        await save(tenant, e)
        log.warning("vision.fetch_failed", block=block_id[:8], error=str(exc)[:120])
        return slot, bare

    sha = vision.image_sha256(data)
    identity = vision.extractor_identity()

    # ── 이미 읽은 바이트는 다시 읽지 않는다 ────────────────────────────────
    stored = await load(tenant, sha, identity)
    if stored is not None:
        if stored.get("error"):
            return slot, bare
        return slot, vision.build_block(vision.Extraction(
            stored["text"] or "", identity, sha, truncated=bool(stored.get("truncated"))))

    e = await vision.read_image(data, media_type, llm_svc)
    if not e.ok:
        await save(tenant, e)
        return slot, bare

    # ── 스캔이 저장보다 **먼저**다 ─────────────────────────────────────────
    # 그림 속 업무 이메일은 추출물이 되어야만 스캐너 눈에 보인다. 격리될 텍스트를 durable
    # 저장에 넣으면, chunk 를 격리해도 그 문자열은 지울 경로 없는 행에 남는다.
    if pii_patterns:
        from nexus.ingest.scanner import scan_content
        scan = scan_content(e.text, pii_patterns)
        if scan.has_pii:
            log.warning("vision.quarantined", block=block_id[:8], types=scan.pii_types)
            await save(tenant, vision.Extraction(
                "", identity, sha, error=f"quarantined: {','.join(scan.pii_types)}"))
            return slot, bare

    stored = await save(tenant, e)
    return slot, vision.build_block(vision.Extraction(
        stored["text"] or "", identity, sha, truncated=bool(stored.get("truncated"))))


async def apply(markdown: str, images: list[dict], *, tenant: str, llm_svc,
                pii_patterns: dict | None = None) -> tuple[str, int]:
    """2패스의 두 번째. 자리 표식을 추출 블록으로 바꾼다. → (markdown, 추출된 장수)

    한 번에 몇 장씩 읽는지는 제한한다 — 44장을 동시에 던지면 공급자 rate limit 에 걸리고,
    직렬로 읽으면 첫 실행이 길어진다.
    """
    if not images:
        return markdown, 0

    ceiling = vision.max_per_ingest()
    todo = images[:ceiling] if ceiling else images
    if len(todo) < len(images):
        # 조용히 자르지 않는다 — 건너뛴 장수는 보여야 다음 실행에서 이어갈 수 있다.
        log.warning("vision.ceiling_reached", limit=ceiling, skipped=len(images) - len(todo))

    sem = asyncio.Semaphore(int(os.getenv("NEXUS_VISION_CONCURRENCY") or 4))

    async def _guarded(im):
        async with sem:
            return await _one(im, tenant, llm_svc, pii_patterns or {})

    results = await asyncio.gather(*(_guarded(im) for im in todo), return_exceptions=True)

    extracted = 0
    for im, r in zip(todo, results):
        slot = f"<!-- khala:vision:slot:{im['block_id']} -->"
        if isinstance(r, Exception):
            log.warning("vision.slot_failed", block=im["block_id"][:8], error=str(r)[:120])
            markdown = markdown.replace(slot, "![]()")
            continue
        _, block = r
        extracted += block.startswith("![](){: derived=vision")
        markdown = markdown.replace(slot, block)

    # 상한에 걸려 못 읽은 자리도 본문에서는 지워야 한다 — 표식이 남으면 청킹이 거기서 갈린다.
    for im in images[len(todo):]:
        markdown = markdown.replace(f"<!-- khala:vision:slot:{im['block_id']} -->", "![]()")

    return markdown, extracted
