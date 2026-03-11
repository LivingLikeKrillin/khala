"""OTel 테스트 — 서비스 이름 해석."""

from khala.otel.resolver import resolve_service_name


class TestServiceNameResolution:
    def test_service_name_attribute(self):
        name, via = resolve_service_name({}, {"service.name": "payment-service"})
        assert name == "payment-service"
        assert via == "service.name"

    def test_unknown_service_falls_through(self):
        name, via = resolve_service_name(
            {"peer.service": "notification-svc"},
            {"service.name": "unknown_service"},
        )
        assert name == "notification-svc"

    def test_peer_service_with_gazetteer(self):
        name, via = resolve_service_name(
            {"peer.service": "payment-service"}, {},
            gazetteer_names={"payment-service", "order-service"},
        )
        assert name == "payment-service"
        assert via == "peer.service+gazetteer"

    def test_k8s_metadata(self):
        name, via = resolve_service_name(
            {}, {"k8s.deployment.name": "payment-api", "k8s.namespace.name": "prod"},
        )
        assert name == "prod/payment-api"
        assert via == "k8s.metadata"

    def test_hash_fallback(self):
        name, via = resolve_service_name({}, {})
        assert name.startswith("unknown_svc_")
        assert via == "hash_fallback"

    def test_priority_order(self):
        name, via = resolve_service_name(
            {"peer.service": "other"},
            {"service.name": "primary"},
        )
        assert name == "primary"
        assert via == "service.name"
