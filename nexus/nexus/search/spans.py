"""단계 span 조립 — **순수 데이터**. DB 도, 설정 읽기도 여기 없다.

왜 갈라놨나: 테스트 표면의 대부분이 DB 없이 돌아야 하고, 저장은 파괴 경로 시험을 위해
갈아 끼울 수 있어야 한다. `search/signals.py` 가 순수 `extract_signals` 와 `_persist` 를
가른 것과 같은 관례다.

⛔ **비율을 만들지 않는다. 개수만 남긴다** — 비율은 분모를 지운다 (`search/evidence_share.py`).
⛔ **문턱을 두지 않는다.** 첫 회차는 관측이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: 경로 이름이 아니라 **지표** 이름이다. ts_rank_cd 는 유사도(클수록 좋음),
#: cosine_distance 는 거리(작을수록 좋음) — 극성이 반대라 span 을 넘어 비교하면 안 된다.
SCORE_KIND = {"bm25": "ts_rank_cd", "vector": "cosine_distance"}

_SCALAR = (str, int, float, bool, type(None))


@dataclass(frozen=True)
class Candidate:
    rank: int                       # 그 단계의 **입력** 순서, 1부터
    doc_rid: str
    chunk_rid: str | None = None    # 보존 옵션 3 에서 비워진다
    raw_score: float | None = None
    dropped: bool = False           # diversify 전용: 이 행이 잘렸다


@dataclass
class StageSpan:
    seq: int
    stage: str
    channel: str | None = None
    leg: str | None = None
    n_in: int | None = None
    n_out: int | None = None
    fired: bool = True
    score_kind: str | None = None
    index_generation: str | None = None
    candidates_expected: int | None = None
    candidates_cap: int | None = None
    detail: dict = field(default_factory=dict)
    candidates: list[Candidate] = field(default_factory=list)


def _check_scalar(detail: dict) -> dict:
    bad = [k for k, v in detail.items() if not isinstance(v, _SCALAR)]
    if bad:
        raise ValueError(f"detail must hold scalar values only; not scalar: {bad}")
    return detail


class SpanSet:
    """한 요청의 span 들. `seq` 는 1부터 조밀하다."""

    def __init__(self, max_candidates: int, index_generation: str | None = None):
        self._max = max_candidates
        self._generation = index_generation
        self.spans: list[StageSpan] = []

    def _add(self, stage: str, candidates: list[Candidate], *, cap_exempt: bool = False,
             **kw) -> StageSpan:
        detail = _check_scalar(kw.pop("detail", {}))
        cap = None if cap_exempt else self._max
        kept = candidates if cap is None else candidates[:cap]
        span = StageSpan(
            seq=len(self.spans) + 1, stage=stage, detail=detail,
            index_generation=self._generation,
            candidates_expected=len(candidates), candidates_cap=cap,
            candidates=kept, **kw,
        )
        self.spans.append(span)
        return span

    def add_leg(self, *, channel: str, leg: str, candidates: list[Candidate],
                fired: bool = True) -> StageSpan:
        return self._add("leg", candidates, channel=channel, leg=leg, fired=fired,
                         n_in=None, n_out=len(candidates), score_kind=SCORE_KIND[leg],
                         detail={"pool_size": len(candidates)})

    def add_fusion(self, *, candidates: list[Candidate], rrf_k: int,
                   n_channels: int) -> StageSpan:
        return self._add("fusion", candidates, n_in=None, n_out=len(candidates),
                         score_kind="rrf",
                         detail={"rrf_k": rrf_k, "n_channels": n_channels})

    def add_diversify(self, *, candidates: list[Candidate], top_k: int, per_doc_cap: int,
                      fired: bool = True) -> StageSpan:
        # 상한 면제: 잘린 행이 곧 진단 자료라 입력 순위로 자르면 정확히 그것을 버린다.
        kept = sum(1 for c in candidates if not c.dropped)
        return self._add("diversify", candidates, cap_exempt=True, fired=fired,
                         n_in=len(candidates), n_out=kept,
                         detail={"top_k": top_k, "per_doc_cap": per_doc_cap})

    def add_section_fill(self, *, candidates: list[Candidate], trigger_saturated: bool,
                         fired: bool = True) -> StageSpan:
        return self._add("section_fill", candidates, fired=fired,
                         n_in=None, n_out=len(candidates),
                         detail={"trigger_saturated": trigger_saturated})

    def add_packet(self, *, candidates: list[Candidate], n_snippets: int,
                   n_graph_edges: int) -> StageSpan:
        # 그래프 findings 는 청크가 아니라 doc_rid 가 없다 → 후보 행을 안 만들고 개수만 남긴다.
        return self._add("packet", candidates, n_in=None, n_out=len(candidates),
                         detail={"n_snippets": n_snippets,
                                 "n_graph_edges": n_graph_edges})

    def add_answer(self, *, n_in: int | None, fired: bool = True, **detail) -> StageSpan:
        # answer 는 후보가 없는 말단 단계라 상한이 뜻이 없다 — cap_exempt 로 candidates_cap=None,
        # candidates_expected=0 을 보장한다. (일반 경로를 타면 candidates_cap 이 max 로 채워진다.)
        return self._add("answer", [], cap_exempt=True, n_in=n_in, n_out=None, fired=fired,
                         detail=detail)
