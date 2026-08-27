"""한국어 검색 평가 하니스 — 적재·채점·판정 (SPEC-nexus-korean-retrieval-eval §4.3~§4.5).

**판정은 "정답 문서를 찾았나" 다.** 다리는 청크를 돌려주므로 문서로 접은 뒤(같은 문서는 최선
순위만) **문서 10개** 안에서 잰다 — 청크 10개 창이 아니다. 한 문서가 청크를 여러 개 올리면 두
읽기의 숫자가 크게 갈리기 때문에 여기서 못박는다.

**검정 규칙도 숫자가 나오기 전에 못박는다** (§4.3):

- 질의별 승패는 키워드 다리 **Recall@10**, 동점이면 **MRR@10** 으로 깬다. 265문서에서 Recall 은
  대부분 동점이라(양쪽 다 정답을 찾되 순위만 다름) 동점을 그냥 버리면 분해가 옮기는 정보를
  통째로 버리게 된다.
- 양측 정확 이항검정(부호검정), α=0.05.
- **불일치쌍 6개 미만이면 p 값을 내지 않는다.** 6–0 이라야 p≈0.031 이므로, 그 아래에서는 검정이
  애초에 결론을 낼 수 없다. 그 상태를 "차이 없음" 으로 적는 것이 지표가 자기 둔감함을
  세탁하는 방법이다. 우리는 **"검정력 부족"** 이라고 쓴다.

지표는 **다리별**로 낸다. 토크나이저는 키워드 다리 말고는 건드리지 못한다 — 융합 숫자로 읽은
토크나이저 판정은 바뀔 수 없는 다리에 희석된 판정이다.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

METRIC_K = 10
ALPHA = 0.05
MIN_DISCORDANT = 6          # 양측 정확 이항검정이 α=0.05 에 도달할 수 있는 최소 불일치쌍


# ── 순수 채점 ────────────────────────────────────────────────────────────────

class OrphanedStoreError(RuntimeError):
    """청크→문서 매핑이 비었거나 순위에 매핑 없는 rid 가 섞였다 — 채점하면 안 되는 상태."""


@dataclass
class AbstentionResult:
    """답변불가 라벨에 대한 채점 — **분모 40 과 섞지 않는다.**

    §4.3 의 분모는 답변가능 40 이고 그건 그대로다. 답변불가 5건은 다른 것을 재기 때문에 따로
    센다: 검색 품질이 아니라 **모르는 것을 모른다고 하는가** 이다.

    지금까지 이 5건은 어느 집계에도 안 들어갔다 — 기권이 답변 문장 안에만 있어서 기계가 읽을 수
    없었기 때문이다(§2.3). `abstained` 플래그가 생겨서 이제 셀 수 있다.
    """
    total: int = 0
    abstained: int = 0
    answered: list[str] = field(default_factory=list)   # 기권했어야 하는데 답한 질의

    @property
    def rate(self) -> float:
        return self.abstained / self.total if self.total else 0.0


def score_abstention(results: dict[str, bool], unanswerable: list[dict]) -> AbstentionResult:
    """`{질의id: abstained}` → 집계.

    **답을 지어내는 것이 기권 실패다.** 근거가 하나도 없을 때만 기권하는 현재 구현에서는 이 값이
    0 에 가깝게 나올 것이다 — BM25 는 거의 언제나 무언가를 돌려주니까. 그것은 이 채점기의 실패가
    아니라 **측정된 사실**이고, 0 이라는 숫자가 있어야 고칠지 말지를 정할 수 있다.
    """
    r = AbstentionResult(total=len(unanswerable))
    for q in unanswerable:
        if results.get(q["id"]):
            r.abstained += 1
        else:
            r.answered.append(q["id"])
    return r


def collapse_to_documents(
    ranked_chunks: list[tuple[str, int]],
    chunk_doc: dict[str, str],
    limit: int = METRIC_K,
) -> list[str]:
    """(청크 rid, 순위) 목록 → 문서 목록. 같은 문서는 최선 순위 한 번만, 상위 `limit` 개.

    **빈 매핑은 0점이 아니라 중단이다.** `clean_db` 가 `chunks` 를 TRUNCATE 하면 평가 저장소는
    살아남고 참조만 끊긴다. 그 상태로 접으면 모든 다리가 빈 목록을 돌려주고 두 실험군이 나란히
    `Recall@10 = 0.000` 을 낸다 — 2026-08-05 에 실제로 나온, 기제상 불가능한 숫자다. 공식 경로는
    `verify_arm` 이 막지만 그 검사를 우회하는 코드가 여기까지 온다. 여기서 멈춘다.
    """
    if ranked_chunks and not chunk_doc:
        raise OrphanedStoreError(
            "청크→문서 매핑이 비었는데 순위 결과가 있다 — 평가 저장소가 고아 상태다. "
            "`ko_eval_embed_compare restore-chunks` 로 팩을 다시 적재해라 "
            "(임베딩은 보존된다).")
    if ranked_chunks:
        unmapped = [rid for rid, _ in ranked_chunks if rid not in chunk_doc]
        if len(unmapped) == len(ranked_chunks):
            raise OrphanedStoreError(
                f"순위에 오른 {len(unmapped)}건이 모두 매핑에 없다 — 저장소가 다른 적재본의 것이다. "
                "`restore-chunks` 가 rid 와 입력 해시를 함께 대조한다.")

    seen: dict[str, int] = {}
    for rid, rank in sorted(ranked_chunks, key=lambda x: x[1]):
        doc = chunk_doc.get(rid)
        if doc is not None and doc not in seen:
            seen[doc] = rank
    return list(seen.keys())[:limit]


@dataclass
class QueryScore:
    """한 질의의 한 다리 점수."""
    qid: str
    recall: float
    rr: float

    @property
    def miss(self) -> bool:
        return self.rr == 0.0


def score_query(qid: str, docs: list[str], gold: list[str] | set[str]) -> QueryScore:
    """Recall@10 / MRR@10. gold 가 비면(답변불가) 이 함수를 부르지 않는다 — §4.3 분모는 40."""
    gold_set = set(gold)
    if not gold_set:
        raise ValueError(f"{qid}: gold 가 빈 질의는 집계 대상이 아니다")
    top = docs[:METRIC_K]
    hit = [d for d in top if d in gold_set]
    rr = 1.0 / (top.index(hit[0]) + 1) if hit else 0.0
    return QueryScore(qid=qid, recall=len(hit) / len(gold_set), rr=rr)


@dataclass
class LegResult:
    """한 다리의 집계. `n` 은 답변가능 질의 수(=분모)."""
    leg: str
    scores: list[QueryScore] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.scores)

    @property
    def recall(self) -> float:
        return sum(s.recall for s in self.scores) / self.n if self.n else 0.0

    @property
    def mrr(self) -> float:
        return sum(s.rr for s in self.scores) / self.n if self.n else 0.0

    @property
    def misses(self) -> int:
        return sum(1 for s in self.scores if s.miss)

    def by_stratum(self, strata: dict[str, str]) -> dict[str, dict]:
        """층별 수치 — **서술용이다.** 8건짜리 층은 아무것도 결정하지 못한다 (§4.3)."""
        out: dict[str, dict] = {}
        for s in self.scores:
            b = out.setdefault(strata.get(s.qid, "?"), {"n": 0, "recall": 0.0, "mrr": 0.0, "misses": 0})
            b["n"] += 1
            b["recall"] += s.recall
            b["mrr"] += s.rr
            b["misses"] += int(s.miss)
        for b in out.values():
            b["recall"] /= b["n"]
            b["mrr"] /= b["n"]
        return out


# ── 순수 판정 ────────────────────────────────────────────────────────────────

def outcomes(a: list[QueryScore], b: list[QueryScore]) -> tuple[int, int, int]:
    """(a 승, a 패, 무). Recall 우선, 동점이면 MRR 로 깬다 (§4.3)."""
    bb = {s.qid: s for s in b}
    wins = losses = ties = 0
    for sa in a:
        sb = bb.get(sa.qid)
        if sb is None:
            continue
        if sa.recall != sb.recall:
            wins, losses = (wins + 1, losses) if sa.recall > sb.recall else (wins, losses + 1)
        elif sa.rr != sb.rr:
            wins, losses = (wins + 1, losses) if sa.rr > sb.rr else (wins, losses + 1)
        else:
            ties += 1
    return wins, losses, ties


def sign_test_p(wins: int, losses: int) -> float:
    """양측 정확 이항검정(p=0.5). 불일치쌍만 센다."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


@dataclass
class Verdict:
    """판정 결과. `underpowered` 면 p 값을 내지 않는다 — 그건 '차이 없음' 과 다른 진술이다."""
    wins: int
    losses: int
    ties: int
    underpowered: bool
    p: float | None
    decision: str

    @property
    def discordant(self) -> int:
        return self.wins + self.losses


def verdict(wins: int, losses: int, ties: int, name_a: str = "A", name_b: str = "B") -> Verdict:
    discordant = wins + losses
    if discordant < MIN_DISCORDANT:
        return Verdict(
            wins, losses, ties, underpowered=True, p=None,
            decision=(f"검정력 부족 — 불일치쌍 {discordant}건(<{MIN_DISCORDANT})으로는 "
                      f"α={ALPHA} 에서 어떤 결론도 나올 수 없다. 이것은 '차이 없음' 이 아니다."),
        )
    p = sign_test_p(wins, losses)
    if p >= ALPHA:
        decision = f"이 표본 크기에서 측정 가능한 차이 없음 (p={p:.3f}) — 현직({name_b}) 유지"
    else:
        ahead = name_a if wins > losses else name_b
        decision = f"{ahead} 우세 (p={p:.3f})"
    return Verdict(wins, losses, ties, underpowered=False, p=p, decision=decision)


# ── 적재·실행 (DB) ───────────────────────────────────────────────────────────

async def load_pack(pack_dir: Path, tenant: str, con, config: dict | None = None) -> dict[str, str]:
    """팩을 버려도 되는 테넌트에 적재하고 **청크 rid → 팩 상대 경로** 매핑을 돌려준다.

    프로덕션 청커(`chunk_document`)를 그대로 쓴다. 평가용으로 따로 쪼개면 재는 대상이 달라진다.
    """
    from nexus.index.bm25 import index_chunk_bm25
    from nexus.ingest.chunker import chunk_document
    from nexus.rid import chunk_rid, doc_rid

    docs_dir = pack_dir / "docs"
    chunk_doc: dict[str, str] = {}
    to_index: list[tuple[str, object]] = []

    # rid 는 **테넌트를 포함한 uri 에서** 결정적으로 만든다. 두 토크나이저 실험군은 서로 다른 테넌트에
    # 같은 문서를 적재하는데, `documents.rid` 는 테넌트가 아니라 전역 기본키다 — 경로만으로 만든
    # rid 는 두 번째 실험군에서 충돌한다.
    for f in sorted(docs_dir.rglob("*.md")):
        rel = f.relative_to(docs_dir).as_posix()
        text = f.read_text(encoding="utf-8")
        uri = f"{tenant}:{rel}"
        drid = doc_rid(uri)
        await con.execute(
            "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, title, status) "
            "VALUES ($1,$2,$3,'h','h',$4,'active')",
            drid, tenant, uri, rel)

        for cd in chunk_document(text, language="ko", config=config):
            crid = chunk_rid(drid, cd.section_path or "root", cd.chunk_index)
            await con.execute(
                "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, chunk_text, section_path, "
                "chunk_index, status, hash) VALUES ($1,$2,$3,$4,$5,$6,$7,'active','h')",
                crid, tenant, uri, drid, cd.chunk_text,
                cd.section_path or "root", cd.chunk_index)
            chunk_doc[crid] = rel
            to_index.append((crid, cd))

    for crid, cd in to_index:
        await index_chunk_bm25(crid, _IndexableChunk(cd))
    return chunk_doc


class _IndexableChunk:
    """`index_chunk_bm25` 가 기대하는 최소 형태 (get_search_text 경유용)."""

    def __init__(self, cd) -> None:
        self.chunk_text = cd.chunk_text
        self.section_path = cd.section_path or "root"
        self.context_prefix = None


async def run_keyword_leg(labels: dict, tenant: str, chunk_doc: dict[str, str],
                          top_k: int = 20) -> LegResult:
    """답변가능 질의만 키워드 다리로 돌려 점수를 낸다 (§4.3 분모 = 40)."""
    from nexus.search import hybrid

    result = LegResult(leg="keyword")
    for q in labels["queries"]:
        if not q.get("answerable"):
            continue
        hits, _top = await hybrid._bm25_search(q["query"], tenant, "INTERNAL", top_k)
        docs = collapse_to_documents(hits, chunk_doc)
        result.scores.append(score_query(q["id"], docs, q["gold"]))
    return result


RRF_K = 60      # config.yaml `search.rrf_k` 기본값. 융합은 프로덕션 함수를 그대로 부른다.


async def run_legs(labels: dict, tenant: str, chunk_doc: dict[str, str],
                   vector_search=None, top_k: int = 20) -> dict[str, LegResult]:
    """키워드·벡터·융합 다리를 한 번에 돌린다 (SPEC-nexus-korean-embedding-comparison §8 Unit 2).

    **융합은 프로덕션 `_rrf_fusion` 을 그대로 부른다.** 평가용으로 다시 구현하면 fused 숫자가
    사용자가 겪는 것과 다른 뜻이 되고, 그건 "사용자가 보는 결과" 를 재겠다는 이 다리의 존재
    이유를 지운다.

    `vector_search` 는 `(query_text) -> list[(chunk_rid, rank)]` 코루틴. 없으면 키워드만 돈다.
    """
    from nexus.search import hybrid

    legs = {"keyword": LegResult(leg="keyword")}
    if vector_search is not None:
        legs["vector"] = LegResult(leg="vector")
        legs["fused"] = LegResult(leg="fused")

    for q in labels["queries"]:
        if not q.get("answerable"):
            continue
        kw, _top = await hybrid._bm25_search(q["query"], tenant, "INTERNAL", top_k)
        legs["keyword"].scores.append(
            score_query(q["id"], collapse_to_documents(kw, chunk_doc), q["gold"]))

        if vector_search is None:
            continue
        vec = await vector_search(q["query"])
        legs["vector"].scores.append(
            score_query(q["id"], collapse_to_documents(vec, chunk_doc), q["gold"]))

        fused_rows = hybrid._rrf_fusion(kw, vec, k=RRF_K)
        fused = [(row["rid"], i + 1) for i, row in enumerate(fused_rows)]
        legs["fused"].scores.append(
            score_query(q["id"], collapse_to_documents(fused, chunk_doc), q["gold"]))

    return legs


async def leg_top_documents(labels: dict, tenant: str, chunk_doc: dict[str, str],
                            vector_search=None, top_k: int = 20,
                            depth: int = METRIC_K) -> dict[str, dict[str, list[str]]]:
    """풀 판정용 — **다리별** 질의별 상위 문서. 융합도 다리다 (§4.5): RRF 가 11~20위를 top-10 으로
    끌어올릴 수 있어서, 융합을 빼고 판정하면 그 문서는 무판정으로 비관련 처리된다."""
    from nexus.search import hybrid

    out: dict[str, dict[str, list[str]]] = {"keyword": {}}
    if vector_search is not None:
        out["vector"], out["fused"] = {}, {}

    for q in labels["queries"]:
        if not q.get("answerable"):
            continue
        kw, _top = await hybrid._bm25_search(q["query"], tenant, "INTERNAL", top_k)
        out["keyword"][q["id"]] = collapse_to_documents(kw, chunk_doc, limit=depth)
        if vector_search is None:
            continue
        vec = await vector_search(q["query"])
        out["vector"][q["id"]] = collapse_to_documents(vec, chunk_doc, limit=depth)
        fused_rows = hybrid._rrf_fusion(kw, vec, k=RRF_K)
        out["fused"][q["id"]] = collapse_to_documents(
            [(r["rid"], i + 1) for i, r in enumerate(fused_rows)], chunk_doc, limit=depth)
    return out


async def top_documents(query: str, tenant: str, chunk_doc: dict[str, str],
                        top_k: int = 20, depth: int = METRIC_K) -> list[str]:
    """풀 판정용 — 한 질의의 상위 문서 목록 (§4.2 의 풀 깊이는 지표 깊이와 같다)."""
    from nexus.search import hybrid

    hits, _top = await hybrid._bm25_search(query, tenant, "INTERNAL", top_k)
    return collapse_to_documents(hits, chunk_doc, limit=depth)


# ── 리포트 ───────────────────────────────────────────────────────────────────

def gate_provenance(root: Path | None = None) -> dict[str, str]:
    """이 숫자가 **게이트 안에서** 만들어졌는지를 리포트가 스스로 말하게 한다.

    ADR-0009 §3(ii) 와 `SPEC-nexus-ko-eval-pool-sensitivity` §0 이 기록한 결함은 같은 모양이다 —
    측정이 승인보다 먼저 이뤄지고, SPEC 이 나중에 그 숫자를 인용한다. Arbiter 게이트는 **편집**을
    막지 **측정**을 막지 않으므로 예방은 못 한다. 대신 **보이게** 한다: 리포트 머리말이 활성 spec 을
    달고 나오면, 게이트 밖 숫자를 인용하는 SPEC 은 인용하는 순간 그 사실이 함께 읽힌다.

    세 상태를 구분한다. **의미가 있는 것은 양성 신호뿐이다** — spec id 가 찍힌 리포트는 무장된
    게이트 아래에서 나왔다는 뜻이다. `none`(마커 디렉터리는 있는데 활성 spec 이 없다)과
    `unknown`(마커 디렉터리 자체가 없다 — 게이트를 여기서 한 번도 무장한 적이 없거나, 컨테이너에
    리포가 안 마운트됐다)은 **둘 다 "게이트 안이었음이 확인되지 않음"** 이지만 이유가 다르므로
    뭉치지 않는다. `.arbiter/` 는 `begin_implementation` 이 처음 만들기 때문에 `unknown` 은 로컬
    에서도 흔한 상태다 — 그래서 이 필드는 **부재를 고발하는 장치가 아니라 존재를 증명하는 장치**다.
    """
    env = os.getenv("ARBITER_ACTIVE_SPEC")
    if env:
        return {"active_spec": env, "source": "ARBITER_ACTIVE_SPEC (선언값)"}
    base = root or Path(__file__).resolve().parents[2]
    marker_dir = base / ".arbiter"
    if not marker_dir.exists():
        return {"active_spec": "unknown", "source": f"{marker_dir} 없음 — 게이트 무장 이력이 없거나 리포가 안 보인다"}
    marker = marker_dir / "active.json"
    if not marker.exists():
        return {"active_spec": "none", "source": "활성 spec 없음 — 게이트 밖에서 만든 숫자다"}
    try:
        return {"active_spec": json.loads(marker.read_text(encoding="utf-8"))["spec_id"],
                "source": ".arbiter/active.json"}
    except Exception as e:  # noqa: BLE001 — 읽을 수 없는 마커는 '없음' 이 아니다
        return {"active_spec": "unknown", "source": f"마커를 읽을 수 없다: {e}"}


def render_report(meta: dict, legs: list[LegResult], strata: dict[str, str],
                  verdict_obj: Verdict | None = None) -> str:
    """커밋되는 산출물. **팩이 khala 자신의 코퍼스가 아니라는 사실을 머리말에 적는다** (§4.1)."""
    out = ["# 한국어 검색 평가 실행 보고", ""]
    gate = gate_provenance()
    meta = {**meta, "게이트": f"{gate['active_spec']} ({gate['source']})"}
    for k, v in meta.items():
        out.append(f"- **{k}**: {v}")
    out += ["", "> Pack A 는 khala 자신의 코퍼스가 아니라 같은 종류의 공개 대역 코퍼스다.",
            "> 이 실행만으로 ADR-0008 §5(b) 가 닫히지 않는다.", ""]

    out += ["## 다리별 (답변가능 질의 기준)", "",
            "| 다리 | n | Recall@10 | MRR@10 | 미스 |", "|---|---:|---:|---:|---:|"]
    for leg in legs:
        out.append(f"| {leg.leg} | {leg.n} | {leg.recall:.3f} | {leg.mrr:.3f} | {leg.misses} |")

    for leg in legs:
        out += ["", f"### 층별 — {leg.leg} (서술용, 아무것도 결정하지 않는다)", "",
                "| 층 | n | Recall@10 | MRR@10 | 미스 |", "|---|---:|---:|---:|---:|"]
        for stratum, b in sorted(leg.by_stratum(strata).items()):
            out.append(f"| {stratum} | {b['n']} | {b['recall']:.3f} | {b['mrr']:.3f} | {b['misses']} |")

    if verdict_obj is not None:
        out += ["", "## 판정", "",
                f"- 승 {verdict_obj.wins} · 패 {verdict_obj.losses} · 무 {verdict_obj.ties} "
                f"(불일치쌍 {verdict_obj.discordant})",
                f"- **{verdict_obj.decision}**"]
    return "\n".join(out) + "\n"
