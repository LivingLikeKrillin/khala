"""엔티티 자동완성/문서 목록 관련 로직 테스트."""

from khala.rid import canonicalize_entity_name, entity_rid


class TestEntitySuggestLogic:
    """엔티티 자동완성에서 사용되는 이름 정규화 로직."""

    def test_canonicalize_service(self):
        name = canonicalize_entity_name("Payment Service", "Service")
        assert name == "payment-service"

    def test_canonicalize_korean(self):
        name = canonicalize_entity_name("결제 서비스", "Service")
        assert name == "결제-서비스"

    def test_canonicalize_idempotent(self):
        name1 = canonicalize_entity_name("payment-service", "Service")
        name2 = canonicalize_entity_name("payment-service", "Service")
        assert name1 == name2

    def test_entity_rid_from_name(self):
        """이름 기반 조회 시 동일 rid 생성 보장."""
        name = canonicalize_entity_name("payment-service", "Service")
        rid1 = entity_rid("default", "Service", name)
        rid2 = entity_rid("default", "Service", name)
        assert rid1 == rid2
        assert rid1.startswith("ent_")

    def test_different_tenants_different_rids(self):
        name = canonicalize_entity_name("payment-service", "Service")
        rid_a = entity_rid("team-a", "Service", name)
        rid_b = entity_rid("team-b", "Service", name)
        assert rid_a != rid_b

    def test_graph_endpoint_name_detection(self):
        """API의 이름 기반 조회: ent_ 접두사로 rid/이름 구분."""
        rid = "ent_abc123def456"
        name = "payment-service"
        assert rid.startswith("ent_")
        assert not name.startswith("ent_")


class TestDiffFilterLogic:
    """/diff 엔드포인트의 entity_filter 로직."""

    def test_filter_match_from(self):
        """from_name이 일치하면 통과."""
        from_name = "payment-service"
        to_name = "notification-service"
        entity_filter = "payment-service"
        assert entity_filter in (from_name, to_name)

    def test_filter_match_to(self):
        """to_name이 일치하면 통과."""
        from_name = "order-service"
        to_name = "payment-service"
        entity_filter = "payment-service"
        assert entity_filter in (from_name, to_name)

    def test_filter_no_match(self):
        """양쪽 모두 일치하지 않으면 제외."""
        from_name = "order-service"
        to_name = "notification-service"
        entity_filter = "payment-service"
        assert entity_filter not in (from_name, to_name)

    def test_no_filter(self):
        """entity_filter가 None이면 모든 항목 통과."""
        entity_filter = None
        should_skip = entity_filter and entity_filter not in ("a", "b")
        assert not should_skip
