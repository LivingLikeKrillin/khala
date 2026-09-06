"""답이 든 청크가 **그 질의의 BM25 에 애초에 걸리기는 하는가** — 결정론, LLM 0회.

⛔ **왜 있나 (실측 2026-09-05, `OPEN.md` A86).** S2 한 건을 span 으로 끝까지 따라갔더니 답이 든
청크가 **어느 후보 풀에도 안 들어왔다**(FP2). 잘린 것이 아니라 애초에 못 들어온 것이고, 원인은
순위가 아니었다 — 질의 tsquery 는 전부 한국어 어간인데 그 청크는 **한글 0.0%** 인 영문 절이라
**겹치는 토큰이 하나도 없었다**(`matches=false`). 벡터도 상위 60 밖이었다.

⭐ **그런데 라벨 하나는 일화다.** 이 리포는 기법 추가로 7전 7패했고 오른 것은 전부 결함 제거였다.
그러니 처방을 고르기 전에 **크기를 측정한다** — 그것이 이 파일의 전부다.

**판정하지 않는다. 문턱도 없다.** 내는 것은 분포다(`self_document_crowding.py` 와 같은 규율).
"몇 % 아래면 문제" 를 여기서 정하면 그 수가 인용되고, 이 리포는 지어낸 수에 이미 여러 번 데였다.

무엇을 세는가 — 라벨마다:

  ① 요구한 사실이 든 청크를 찾는다 (선언된 테넌트 안에서, 부분일치)
  ② 그 청크가 **이 질의의 tsquery** 에 걸리는가 (`tsvector_ko @@ to_tsquery`)
  ③ 안 걸리면 BM25 는 그 청크를 **영영 못 낸다** — 벡터 하나에 전부 걸린 상태다

②는 프로덕션과 같은 경로로 만든다(`active_tokenizer` → `tokens_to_tsquery`). 사본을 두면
하니스가 아무도 안 지나는 토큰화를 측정한다 — 이 리포가 이미 데인 자리다.

    docker exec nexus-app python -m scripts.answer_chunk_reach \\
        --labels /app/tests/eval/local/answer-facts.yaml \\
        --labels /app/tests/eval/local/packb-labels.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from nexus import db  # noqa: E402
from nexus.api import _load_config  # noqa: E402
from nexus.index.bm25 import active_tokenizer, tokens_to_tsquery  # noqa: E402
from nexus.index.vector_index import configured_column  # noqa: E402
from nexus.providers.embedding import embedding_service_from_config  # noqa: E402
from scripts.ko_eval_corpus_reach import UndeclaredCorpus, escape_like, resolve_tenant  # noqa: E402

HANGUL = re.compile(r"[가-힣]")


def hangul_ratio(text: str) -> float:
    """한글 글자 비율. **설명 변수이지 판정이 아니다** — 이 수로 무엇을 자르지 않는다."""
    return len(HANGUL.findall(text or "")) / max(len(text or ""), 1)


#: 한 묶음의 판정. **순수 함수로 뺀 이유가 있다** — 첫 판은 이 조합이 DB 함수 안에 있었고,
#: 벡터 판정을 통째로 지워도 검사가 **전부 초록이었다**. 크기를 2배로 과장하는 파손이 안 잡혔다.
def group_verdict(chunks: int, bm25: bool | None, vector: bool | None) -> str:
    """`absent`(코퍼스에 답이 없다) · `reachable` · `bm25_blind`(벡터만 길이 있다) ·
    `unreachable`(두 레그 다 못 넣는다).

    ⭐ `bm25_blind` 와 `unreachable` 을 가르는 것이 이 측정의 값이다. BM25 만 보면 잠복까지
    같이 세어 크기가 부풀고, 부푼 수로 비싼 처방을 고르게 된다.
    """
    if not chunks:
        return "absent"
    if bm25:
        return "reachable"
    return "bm25_blind" if vector else "unreachable"


def required_groups(q: dict) -> list[list[str]]:
    """두 라벨 스키마를 하나로 읽는다.

    `expect`/`expect_all` 은 `answer_fact_probe` 의 규칙이고 `must_contain` 은 Pack B 계열의
    것이다. 둘 다 **묶음은 AND, 묶음 안은 표기 후보 OR** 로 같은 모양이라 여기서 합쳐 읽는다.
    """
    if q.get("must_contain"):
        return [list(g) if isinstance(g, list) else [g] for g in q["must_contain"]]
    if q.get("expect_all"):
        return [list(g) if isinstance(g, list) else [g] for g in q["expect_all"]]
    expect = list(q.get("expect") or [])
    return [expect] if expect else []


#: ⚠ **`chunk_text` 로 찾는 것은 검색이 아니다.** `nexus/CLAUDE.md` 는 *검색* 대상으로
#: `search_text` 를 쓰라고 하고 그 규칙은 옳다 — 여기서 하는 일은 검색이 아니라 **요구한 문자열이
#: 어느 청크 본문에 있는가**를 찾는 것이다. 반대로 걸리는가 판정(`tsvector_ko @@ to_tsquery`)은
#: `search/hybrid.py` 의 BM25 레그와 **같은 식**이다 — 그쪽이 실제 검색이라서 그렇다.
_SQL = r"""
SELECT c.rid, c.chunk_text, c.tenant,
       (c.tsvector_ko @@ to_tsquery('simple', $3)) AS matches
FROM chunks c
WHERE c.tenant = ANY($2::text[])
  AND c.status = 'active'
  AND c.chunk_text ILIKE '%' || $1 || '%' ESCAPE '\'
"""


async def group_reach(alternates: list[str], tenants: list[str], tsquery: str,
                      vec_pool: set[str], pool) -> dict:
    """이 묶음의 답이 든 청크들과, 그 청크가 이 질의에 잡히는가.

    ⚠ 묶음 안 후보 중 **하나라도** 든 청크를 전부 모은다. 그중 하나라도 tsquery 에 걸리면
    BM25 에 길이 있다 — 순위는 별개다. 이 검사가 답하는 것은 **길이 있는가**뿐이다.
    """
    rows = []
    for alt in alternates:
        if not alt:
            continue
        rows += await pool.fetch(_SQL, escape_like(alt), tenants, tsquery)
    by_rid = {r["rid"]: r for r in rows}
    if not by_rid:
        return {"chunks": 0, "bm25_reachable": None, "vector_reachable": None,
                "verdict": group_verdict(0, None, None),
                "min_hangul": None, "max_hangul": None}
    ratios = [hangul_ratio(r["chunk_text"]) for r in by_rid.values()]
    bm25 = any(r["matches"] for r in by_rid.values())
    vector = bool(by_rid.keys() & vec_pool)
    return {
        "chunks": len(by_rid),
        "bm25_reachable": bm25,
        "vector_reachable": vector,
        "verdict": group_verdict(len(by_rid), bm25, vector),
        "min_hangul": round(min(ratios), 4),
        "max_hangul": round(max(ratios), 4),
    }


async def vector_pool(query: str, tenants: list[str], top_k: int, svc, column: str, pool) -> set[str]:
    """이 질의의 **벡터 후보 풀**(상위 `top_k`)에 든 청크 rid.

    BM25 만 보면 *"길이 없다"* 를 과장한다 — S2 에서 실제로 답을 못 낸 이유는 두 레그가 **둘 다**
    못 넣은 것이지 BM25 하나가 아니었다. 프로덕션과 같은 컬럼·같은 상한을 쓴다.
    """
    vec = (await svc.embed_query(query)) if hasattr(svc, "embed_query") \
        else (await svc.embed([query]))[0]
    lit = "[" + ",".join(f"{x:.7f}" for x in vec) + "]"
    rows = await pool.fetch(
        f"SELECT rid FROM chunks WHERE tenant = ANY($2::text[]) AND status='active'"
        f" AND {column} IS NOT NULL ORDER BY {column} <=> $1::vector LIMIT {int(top_k)}",
        lit, tenants)
    return {r["rid"] for r in rows}


async def scan(path: Path, cli_tenant: str, pool) -> dict:
    labels = yaml.safe_load(path.read_text(encoding="utf-8"))
    tenant, note = resolve_tenant(labels, cli_tenant)
    tenants = [t.strip() for t in tenant.split(",") if t.strip()]
    tok = active_tokenizer()
    # 프로덕션과 **같은 컬럼·같은 상한**을 쓴다. 여기서 수를 지어내면 아무도 안 지나는 풀을 센다.
    cfg = _load_config()
    # ⛔ 컬럼을 설정에서 직접 읽지 않는다 — `nexus/CLAUDE.md` 이음매 지도의 그 자리다.
    # 검색 경로와 여기가 다른 컬럼을 보면 이 측정은 아무도 안 지나는 벡터를 센다.
    column = configured_column(cfg)
    top_k = int(cfg.get("search", {}).get("vector_top_k", 20))
    svc = embedding_service_from_config()
    rows = []
    for q in labels.get("queries") or []:
        if q.get("blocked_on") or not q.get("query"):
            continue
        groups = required_groups(q)
        if not groups:
            continue
        tokens = tok(q["query"]) if callable(tok) else tok.tokenize(q["query"])
        tsquery = tokens_to_tsquery(tokens)
        if not tsquery:
            continue
        vec_pool = await vector_pool(q["query"], tenants, top_k, svc, column, pool)
        found = [await group_reach(g, tenants, tsquery, vec_pool, pool) for g in groups]
        rows.append({
            "id": q.get("id"),
            "query_hangul": round(hangul_ratio(q["query"]), 4),
            "groups": len(groups),
            # 코퍼스에 아예 없는 묶음 — 이 검사의 대상이 아니다(겨냥 문제이거나 FP1)
            "absent": sum(1 for f in found if f["verdict"] == "absent"),
            # ⭐ **이 파일의 수**: 답이 코퍼스에 있는데 BM25 가 그 청크를 못 보는 묶음
            "invisible_to_bm25": sum(
                1 for f in found if f["verdict"] in ("bm25_blind", "unreachable")),
            "reachable": sum(1 for f in found if f["verdict"] == "reachable"),
            # ⭐ **두 레그가 다 못 넣는 묶음** — S2 가 실제로 답을 못 낸 그 상태다
            "unreachable_by_either": sum(1 for f in found if f["verdict"] == "unreachable"),
            "min_hangul_of_answer_chunks": min(
                [f["min_hangul"] for f in found if f["min_hangul"] is not None], default=None),
        })
    return {"labels": path.name, "tenant": tenant, "note": note, "rows": rows}


def report_lines(scans: list[dict]) -> list[str]:
    """**분포만 낸다.** 비율도 등급도 없다 — 무엇을 고칠지는 사람이 이 표를 보고 정한다."""
    out: list[str] = []
    tot_labels = tot_groups = tot_blind = tot_dead = 0
    for s in scans:
        rows = s["rows"]
        blind = [r for r in rows if r["invisible_to_bm25"]]
        dead = [r for r in rows if r["unreachable_by_either"]]
        groups = sum(r["groups"] for r in rows)
        tot_labels += len(rows)
        tot_groups += groups
        tot_blind += sum(r["invisible_to_bm25"] for r in rows)
        tot_dead += sum(r["unreachable_by_either"] for r in rows)
        out += ["", f"── {s['labels']}  (테넌트 `{s['tenant']}`)",
                f"   라벨 {len(rows)}건 · 요구 묶음 {groups}개",
                f"   BM25 가 답 청크를 못 보는 라벨: {len(blind)}건 {[r['id'] for r in blind]}",
                f"   **두 레그가 다 못 넣는** 라벨: {len(dead)}건 {[r['id'] for r in dead]}",
                f"   코퍼스에 답이 아예 없는 묶음이 있는 라벨: "
                f"{len([r for r in rows if r['absent']])}건"]
        for r in blind:
            tail = " · **벡터도 못 넣는다**" if r["unreachable_by_either"] else " · 벡터는 넣는다"
            out.append(f"     - {r['id']}: 질의 한글 {r['query_hangul']:.0%} · "
                       f"답 청크 한글 최저 {r['min_hangul_of_answer_chunks']:.0%}{tail}")
    out += ["",
            f"합계 — 라벨 {tot_labels}건 · 요구 묶음 {tot_groups}개 중 "
            f"BM25 사각 {tot_blind}개 · **두 레그 모두 사각 {tot_dead}개**",
            "",
            "⚠ **길이 있는가**만 말한다 — 풀에 들어갈 수 있는가이지 상위에 오는가가 아니다.",
            "⚠ 한글 비율은 설명 변수이지 판정이 아니다 — 이 수로 무엇을 자르지 마라.",
            "⚠ 답 청크는 **요구 문자열이 든 청크**로 정의했다. 사람이 고른 gold 문서가 아니다."]
    return out


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", action="append", required=True, help="라벨 파일(여러 번 줄 수 있다)")
    ap.add_argument("--tenant", default="", help="라벨의 `corpus.tenant` 를 덮어쓴다")
    ap.add_argument("--out", default="", help="행 단위 기록을 적을 JSON")
    args = ap.parse_args()

    pool = await db.get_pool()
    try:
        scans = []
        for raw in args.labels:
            try:
                scans.append(await scan(Path(raw), args.tenant, pool))
            except UndeclaredCorpus as e:
                print(f"⛔ {raw}: {e}")
                return 2
        for line in report_lines(scans):
            print(line)
        if args.out:
            Path(args.out).write_text(json.dumps(scans, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
            print(f"\n  기록: {args.out}")
    finally:
        await db.close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
