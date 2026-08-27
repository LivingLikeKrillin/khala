"""컷오버가 지불해야 하는 지연 측정 (SPEC-nexus-embedding-cutover-seam §4.7).

교체 SPEC §4.1 은 자기 표를 스스로 철회했다 — KURE 수치는 **in-process** 라이브러리 호출이었고
프로덕션 경로는 사이드카다. 그래서 "어떤 컷오버 결정보다 먼저 그 경로 위에서 다시 잰다" 고 적혔고,
§4.6 은 `/search` end-to-end p50/p95 를 before/after 로 요구했다. 둘 다 없었다. 이 스크립트가 그
빚이다.

**규칙은 숫자를 보기 전에 고정돼 있다**: `/search` p95(after) ≤ 1.5 × p95(before) **이고**
≤ 1500 ms. 둘 중 하나라도 어기면 같은 세션에 flip 을 되돌린다. 나중에 규칙을 정하는 것은 결론을
고르는 것이다.

**보고서에는 코퍼스 내용이 들어가지 않는다.** 질의는 리포에 커밋된 고정 세트에서만 오고, 렌더러는
집계 레코드의 필드만 찍는다 — 질의 문자열에서 보고서로 가는 경로가 없다(테스트가 그 형태를 잰다).

사용:
    python -m scripts.latency_probe embed  --model KURE-v1 --backend sidecar
    python -m scripts.latency_probe search --label before --n 200
    python -m scripts.latency_probe report --before before.json --after after.json --out report.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx
import yaml

QUERIES_PATH = Path(__file__).resolve().parents[1] / "tests" / "eval" / "latency_queries.yaml"

#: 사전등록 규칙 (§4.7). 이 배포의 flip 판정에만 쓰이고, 다른 코퍼스는 자기 규칙을 다시 등록한다.
P95_RATIO_MAX = 1.5
P95_ABSOLUTE_MAX_MS = 1500.0


def load_queries() -> list[str]:
    data = yaml.safe_load(QUERIES_PATH.read_text(encoding="utf-8"))
    queries = [str(q) for q in data.get("queries", [])]
    if not queries:
        raise SystemExit(f"질의 세트가 비었다: {QUERIES_PATH}")
    return queries


@dataclass
class Percentiles:
    """**집계만** 담는다 — 이 레코드에 질의 문자열이 들어갈 자리는 없다 (§4.7 (i))."""
    n: int = 0
    min_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    max_ms: float = 0.0

    @classmethod
    def of(cls, samples: list[float]) -> "Percentiles":
        if not samples:
            return cls()
        ordered = sorted(samples)
        # p95 = 위에서 5% 지점의 **관측값**. 보간하지 않는다 — 표본이 200이면 190번째다.
        idx = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
        return cls(n=len(ordered), min_ms=round(ordered[0], 2),
                   p50_ms=round(statistics.median(ordered), 2),
                   p95_ms=round(ordered[idx], 2), max_ms=round(ordered[-1], 2))


#: 동시성 판정 (§4.7 이 "재측정 트리거는 동시성" 이라고 남긴 자리). 팀 배포의 현실적 동시 검색자
#: 수를 4로 잡고, 그 지점의 절대 예산은 컷오버 때 사전등록한 것과 **같은 값**을 쓴다 — 예산을
#: 상황마다 새로 정하면 그건 예산이 아니다.
CONCURRENCY_TARGET = 4
CONCURRENCY_P95_MAX_MS = P95_ABSOLUTE_MAX_MS


@dataclass
class Measurement:
    kind: str                       # "embed" | "search"
    label: str                      # "before" | "after" | 자유 라벨
    model: str = ""
    backend: str = ""
    column: str = ""
    revision: str | None = None
    queries: int = 0                # 세트 크기(문자열이 아니라 개수)
    warmups: int = 0
    active_chunks: int | None = None
    latency: Percentiles = field(default_factory=Percentiles)
    errors: int = 0
    concurrency: int = 1            # 동시에 떠 있는 요청 수
    throughput_rps: float = 0.0     # 완료/초 — 지연만 보면 포화와 정체를 구분 못 한다
    route: str = ""                 # search 전용: hybrid_only | keyword_only(임베딩 없는 대조군)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


async def _generation() -> dict:
    """지금 이 배포가 무엇으로 도는가 — 보고서가 스스로 답해야 하는 질문이다."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        token = (await client.get("http://localhost:8000/auth/dev-token")).json()["data"]["token"]
        status = (await client.get("http://localhost:8000/status",
                                   headers={"Authorization": f"Bearer {token}"})).json()["data"]
    return {"token": token, "status": status}


async def measure_embed(model: str, backend: str, n: int, warmups: int) -> Measurement:
    """질의 임베딩 지연 — **양쪽 다 HTTP 경계 너머로** 잰다 (§4.1 이 철회한 표의 자리)."""
    from nexus.providers.embedding import MODEL_DIMENSIONS, EmbeddingService

    svc = EmbeddingService(model=model, backend=backend, dimensions=MODEL_DIMENSIONS[model])
    queries = load_queries()
    samples: list[float] = []
    errors = 0
    for i in range(warmups + n):
        query = queries[i % len(queries)]
        t0 = asyncio.get_event_loop().time()
        try:
            await svc.embed_query(query)
        except Exception:                       # noqa: BLE001 — 실패도 예산의 일부다
            errors += 1
            continue
        elapsed = (asyncio.get_event_loop().time() - t0) * 1000
        if i >= warmups:
            samples.append(elapsed)
    return Measurement(kind="embed", label=f"{model}/{backend}", model=model, backend=backend,
                       queries=len(queries), warmups=warmups,
                       latency=Percentiles.of(samples), errors=errors)


async def measure_search(label: str, n: int, warmups: int, top_k: int) -> Measurement:
    """`/search` end-to-end — 롤백 판정이 걸려 있는 예산 (§4.6)."""
    ctx = await _generation()
    token, status = ctx["token"], ctx["status"]
    queries = load_queries()
    samples: list[float] = []
    errors = 0
    async with httpx.AsyncClient(timeout=60.0) as client:
        for i in range(warmups + n):
            query = queries[i % len(queries)]
            t0 = asyncio.get_event_loop().time()
            resp = await client.post(
                "http://localhost:8000/search",
                headers={"Authorization": f"Bearer {token}"},
                json={"query": query, "top_k": top_k})
            elapsed = (asyncio.get_event_loop().time() - t0) * 1000
            if resp.status_code != 200:
                errors += 1
                continue
            if i >= warmups:
                samples.append(elapsed)
    active = sum(row["active"] for row in status.get("embedding_coverage", []) or [])
    return Measurement(
        kind="search", label=label,
        model=status.get("embedding_model", ""), backend=status.get("embedding_backend", ""),
        column=status.get("embedding_column", ""), revision=status.get("embedding_revision"),
        queries=len(queries), warmups=warmups, active_chunks=active or None,
        latency=Percentiles.of(samples), errors=errors)


async def _drive(worker, total: int, concurrency: int, warmups: int) -> tuple[list[float], int, float]:
    """동시성 `concurrency` 를 **유지하며** `total` 건을 흘린다. (표본, 오류, 초당완료).

    배치로 나눠 `gather` 하면 각 배치의 꼬리가 다음 배치를 기다리게 되어 **실제보다 낮은 동시성**을
    재게 된다. 그래서 워커를 상주시키고 공용 카운터에서 일감을 꺼낸다 — 하나가 끝나면 곧바로 다음이
    들어가므로 관측 창 내내 부하가 유지된다.
    """
    counter = {"i": 0}
    samples: list[float] = []
    errors = 0
    lock = asyncio.Lock()
    started = None

    async def _run_one(index: int) -> None:
        nonlocal errors
        t0 = asyncio.get_event_loop().time()
        ok = await worker(index)
        elapsed = (asyncio.get_event_loop().time() - t0) * 1000
        if not ok:
            errors += 1
            return
        if index >= warmups:            # 워밍업은 창에서 뺀다 — 모델·풀·JIT 의 첫 비용은 예산이 아니다
            samples.append(elapsed)

    async def _worker() -> None:
        while True:
            async with lock:
                index = counter["i"]
                counter["i"] += 1
            if index >= total + warmups:
                return
            await _run_one(index)

    started = asyncio.get_event_loop().time()
    await asyncio.gather(*[_worker() for _ in range(concurrency)])
    window = asyncio.get_event_loop().time() - started
    return samples, errors, (len(samples) / window if window else 0.0)


async def measure_search_concurrent(label: str, concurrency: int, total: int, warmups: int,
                                    top_k: int, route: str) -> Measurement:
    """부하 아래의 `/search`. `route=keyword_only` 는 **임베딩을 안 타는 대조군**이다 —
    느려지는 것이 사이드카인지 앱·DB인지는 그 대조군 없이는 말할 수 없다.
    """
    ctx = await _generation()
    token, status = ctx["token"], ctx["status"]
    queries = load_queries()

    async with httpx.AsyncClient(
            timeout=120.0, limits=httpx.Limits(max_connections=concurrency + 4)) as client:
        async def _one(index: int) -> bool:
            resp = await client.post(
                "http://localhost:8000/search",
                headers={"Authorization": f"Bearer {token}"},
                json={"query": queries[index % len(queries)], "top_k": top_k, "route": route})
            return resp.status_code == 200

        samples, errors, rps = await _drive(_one, total, concurrency, warmups)

    active = sum(row["active"] for row in status.get("embedding_coverage", []) or [])
    return Measurement(
        kind="search", label=label, model=status.get("embedding_model", ""),
        backend=status.get("embedding_backend", ""), column=status.get("embedding_column", ""),
        revision=status.get("embedding_revision"), queries=len(queries), warmups=warmups,
        active_chunks=active or None, latency=Percentiles.of(samples), errors=errors,
        concurrency=concurrency, throughput_rps=round(rps, 2), route=route)


async def measure_embed_concurrent(label: str, concurrency: int, total: int, warmups: int,
                                   url: str) -> Measurement:
    """사이드카 `/embed` 를 직접 때린다 — 앱·DB 를 경로에서 빼고 임베딩 단계만 본다."""
    queries = load_queries()

    async with httpx.AsyncClient(
            timeout=120.0, limits=httpx.Limits(max_connections=concurrency + 4)) as client:
        async def _one(index: int) -> bool:
            resp = await client.post(f"{url}/embed",
                                     json={"texts": [queries[index % len(queries)]]})
            return resp.status_code == 200

        samples, errors, rps = await _drive(_one, total, concurrency, warmups)

    return Measurement(kind="embed", label=label, model="KURE-v1", backend="sidecar",
                       queries=len(queries), warmups=warmups, latency=Percentiles.of(samples),
                       errors=errors, concurrency=concurrency, throughput_rps=round(rps, 2))


def concurrency_verdict(sweep: list[Measurement]) -> tuple[bool, str]:
    """사전등록: 동시 검색자 `CONCURRENCY_TARGET` 에서 p95 가 절대 예산 안에 있는가.

    지연만 보지 않는다 — **처리량이 꺾이는지**도 함께 읽는다. 스레드 오버섭스크립션은 지연을
    늘리면서 처리량을 *떨어뜨리는* 모양으로 나타나고, 그건 "느리다" 와 다른 병이다.
    """
    at_target = next((m for m in sweep if m.concurrency == CONCURRENCY_TARGET), None)
    if at_target is None:
        return False, f"동시성 {CONCURRENCY_TARGET} 측정이 없다 — 판정 불가"
    ok = at_target.latency.p95_ms <= CONCURRENCY_P95_MAX_MS
    peak = max(sweep, key=lambda m: m.throughput_rps)
    return ok, (f"C={CONCURRENCY_TARGET} 에서 p95 {at_target.latency.p95_ms} ms "
                f"(예산 {CONCURRENCY_P95_MAX_MS:.0f} ms) · 처리량 정점 "
                f"{peak.throughput_rps} rps @ C={peak.concurrency}")


def verdict(before: Measurement, after: Measurement) -> tuple[bool, str]:
    """사전등록 규칙을 적용한다. **숫자를 보고 규칙을 고르지 않는다.**"""
    ratio = after.latency.p95_ms / before.latency.p95_ms if before.latency.p95_ms else float("inf")
    within_ratio = ratio <= P95_RATIO_MAX
    within_absolute = after.latency.p95_ms <= P95_ABSOLUTE_MAX_MS
    ok = within_ratio and within_absolute
    reason = (f"p95 {before.latency.p95_ms} ms → {after.latency.p95_ms} ms "
              f"(×{ratio:.2f}, 한도 ×{P95_RATIO_MAX} 및 {P95_ABSOLUTE_MAX_MS:.0f} ms)")
    if not within_ratio:
        reason += " — 배율 초과"
    if not within_absolute:
        reason += " — 절대값 초과"
    return ok, reason


def render_report(before: Measurement, after: Measurement,
                  embeds: list[Measurement], date: str, machine: str) -> str:
    """집계 레코드의 필드만 찍는다. 질의 문자열은 이 함수에 **들어오지도 않는다**."""
    ok, reason = verdict(before, after)
    lines = [
        f"# 컷오버 지연 측정 — {date}",
        "",
        "> 교체 SPEC §4.1 이 철회한 in-process 표를 **배송 경로(HTTP)** 위의 수치로 대체하고,",
        "> §4.6 이 요구한 `/search` before/after 를 기록한다. 판정 규칙은 측정 전에 고정됐다:",
        f"> p95(after) ≤ {P95_RATIO_MAX}× p95(before) **이고** ≤ {P95_ABSOLUTE_MAX_MS:.0f} ms.",
        "",
        f"- 기계: {machine}",
        f"- 질의 세트: `tests/eval/latency_queries.yaml` ({before.queries}건, 커밋된 고정 세트)",
        f"- 표본: 각 {before.latency.n}회 (워밍업 {before.warmups}회 폐기)",
        "",
        "## 질의 임베딩 (HTTP 경계 너머)",
        "",
        "| 실험군 | n | p50 | p95 | max | 오류 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for m in embeds:
        lines.append(f"| {m.label} | {m.latency.n} | {m.latency.p50_ms} | {m.latency.p95_ms} "
                     f"| {m.latency.max_ms} | {m.errors} |")
    lines += [
        "",
        "## `/search` end-to-end",
        "",
        "| 시점 | 세대 | 활성 청크 | n | p50 | p95 | max | 오류 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for m in (before, after):
        gen = f"{m.model} · {m.column} · {m.backend}"
        lines.append(f"| {m.label} | {gen} | {m.active_chunks or '?'} | {m.latency.n} "
                     f"| {m.latency.p50_ms} | {m.latency.p95_ms} | {m.latency.max_ms} | {m.errors} |")
    lines += [
        "",
        f"**판정: {'통과 — flip 유지' if ok else '위반 — 같은 세션에 롤백'}** ({reason})",
        "",
        "## 이 수치가 말하지 않는 것",
        "",
        "- **모델 탓이라고 말하지 않는다.** flip 에서 모델·백엔드·HTTP 홉·새로 만든 인덱스가 함께",
        "  바뀐다. 그 묶음이 곧 프로덕션이 돌릴 것이라 예산 판정에는 맞지만, 원인 귀속에는 못 쓴다.",
        "- **다른 규모를 예측하지 않는다.** 이 코퍼스에서 `lists=1` 이면 인덱스는 사실상 전수 스캔이고",
        "  고정 오버헤드가 지배한다. 큰 코퍼스는 다시 재고 자기 규칙을 다시 등록한다.",
    ]
    return "\n".join(lines) + "\n"


def _run(coro):
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(coro)


def main() -> int:
    ap = argparse.ArgumentParser(description="컷오버 지연 측정")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_embed = sub.add_parser("embed")
    p_embed.add_argument("--model", required=True)
    p_embed.add_argument("--backend", required=True, choices=["ollama", "sidecar"])
    p_embed.add_argument("--n", type=int, default=200)
    p_embed.add_argument("--warmups", type=int, default=20)
    p_embed.add_argument("--out", type=Path)

    p_search = sub.add_parser("search")
    p_search.add_argument("--label", required=True)
    p_search.add_argument("--n", type=int, default=200)
    p_search.add_argument("--warmups", type=int, default=20)
    p_search.add_argument("--top-k", type=int, default=10)
    p_search.add_argument("--out", type=Path)

    p_conc = sub.add_parser("concurrent")
    p_conc.add_argument("--target", required=True, choices=["search", "embed"])
    p_conc.add_argument("--c", type=int, nargs="+", required=True, help="동시성 스윕 (예: 1 2 4 8)")
    p_conc.add_argument("--n", type=int, default=60, help="동시성마다 셀 요청 수")
    p_conc.add_argument("--warmups", type=int, default=10)
    p_conc.add_argument("--top-k", type=int, default=10)
    p_conc.add_argument("--route", default="hybrid_only",
                        choices=["hybrid_only", "keyword_only", "vector_only"])
    p_conc.add_argument("--url", default="http://nexus-embed:8080")
    p_conc.add_argument("--out", type=Path)

    p_report = sub.add_parser("report")
    p_report.add_argument("--before", type=Path, required=True)
    p_report.add_argument("--after", type=Path, required=True)
    p_report.add_argument("--embed", type=Path, nargs="*", default=[])
    p_report.add_argument("--date", required=True)
    p_report.add_argument("--machine", required=True)
    p_report.add_argument("--out", type=Path, required=True)

    args = ap.parse_args()

    def _load(path: Path) -> Measurement:
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["latency"] = Percentiles(**raw["latency"])
        return Measurement(**raw)

    if args.cmd == "report":
        before, after = _load(args.before), _load(args.after)
        embeds = [_load(p) for p in args.embed]
        args.out.write_text(render_report(before, after, embeds, args.date, args.machine),
                            encoding="utf-8")
        print(args.out)
        ok, reason = verdict(before, after)
        print(("통과: " if ok else "위반: ") + reason)
        return 0 if ok else 1

    if args.cmd == "concurrent":
        sweep: list[Measurement] = []
        for c in args.c:
            if args.target == "search":
                m = _run(measure_search_concurrent(f"C={c}", c, args.n, args.warmups,
                                                   args.top_k, args.route))
            else:
                m = _run(measure_embed_concurrent(f"C={c}", c, args.n, args.warmups, args.url))
            sweep.append(m)
            print(f"C={c:<3} n={m.latency.n:<4} p50={m.latency.p50_ms:>8.1f} "
                  f"p95={m.latency.p95_ms:>8.1f} max={m.latency.max_ms:>8.1f} "
                  f"rps={m.throughput_rps:>6.2f} err={m.errors}", flush=True)
        ok, reason = concurrency_verdict(sweep)
        print(("통과: " if ok else "위반: ") + reason)
        if args.out:
            args.out.write_text(json.dumps([asdict(m) for m in sweep], ensure_ascii=False,
                                           indent=2), encoding="utf-8")
        return 0 if ok else 1

    if args.cmd == "embed":
        m = _run(measure_embed(args.model, args.backend, args.n, args.warmups))
    else:
        m = _run(measure_search(args.label, args.n, args.warmups, args.top_k))

    print(m.to_json())
    if args.out:
        args.out.write_text(m.to_json(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
