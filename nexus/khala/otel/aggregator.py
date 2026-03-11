"""OTel Aggregator — Tempo 쿼리 → CALLS_OBSERVED 생성.

Raw trace는 Khala DB에 저장하지 않는다. Tempo에 포인터만 유지.
5분 단위 집계로 observed_edge를 생성/갱신한다.
"""

from __future__ import annotations

import os
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
import structlog
import yaml

from khala import db
from khala.index.graph_extractor import ensure_entity_exists
from khala.otel.resolver import resolve_service_name
from khala.repositories.graph import PostgresGraphRepository
from khala.rid import canonicalize_entity_name, entity_rid, evidence_rid, observed_edge_rid

logger = structlog.get_logger(__name__)


@dataclass
class AggregatedEdge:
    """집계된 서비스 간 호출."""
    from_service: str
    to_service: str
    call_count: int = 0
    error_count: int = 0
    latencies: list[float] = field(default_factory=list)
    protocol: str = ""
    interaction_style: str = "SYNC"
    sample_trace_ids: list[str] = field(default_factory=list)
    trace_query_ref: str = ""
    resolved_via: str = ""


@dataclass
class AggregationResult:
    """집계 결과 요약."""
    edges_created: int = 0
    edges_updated: int = 0
    unresolved_services: list[str] = field(default_factory=list)
    timing_ms: int = 0


async def _fetch_traces_from_tempo(
    tempo_url: str,
    lookback_minutes: int = 60,
) -> list[dict]:
    """Tempo에서 trace 조회.

    실제 Tempo API: GET /api/search
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{tempo_url}/api/search",
                params={
                    "limit": 100,
                    "start": int((datetime.now(timezone.utc).timestamp() - lookback_minutes * 60)),
                    "end": int(datetime.now(timezone.utc).timestamp()),
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("traces", [])
    except Exception as e:
        logger.error("tempo_fetch_failed", error=str(e))
        return []


async def _fetch_trace_detail(tempo_url: str, trace_id: str) -> dict | None:
    """개별 trace의 상세 span 조회."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{tempo_url}/api/traces/{trace_id}")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning("trace_detail_fetch_failed", trace_id=trace_id, error=str(e))
        return None


def _extract_service_pairs(trace_data: dict, gazetteer_names: set[str]) -> list[dict]:
    """Trace에서 (from_service, to_service) 쌍 추출."""
    pairs: list[dict] = []

    batches = trace_data.get("batches", [])
    for batch in batches:
        resource = batch.get("resource", {})
        resource_attrs = {}
        for attr in resource.get("attributes", []):
            resource_attrs[attr.get("key", "")] = attr.get("value", {}).get("stringValue", "")

        for scope_spans in batch.get("scopeSpans", batch.get("instrumentationLibrarySpans", [])):
            for span in scope_spans.get("spans", []):
                span_attrs = {}
                for attr in span.get("attributes", []):
                    key = attr.get("key", "")
                    val = attr.get("value", {})
                    span_attrs[key] = val.get("stringValue", val.get("intValue", ""))

                # 서비스 이름 해석
                from_name, from_via = resolve_service_name(span_attrs, resource_attrs, gazetteer_names)
                to_name = span_attrs.get("peer.service", "")

                if not to_name:
                    continue

                to_name_resolved, to_via = resolve_service_name(
                    {"peer.service": to_name}, {}, gazetteer_names,
                )

                # 메트릭 추출
                duration_ns = int(span.get("endTimeUnixNano", 0)) - int(span.get("startTimeUnixNano", 0))
                duration_ms = duration_ns / 1_000_000 if duration_ns > 0 else 0
                is_error = span.get("status", {}).get("code", 0) == 2  # ERROR

                pairs.append({
                    "from_service": from_name,
                    "to_service": to_name_resolved,
                    "duration_ms": duration_ms,
                    "is_error": is_error,
                    "trace_id": span.get("traceId", ""),
                    "resolved_via": from_via,
                    "protocol": span_attrs.get("rpc.system", span_attrs.get("http.method", "")),
                })

    return pairs


def _aggregate_pairs(pairs: list[dict]) -> dict[tuple[str, str], AggregatedEdge]:
    """서비스 쌍별 메트릭 집계."""
    agg: dict[tuple[str, str], AggregatedEdge] = {}

    for p in pairs:
        key = (p["from_service"], p["to_service"])
        if key not in agg:
            agg[key] = AggregatedEdge(
                from_service=p["from_service"],
                to_service=p["to_service"],
                resolved_via=p.get("resolved_via", ""),
            )
        edge = agg[key]
        edge.call_count += 1
        if p.get("is_error"):
            edge.error_count += 1
        if p.get("duration_ms", 0) > 0:
            edge.latencies.append(p["duration_ms"])
        if p.get("trace_id") and len(edge.sample_trace_ids) < 5:
            edge.sample_trace_ids.append(p["trace_id"])
        if p.get("protocol"):
            edge.protocol = p["protocol"]

    return agg


async def run_otel_aggregation(
    window_minutes: int = 5,
    lookback_minutes: int = 60,
    tenant: str = "default",
    config_path: str = "config.yaml",
) -> AggregationResult:
    """OTel 집계 파이프라인 실행.

    1. Tempo에서 trace 조회
    2. 서비스 이름 해석
    3. 서비스 쌍별 메트릭 집계
    4. observed_edge upsert

    Args:
        window_minutes: 집계 윈도우 (분)
        lookback_minutes: 조회 기간 (분)
        tenant: 테넌트 ID
        config_path: 설정 파일 경로

    Returns:
        AggregationResult
    """
    import time
    start = time.time()

    tempo_url = os.getenv("TEMPO_URL", "http://localhost:3200")

    # Gazetteer 로드
    from pathlib import Path
    gaz_path = Path("entities.yaml")
    gazetteer_names: set[str] = set()
    if gaz_path.exists():
        with open(gaz_path, encoding="utf-8") as f:
            gaz_data = yaml.safe_load(f) or {}
        for ent in gaz_data.get("entities", []):
            gazetteer_names.add(ent["name"])
            for alias in ent.get("aliases", []):
                gazetteer_names.add(alias)

    result = AggregationResult()

    # 1. Trace 목록 조회
    traces = await _fetch_traces_from_tempo(tempo_url, lookback_minutes)
    if not traces:
        logger.info("no_traces_found")
        result.timing_ms = int((time.time() - start) * 1000)
        return result

    # 2. 각 trace의 상세 span 분석
    all_pairs: list[dict] = []
    for trace_summary in traces[:50]:  # 최대 50 trace
        trace_id = trace_summary.get("traceID", "")
        if not trace_id:
            continue
        detail = await _fetch_trace_detail(tempo_url, trace_id)
        if detail:
            pairs = _extract_service_pairs(detail, gazetteer_names)
            all_pairs.extend(pairs)

    # 3. 집계
    aggregated = _aggregate_pairs(all_pairs)

    # 4. DB에 upsert
    pool = await db.get_pool()
    graph_repo = PostgresGraphRepository(pool)

    now = datetime.now(timezone.utc)
    window_start = datetime.fromtimestamp(
        now.timestamp() - window_minutes * 60, tz=timezone.utc,
    )

    edges_to_upsert: list[dict] = []
    for (from_svc, to_svc), agg_edge in aggregated.items():
        # 엔티티 확보
        from_canonical = canonicalize_entity_name(from_svc, "Service")
        to_canonical = canonicalize_entity_name(to_svc, "Service")

        from_rid_val = await ensure_entity_exists(
            tenant, from_svc, "Service", source_kind="otel",
        )
        to_rid_val = await ensure_entity_exists(
            tenant, to_svc, "Service", source_kind="otel",
        )

        # 퍼센타일 계산
        latencies = sorted(agg_edge.latencies) if agg_edge.latencies else []
        p50 = latencies[len(latencies) // 2] if latencies else None
        p95_idx = int(len(latencies) * 0.95) if latencies else 0
        p95 = latencies[min(p95_idx, len(latencies) - 1)] if latencies else None
        p99_idx = int(len(latencies) * 0.99) if latencies else 0
        p99 = latencies[min(p99_idx, len(latencies) - 1)] if latencies else None

        error_rate = agg_edge.error_count / agg_edge.call_count if agg_edge.call_count > 0 else 0.0

        rid = observed_edge_rid(tenant, "CALLS_OBSERVED", from_rid_val, to_rid_val)

        edges_to_upsert.append({
            "rid": rid,
            "tenant": tenant,
            "edge_type": "CALLS_OBSERVED",
            "from_rid": from_rid_val,
            "to_rid": to_rid_val,
            "call_count": agg_edge.call_count,
            "error_rate": error_rate,
            "latency_p50": p50,
            "latency_p95": p95,
            "latency_p99": p99,
            "protocol": agg_edge.protocol,
            "interaction_style": agg_edge.interaction_style,
            "sample_trace_ids": agg_edge.sample_trace_ids[:5],
            "trace_query_ref": f"{tempo_url}/api/search?start={int(window_start.timestamp())}",
            "resolved_via": agg_edge.resolved_via,
            "window_start": window_start,
            "window_end": now,
        })

    if edges_to_upsert:
        count = await graph_repo.upsert_observed_edges(edges_to_upsert)
        result.edges_created = count

        # Evidence 생성: observed_edge → trace_query_ref 연결
        for e in edges_to_upsert:
            evi_rid = evidence_rid(e["rid"], e.get("trace_query_ref", ""))
            try:
                await db.execute(
                    """
                    INSERT INTO evidence (
                        rid, rtype, tenant, classification, owner,
                        source_kind, status, created_at, updated_at,
                        subject_rid, evidence_rid, kind, weight, note
                    ) VALUES (
                        $1, 'evidence', $2, 'INTERNAL', 'otel-aggregator',
                        'otel', 'active', now(), now(),
                        $3, $4, 'trace_ref', 0.25, $5
                    )
                    ON CONFLICT (rid) DO UPDATE SET updated_at = now()
                    """,
                    evi_rid, tenant,
                    e["rid"], e.get("trace_query_ref", ""),
                    f"calls={e.get('call_count', 0)}, error_rate={e.get('error_rate', 0):.2%}",
                )
            except Exception as ev_err:
                logger.warning("otel_evidence_failed", rid=e["rid"], error=str(ev_err))

    result.timing_ms = int((time.time() - start) * 1000)
    logger.info("otel_aggregation_complete",
                edges=result.edges_created,
                timing_ms=result.timing_ms)

    return result
