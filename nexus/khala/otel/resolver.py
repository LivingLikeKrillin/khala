"""Service Name Resolution.

OTel span의 서비스 이름을 정규화한다.
우선순위: service.name → peer.service + gazetteer → k8s → reverse DNS → hash fallback
"""

from __future__ import annotations

import hashlib

import structlog

logger = structlog.get_logger(__name__)


def resolve_service_name(
    span_attrs: dict,
    resource_attrs: dict,
    gazetteer_names: set[str] | None = None,
) -> tuple[str, str]:
    """Span 속성에서 서비스 이름을 해석.

    Args:
        span_attrs: span-level attributes
        resource_attrs: resource-level attributes
        gazetteer_names: entities.yaml에 등록된 서비스 이름 집합

    Returns:
        (resolved_name, resolved_via)
    """
    gazetteer = gazetteer_names or set()

    # 1. service.name (resource attribute)
    if name := resource_attrs.get("service.name"):
        if name != "unknown_service" and name.strip():
            return name.strip(), "service.name"

    # 2. peer.service + gazetteer 검증
    if peer := span_attrs.get("peer.service"):
        peer = peer.strip()
        if peer in gazetteer:
            return peer, "peer.service+gazetteer"
        # gazetteer에 없어도 유효한 이름이면 사용
        if peer and peer != "unknown":
            return peer, "peer.service"

    # 3. k8s metadata
    k8s_deploy = resource_attrs.get("k8s.deployment.name")
    k8s_ns = resource_attrs.get("k8s.namespace.name")
    if k8s_deploy:
        name = f"{k8s_ns}/{k8s_deploy}" if k8s_ns else k8s_deploy
        return name, "k8s.metadata"

    # 4. server.address (reverse DNS)
    if addr := span_attrs.get("server.address"):
        return addr.strip(), "server.address"

    # 5. fallback: hash
    raw = str(span_attrs) + str(resource_attrs)
    h = hashlib.sha256(raw.encode()).hexdigest()[:8]
    fallback_name = f"unknown_svc_{h}"
    logger.warning("service_name_fallback", fallback=fallback_name)
    return fallback_name, "hash_fallback"
