"""Pack B — khala 자신의 코퍼스를 얼린다 (SPEC-nexus-korean-retrieval-eval §4.1).

ADR-0008 §5(b) 는 **토크나이저를** khala 의 진짜 코퍼스에서 비교할 수 있는 평가셋을 요구한다.
Pack A 는 같은 종류의 공개 대역이라 그 조건을 닫지 못한다.

**얼리는 이유는 라이브 테넌트가 움직이기 때문이다.** §4.1 이 라이브 테넌트를 실격시킨 근거가
그것이고, 그래서 Pack B 는 *이름 붙인 테넌트의 이름 붙인 시점* 이어야 한다. 매니페스트가
검증되지 않는 실행은 결과가 아니다.

**형식은 SPEC 문구와 다르다 — 이탈로 기록한다.** §4.1 은 "문서 rid·제목·본문을 디스크에" 라고
적었는데, Nexus 는 원칙 5번("인덱스이지 저장소가 아님")에 따라 **원문을 갖고 있지 않다**. 본문은
`chunks.chunk_text` 뿐이다. 그래서 디스크 파일로 내보내면 `load_pack` 이 **다시 청킹**하게 되어
재는 대상이 미묘하게 어긋난다. 대신 **테넌트 스냅샷**을 쓴다: 청크를 그대로 복사하므로 색인된
것을 정확히 그대로 재고, §4.1 이 실격시킨 이유(움직인다)는 그대로 해소한다.

rid 는 리포 관례대로 **스냅샷 테넌트를 품어** 새로 만든다 — 전역 PK 이기도 하고, 동점 정렬 키가
테넌트를 품는다는 성질에 결정성 테스트가 기대고 있다.

임베딩은 만들지 않는다. §5(b) 가 요구하는 것은 **키워드 다리**의 토크나이저 비교다.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LOCAL_DIR = Path(__file__).resolve().parents[1] / "tests" / "eval" / "local"
MANIFEST = LOCAL_DIR / "packb-manifest.json"
SNAPSHOT_TENANT = "ko_eval_packb"


def _doc_key(source_uri: str) -> str:
    """gold 가 참조할 문서 키 — `tenant:` 접두를 뗀 경로. 테넌트가 바뀌어도 같아야 한다."""
    return source_uri.split(":", 1)[1] if ":" in source_uri else source_uri


def _body_hash(texts: list[str]) -> str:
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


async def _collect(con, tenant: str) -> dict[str, dict]:
    """`{문서키: {title, chunks:[(section_path, chunk_index, text)]}}` — 활성만."""
    rows = await con.fetch(
        "SELECT d.source_uri, d.title, c.section_path, c.chunk_index, c.chunk_text "
        "FROM documents d JOIN chunks c ON c.doc_rid = d.rid AND c.tenant = d.tenant "
        "WHERE d.tenant = $1 AND d.status = 'active' AND c.status = 'active' "
        "  AND d.is_quarantined = false AND c.is_quarantined = false "
        "ORDER BY d.source_uri, c.chunk_index", tenant)
    out: dict[str, dict] = {}
    for r in rows:
        key = _doc_key(r["source_uri"])
        doc = out.setdefault(key, {"title": r["title"], "chunks": []})
        doc["chunks"].append((r["section_path"], r["chunk_index"], r["chunk_text"]))
    return out


async def cmd_freeze(args) -> int:
    """라이브 테넌트를 스냅샷 테넌트로 얼리고 매니페스트를 쓴다."""
    from nexus import db
    from nexus.index.bm25 import index_chunk_bm25
    from nexus.rid import chunk_rid, doc_rid

    class _Indexable:
        def __init__(self, text, section):
            self.chunk_text, self.section_path, self.context_prefix = text, section, None

    pool = await db.get_pool()
    try:
        async with pool.acquire() as con:
            docs = await _collect(con, args.source_tenant)
            if not docs:
                print(f"✗ {args.source_tenant} 에 활성 문서가 없다")
                return 1

            # 스냅샷을 다시 만들면 이전 것은 지운다 — 두 시점이 한 테넌트에 섞이면 그 자체가
            # §4.1 이 막으려던 '움직이는 코퍼스' 다.
            await con.execute("DELETE FROM chunks WHERE tenant=$1", SNAPSHOT_TENANT)
            await con.execute("DELETE FROM documents WHERE tenant=$1", SNAPSHOT_TENANT)

            manifest_docs = []
            n_chunks = 0
            for key, doc in sorted(docs.items()):
                uri = f"{SNAPSHOT_TENANT}:{key}"
                drid = doc_rid(uri)
                await con.execute(
                    "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, title, "
                    "status) VALUES ($1,$2,$3,'h',$4,$5,'active')",
                    drid, SNAPSHOT_TENANT, uri,
                    _body_hash([t for _, _, t in doc["chunks"]]), doc["title"])
                for section, idx, text in doc["chunks"]:
                    crid = chunk_rid(drid, section or "root", idx)
                    await con.execute(
                        "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, chunk_text, "
                        "section_path, chunk_index, status, hash) "
                        "VALUES ($1,$2,$3,$4,$5,$6,$7,'active','h')",
                        crid, SNAPSHOT_TENANT, uri, drid, text, section or "root", idx)
                    await index_chunk_bm25(crid, _Indexable(text, section or "root"))
                    n_chunks += 1
                manifest_docs.append({
                    "key": key, "title": doc["title"], "chunks": len(doc["chunks"]),
                    "body_sha256": _body_hash([t for _, _, t in doc["chunks"]]),
                })

        manifest = {
            "pack": args.name,
            "source_tenant": args.source_tenant,
            "snapshot_tenant": SNAPSHOT_TENANT,
            "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "documents": len(manifest_docs),
            "chunks": n_chunks,
            "note": ("Pack B — khala 자신의 코퍼스. 내부 문서라 **커밋하지 않는다**; 라벨과 리포트도 "
                     "이 디렉터리에만 남는다 (SPEC-nexus-korean-retrieval-eval §4.1)."),
            "docs": manifest_docs,
        }
        LOCAL_DIR.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8", newline="\n")
        print(f"✓ 얼렸다: 문서 {len(manifest_docs)} · 청크 {n_chunks} → 테넌트 {SNAPSHOT_TENANT}")
        print(f"  매니페스트: {MANIFEST}")
        return 0
    finally:
        await db.close_pool()


async def cmd_verify(_args) -> int:
    """스냅샷이 매니페스트와 같은지. **검증되지 않는 실행은 결과가 아니다** (§4.1)."""
    from nexus import db

    if not MANIFEST.exists():
        print(f"✗ 매니페스트가 없다: {MANIFEST} — 먼저 freeze 를 돌려라")
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    pool = await db.get_pool()
    try:
        async with pool.acquire() as con:
            live = await _collect(con, manifest["snapshot_tenant"])
    finally:
        await db.close_pool()

    problems: list[str] = []
    recorded = {d["key"]: d for d in manifest["docs"]}
    if len(live) != manifest["documents"]:
        problems.append(f"문서 수 {len(live)} ≠ 매니페스트 {manifest['documents']}")
    for key, doc in live.items():
        rec = recorded.get(key)
        if rec is None:
            problems.append(f"매니페스트에 없는 문서: {key}")
            continue
        got = _body_hash([t for _, _, t in doc["chunks"]])
        if got != rec["body_sha256"]:
            problems.append(f"본문이 달라졌다: {key}")
    for key in recorded:
        if key not in live:
            problems.append(f"스냅샷에서 사라진 문서: {key}")

    if problems:
        print(f"✗ 검증 실패 {len(problems)}건:", *problems[:8], sep="\n  ")
        return 1
    print(f"✓ 검증: 문서 {len(live)} · 매니페스트와 일치 ({manifest['frozen_at']} 시점)")
    return 0


async def cmd_status(_args) -> int:
    """얼린 코퍼스가 자로서 작동할 수 있는 크기인지."""
    from nexus import db

    pool = await db.get_pool()
    try:
        async with pool.acquire() as con:
            docs = await con.fetchval(
                "SELECT count(*) FROM documents WHERE tenant=$1 AND status='active'",
                SNAPSHOT_TENANT) or 0
            chunks = await con.fetchval(
                "SELECT count(*) FROM chunks WHERE tenant=$1 AND status='active'",
                SNAPSHOT_TENANT) or 0
    finally:
        await db.close_pool()

    window = 10
    floor = window / docs if docs else 1.0
    print(f"스냅샷 테넌트 {SNAPSHOT_TENANT}: 문서 {docs} · 청크 {chunks}")
    print(f"  무작위 랭커 바닥값 = 창({window}) / 문서({docs}) = {floor:.3f}")
    print("  Pack A 는 0.038. 0.10 을 넘으면 두 팔이 바닥 위에 붙어 무승부만 쌓인다.")
    print("  → " + ("잴 수 있다" if floor <= 0.10 else "검정력 부족이 예상된다"))
    return 0


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze", help="라이브 테넌트를 얼린다")
    f.add_argument("--source-tenant", default="default")
    f.add_argument("--name", default="packb-" + datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    sub.add_parser("verify", help="스냅샷 ↔ 매니페스트")
    sub.add_parser("status", help="자로서 작동할 크기인지")
    args = ap.parse_args(argv)

    if not os.getenv("DATABASE_URL"):
        print("✗ DATABASE_URL 이 없다")
        return 1
    return asyncio.run({"freeze": cmd_freeze, "verify": cmd_verify,
                        "status": cmd_status}[args.cmd](args))


if __name__ == "__main__":
    sys.exit(main())
