"""지연 측정의 두 가지 성질: 규칙은 미리 고정돼 있고, 보고서에는 코퍼스가 없다
(SPEC-nexus-embedding-cutover-seam §4.7).

이 리포지토리는 공개이고 배포 코퍼스는 실제 조직 문서다. 그래서 질의는 **커밋된 손글씨 세트**에서만
오고, 렌더러는 집계 레코드의 필드만 찍는다 — 질의 문자열에서 보고서로 가는 경로가 없다는 것을
여기서 측정한다. "조심하겠다" 는 보증이 아니다.
"""

from __future__ import annotations

import pytest

from scripts.latency_probe import (
    P95_ABSOLUTE_MAX_MS,
    P95_RATIO_MAX,
    Measurement,
    Percentiles,
    load_queries,
    render_report,
    verdict,
)

DISTINCTIVE = "해파리 양식장 위탁 운영 규정"      # 세트에 실재하는 질의 — 보고서에 나오면 안 된다


def _m(label: str, p95: float, **kw) -> Measurement:
    return Measurement(kind="search", label=label, model=kw.get("model", "nomic-embed-text"),
                       backend=kw.get("backend", "ollama"), column=kw.get("column", "embedding"),
                       queries=20, warmups=20, active_chunks=167,
                       latency=Percentiles(n=200, min_ms=10, p50_ms=p95 / 2, p95_ms=p95,
                                           max_ms=p95 * 2))


# ── 사전등록 규칙 ────────────────────────────────────────────────────────────


def test_the_rule_is_two_conditions_and_both_must_hold():
    """배율만 보면 느린 배포에서 무한정 느려질 수 있고, 절대값만 보면 급격한 퇴행을 놓친다."""
    assert verdict(_m("before", 100), _m("after", 140))[0] is True
    assert verdict(_m("before", 100), _m("after", 160))[0] is False, "배율 초과"
    assert verdict(_m("before", 1200), _m("after", 1600))[0] is False, "절대값 초과"


def test_the_thresholds_are_the_ones_registered_in_the_spec():
    """숫자를 나중에 고치면 결론을 고르는 것이 된다 — 값 자체를 못 박는다."""
    assert (P95_RATIO_MAX, P95_ABSOLUTE_MAX_MS) == (1.5, 1500.0)


def test_the_reason_names_both_sides_of_the_comparison():
    ok, reason = verdict(_m("before", 100), _m("after", 160))
    assert ok is False and "100" in reason and "160" in reason


# ── 보고서에 코퍼스가 없다 ───────────────────────────────────────────────────


def test_the_report_renders_only_the_aggregate_record():
    """렌더러는 Measurement 의 필드만 본다. 질의 문자열은 인자로 들어오지도 않는다."""
    before, after = _m("before", 100), _m("after", 120, model="KURE-v1",
                                          column="embedding_1024", backend="sidecar")
    text = render_report(before, after, [], date="2026-08-05", machine="test")

    assert DISTINCTIVE not in text
    for query in load_queries():
        assert query not in text, f"질의가 보고서에 새어 나왔다: {query[:20]}"
    # 담아야 할 것은 담는다 — 아무것도 안 찍는 렌더러도 위 단언을 통과한다
    assert "p95" in text and "167" in text and "KURE-v1" in text


def test_the_measurement_record_has_no_place_to_put_a_query():
    """필드를 늘려 질의를 담기 시작하면 그때부터는 '조심' 이 유일한 방어가 된다."""
    fields = set(Measurement("search", "x").__dict__)
    assert "queries" in fields and isinstance(Measurement("search", "x").queries, int)
    assert not {f for f in fields if f in {"query", "query_text", "samples", "sample_queries"}}


# ── 질의 세트 ────────────────────────────────────────────────────────────────


def test_the_query_set_is_committed_and_non_trivial():
    queries = load_queries()
    assert len(queries) >= 15, "p95 를 흔들지 않으려면 세트가 충분히 넓어야 한다"
    assert len(set(queries)) == len(queries), "중복 질의는 캐시를 측정하는 것에 가깝다"


# ── 계측기 자체 — 동시성을 정말 유지하는가 ──────────────────────────────────


@pytest.mark.asyncio
async def test_the_driver_keeps_the_load_up_instead_of_running_in_batches():
    """배치로 `gather` 하면 각 배치의 꼬리가 다음 배치를 막아 **실제보다 낮은 동시성**을 측정한다.

    그래서 실제로 몇 개가 동시에 떠 있었는지를 센다 — 부하 측정에서 이게 틀리면 나머지 숫자는
    전부 다른 질문의 답이다.
    """
    import asyncio

    from scripts.latency_probe import _drive

    inflight, peak = 0, 0

    async def worker(index: int) -> bool:
        nonlocal inflight, peak
        inflight += 1
        peak = max(peak, inflight)
        await asyncio.sleep(0.01)
        inflight -= 1
        return True

    samples, errors, rps = await _drive(worker, total=20, concurrency=4, warmups=4)

    assert peak == 4, f"동시에 떠 있던 최대 요청이 4가 아니라 {peak}"
    assert len(samples) == 20, "워밍업은 창에서 빠지고 나머지는 전부 세야 한다"
    assert errors == 0 and rps > 0


@pytest.mark.asyncio
async def test_the_driver_counts_failures_without_putting_them_in_the_latency():
    """실패한 요청의 지연을 표본에 넣으면 '빨리 실패하는' 배포가 빨라 보인다."""
    from scripts.latency_probe import _drive

    async def worker(index: int) -> bool:
        return index % 2 == 0

    samples, errors, _ = await _drive(worker, total=10, concurrency=2, warmups=0)
    assert errors == 5 and len(samples) == 5


def test_the_concurrency_budget_is_the_same_number_the_cutover_registered():
    """상황마다 예산을 새로 정하면 그건 예산이 아니라 결론이다."""
    from scripts.latency_probe import CONCURRENCY_P95_MAX_MS, CONCURRENCY_TARGET

    assert CONCURRENCY_TARGET == 4
    assert CONCURRENCY_P95_MAX_MS == P95_ABSOLUTE_MAX_MS


@pytest.mark.parametrize("shape", ["조사", "복합", "혼용"])
def test_the_set_covers_the_shapes_it_claims_to(shape):
    """세트의 목적은 정답률이 아니라 **경로의 모양**이다 — 한 모양만 있으면 그 주장이 거짓이 된다."""
    queries = load_queries()
    has_particle = any(q.endswith(("나요", "나", "가요")) for q in queries)
    has_compound = any(len(q.split()) >= 2 and all(len(w) >= 2 for w in q.split())
                       for q in queries)
    has_mixed = any(any(c.isascii() and c.isalpha() for c in q) for q in queries)
    assert {"조사": has_particle, "복합": has_compound, "혼용": has_mixed}[shape]
