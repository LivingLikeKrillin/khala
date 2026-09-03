"""Pack B — khala 자신의 코퍼스를 얼린다 (SPEC-nexus-korean-retrieval-eval §4.1).

ADR-0008 §5(b) 는 **토크나이저를** khala 의 진짜 코퍼스에서 비교할 수 있는 평가셋을 요구한다.
Pack A 는 같은 종류의 공개 대역이라 그 조건을 닫지 못한다.

**얼리는 이유는 라이브 테넌트가 움직이기 때문이다.** §4.1 이 라이브 테넌트를 실격시킨 근거가
그것이고, 그래서 Pack B 는 *이름 붙인 테넌트의 이름 붙인 시점* 이어야 한다. 매니페스트가
검증되지 않는 실행은 결과가 아니다.

**형식은 SPEC 문구와 다르다 — 이탈로 기록한다.** §4.1 은 "문서 rid·제목·본문을 디스크에" 라고
적었는데, Nexus 는 원칙 5번("인덱스이지 저장소가 아님")에 따라 **원문을 갖고 있지 않다**. 본문은
`chunks.chunk_text` 뿐이다. 그래서 디스크 파일로 내보내면 `load_pack` 이 **다시 청킹**하게 되어
측정하는 대상이 미묘하게 어긋난다. 대신 **테넌트 스냅샷**을 쓴다: 청크를 그대로 복사하므로 색인된
것을 정확히 그대로 측정하고, §4.1 이 실격시킨 이유(움직인다)는 그대로 해소한다.

rid 는 리포 관례대로 **스냅샷 테넌트를 품어** 새로 만든다 — 전역 PK 이기도 하고, 동점 정렬 키가
테넌트를 품는다는 성질에 결정성 테스트가 기대고 있다.

임베딩은 만들지 않는다. §5(b) 가 요구하는 것은 **키워드 경로**의 토크나이저 비교다.
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


#: 탐침 결과 파일 — 라벨 없이 측정한 "두 실험군이 다른 순위를 내는가".
PROBE = LOCAL_DIR / "packb-disagreement.json"

#: 상위 3위 안에서 갈리는 질의의 최소 건수. 판정 규칙의 `MIN_DISCORDANT = 6` 과 같은 수를 쓴다 —
#: 이것은 불일치쌍의 **필요조건**이므로, 필요조건이 이미 최소 요구치에 못 미치면 판정은 확실히
#: 검정력 부족이다. 반대 방향의 보장은 없다(순위가 갈려도 둘 다 gold 를 잡으면 무승부다).
SHALLOW_MIN = 6


def _load_probe() -> dict | None:
    if not PROBE.exists():
        return None
    d = json.loads(PROBE.read_text(encoding="utf-8"))
    return {
        "shallow": d.get("first_difference_rank_histogram", {}).get("1-3", 0),
        "order_differs": d.get("order_differs", 0),
        "queries": d.get("queries", 0),
        "surfaced": d.get("distinct_documents_surfaced", 0),
    }


def _doc_key(source_uri: str) -> str:
    """gold 가 참조할 문서 키 — `tenant:` 접두를 뗀 경로. 테넌트가 바뀌어도 같아야 한다."""
    return source_uri.split(":", 1)[1] if ":" in source_uri else source_uri


def _body_hash(texts: list[str]) -> str:
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _manifest_doc(key: str, doc: dict) -> dict:
    """매니페스트 한 줄. **본문 길이를 함께 남긴다** — 실질 문서 판정을 DB 없이 할 수 있어야 한다.

    제목은 남기지만 본문은 남기지 않는다: 다른 조직의 정책 문서이고 리포는 public 이라, 이 파일은
    gitignore 된 `tests/eval/local/` 밖으로 나가지 않는다.
    """
    texts = [t for _, _, t in doc["chunks"]]
    return {
        "key": key, "title": doc["title"], "chunks": len(doc["chunks"]),
        "body_chars": sum(len(t) for t in texts),
        "body_sha256": _body_hash(texts),
    }


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


async def tenant_bodies(con, tenant: str) -> dict[str, dict]:
    """`{문서키: {sha, chunks, chars, machine_read}}` — **지금** 그 테넌트에 있는 본문.

    해시는 매니페스트와 **같은 함수**다. 갈라지면 라벨 서명과 팩 서명이 다른 것을 측정하게 된다.
    `machine_read` 를 같이 내는 이유는 재서명하는 사람이 자기가 무엇에 서명하는지 봐야 하기
    때문이다 — ADR-0010 §2 는 기계가 읽은 텍스트를 저술 텍스트와 같이 취급하지 말라고 한다.
    """
    docs = await _collect(con, tenant)
    tiers = {r["key"]: r["n"] for r in await con.fetch(
        "SELECT split_part(d.source_uri, ':', 2) AS key, count(*) AS n "
        "FROM documents d JOIN chunks c ON c.doc_rid = d.rid AND c.tenant = d.tenant "
        "WHERE d.tenant = $1 AND d.status = 'active' AND c.status = 'active' "
        "  AND d.is_quarantined = false AND c.is_quarantined = false "
        "  AND c.provenance_tier = 'machine_read' GROUP BY 1", tenant)}
    return {key: {"sha": _body_hash([t for _, _, t in doc["chunks"]]),
                  "chunks": len(doc["chunks"]),
                  "chars": sum(len(t) for _, _, t in doc["chunks"]),
                  "machine_read": tiers.get(key, 0)}
            for key, doc in docs.items()}


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
                manifest_docs.append(_manifest_doc(key, doc))

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
        # 얼린 직후에 두 조건을 알려준다 — "얼렸다" 를 "측정할 수 있다" 로 읽는 것을 막는다.
        from nexus.sources.corpus import PACK_B_MIN_SUBSTANTIVE, PACK_B_SUBSTANTIVE_CHARS
        n_sub = sum(1 for d in manifest_docs if d["body_chars"] >= PACK_B_SUBSTANTIVE_CHARS)
        print(f"  실질 문서(본문 {PACK_B_SUBSTANTIVE_CHARS}자 이상) {n_sub} / 최소 "
              f"{PACK_B_MIN_SUBSTANTIVE}"
              + ("" if n_sub >= PACK_B_MIN_SUBSTANTIVE else "  ← 부족하다. status 를 보라"))
        return 0
    finally:
        await db.close_pool()


def extension_problems(keys: list[str], live: dict, frozen: dict) -> list[str]:
    """더할 수 있는 문서인가. **이미 얼린 것을 조용히 갈아치우지 않는다.**

    ⛔ 왜 거부하는가 (2026-09-03). `freeze` 는 스냅샷 테넌트를 **지우고 다시 만든다** — 두 시점이
    한 테넌트에 섞이는 것을 막는 옳은 설계지만, 그래서 gold 문서 하나를 더하려고 부르면 이미 얼린
    문서 전부의 본문이 함께 지금 것으로 바뀐다. 그 본문은 재서명 워크시트가 *"무엇이 달라졌나"* 를
    보여 주는 유일한 재료다(`OPEN.md` A55). 하나를 더하려다 남의 서명 근거를 지우게 된다.

    그래서 이 명령은 **더하기만** 한다. 이미 있는 키는 갱신이 아니라 거부다.
    """
    out = [f"{k}: 라이브 `default` 에 없다" for k in keys if k not in live]
    out += [f"{k}: 이미 얼려 있다 — 갱신하려면 그 문서를 판정한 라벨을 먼저 재서명해야 한다"
            for k in keys if k in frozen]
    return out


def extended_manifest(old: dict, added: list[dict], at: str) -> dict:
    """매니페스트에 문서를 더한다. `frozen_at` 은 **안 건드린다** — 그날 얼린 것은 그날 얼린 것이다."""
    docs = old["docs"] + added
    return {**old, "documents": len(docs),
            "chunks": sum(d["chunks"] for d in docs),
            "extended_at": at, "docs": docs}


async def cmd_extend(args) -> int:
    """얼린 팩에 문서를 **더한다**. 나머지는 얼린 그대로 둔다."""
    from nexus import db
    from nexus.index.bm25 import index_chunk_bm25
    from nexus.rid import chunk_rid, doc_rid

    class _Indexable:
        def __init__(self, text, section):
            self.chunk_text, self.section_path, self.context_prefix = text, section, None

    if not MANIFEST.exists():
        print(f"✗ 매니페스트가 없다: {MANIFEST} — 더할 팩이 없다. 먼저 freeze 를 돌려라")
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    pool = await db.get_pool()
    try:
        async with pool.acquire() as con:
            live = await _collect(con, args.source_tenant)
            frozen = await _collect(con, SNAPSHOT_TENANT)
            if problems := extension_problems(args.keys, live, frozen):
                print("✗ 더할 수 없다:", *problems, sep="\n  ")
                return 1
            added = []
            for key in args.keys:
                doc = live[key]
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
                added.append(_manifest_doc(key, doc))

        at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        MANIFEST.write_text(
            json.dumps(extended_manifest(manifest, added, at), ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8", newline="\n")
        for d in added:
            print(f"✓ 더했다: {d['key']} · 청크 {d['chunks']} · 본문 {d['body_chars']}자")
        print(f"  팩 문서 {manifest['documents']} → {manifest['documents'] + len(added)}")
        print("  ⚠ 얼린 나머지는 건드리지 않았다 — 그 본문이 재서명의 대조 기준이다")
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
    """얼린 코퍼스가 자로서 작동할 수 있는지 — **두 조건**을 측정한다.

    문서 수만 세다 걸린 적이 있다(2026-08-07): 116문서를 채웠는데 본문 800자 이상이 19건이었고,
    나머지는 개정 이력 행이었다. 바닥값은 통과인데 gold 로 쓸 문서가 없어서 못 측정한다.
    """
    from nexus import db
    from nexus.sources.corpus import PACK_B_SUBSTANTIVE_CHARS

    pool = await db.get_pool()
    try:
        async with pool.acquire() as con:
            docs = await con.fetchval(
                "SELECT count(*) FROM documents WHERE tenant=$1 AND status='active'",
                SNAPSHOT_TENANT) or 0
            chunks = await con.fetchval(
                "SELECT count(*) FROM chunks WHERE tenant=$1 AND status='active'",
                SNAPSHOT_TENANT) or 0
            substantive = await con.fetchval(
                "SELECT count(*) FROM ("
                "  SELECT d.rid FROM documents d JOIN chunks c "
                "    ON c.doc_rid = d.rid AND c.tenant = d.tenant AND c.status='active' "
                "  WHERE d.tenant=$1 AND d.status='active' "
                "  GROUP BY d.rid HAVING sum(length(c.chunk_text)) >= $2) t",
                SNAPSHOT_TENANT, PACK_B_SUBSTANTIVE_CHARS) or 0
    finally:
        await db.close_pool()

    window = 10
    floor = window / docs if docs else 1.0
    ok_floor = floor <= 0.10
    print(f"스냅샷 테넌트 {SNAPSHOT_TENANT}: 문서 {docs} · 청크 {chunks}")
    print(f"  [1] 무작위 랭커 바닥값 = 창({window}) / 문서({docs}) = {floor:.3f}"
          f"  → {'통과' if ok_floor else '검정력 부족이 예상된다'}")
    print("      Pack A 는 0.038. 0.10 을 넘으면 두 실험군이 바닥 위에 붙어 무승부만 쌓인다.")

    # [2] 는 **측정한 문턱**이다. 한때 여기 "실질 문서 ≥ 60" 이 있었는데 그 60 은 측정해 보지 않고
    # 만든 어림수였고, 같은 날 라벨 없이 재보니 그 근거가 반증됐다(§6.3). 검정력을 예고하는 양은
    # 문서 수가 아니라 **두 실험군의 순위가 갈리는 자리**다.
    probe = _load_probe()
    print(f"  [2] 탐침: 상위 3위 안에서 갈리는 질의 = "
          f"{probe['shallow'] if probe else '미측정'}"
          + (f" / 최소 {SHALLOW_MIN}" if probe else ""))
    if probe:
        print(f"      순위표가 갈리는 질의 {probe['order_differs']}/{probe['queries']} · "
              f"상위10에 뜬 문서 {probe['surfaced']}")
        print("      gold 가 갈리는 자리 이후에 있어야 승패가 생긴다. 얕게 갈릴수록 여지가 크다.")
    else:
        print("      아직 안 돌렸다: scripts/ko_eval_packb_disagreement.py")
    print(f"  참고: 실질 문서(본문 {PACK_B_SUBSTANTIVE_CHARS}자 이상) {substantive} — "
          "문턱이 아니라 코퍼스 구성 정보다")

    ok_probe = bool(probe) and probe["shallow"] >= SHALLOW_MIN
    print("  → " + ("측정할 수 있다" if ok_floor and ok_probe else
                    "아직 아니다 — 탐침을 돌려 승패가 생길 자리가 있는지부터 보라"))
    print("     (필요조건이다. 순위가 갈려도 둘 다 gold 를 잡으면 무승부이고, '검정력 부족' 은 "
          "여전히 나올 수 있다 — 그때 의무는 ADR-0009 대로 열린 채 남는다.)")
    return 0 if (ok_floor and ok_probe) else 1


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
    e = sub.add_parser("extend", help="얼린 팩에 문서를 더한다(나머지는 그대로)")
    e.add_argument("keys", nargs="+", help="더할 문서 키")
    e.add_argument("--source-tenant", default="default")
    sub.add_parser("verify", help="스냅샷 ↔ 매니페스트")
    sub.add_parser("status", help="자로서 작동할 크기인지")
    args = ap.parse_args(argv)

    if not os.getenv("DATABASE_URL"):
        print("✗ DATABASE_URL 이 없다")
        return 1
    return asyncio.run({"freeze": cmd_freeze, "extend": cmd_extend, "verify": cmd_verify,
                        "status": cmd_status}[args.cmd](args))


if __name__ == "__main__":
    sys.exit(main())
