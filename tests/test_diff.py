"""Diff 테스트 — DiffItem 구조 검증."""

from khala.repositories.graph import DiffItem


class TestDiffItem:
    def test_doc_only(self):
        item = DiffItem(
            flag="doc_only", edge_rid="edge_001", observed_edge_rid=None,
            from_name="payment-service", to_name="notification-service",
            edge_type="CALLS", detail="설계에만 존재",
        )
        assert item.flag == "doc_only"
        assert item.observed_edge_rid is None

    def test_observed_only(self):
        item = DiffItem(
            flag="observed_only", edge_rid=None, observed_edge_rid="obs_001",
            from_name="order-service", to_name="payment-service",
            edge_type="CALLS_OBSERVED", detail="관측에만 존재",
        )
        assert item.flag == "observed_only"
        assert item.edge_rid is None

    def test_conflict(self):
        item = DiffItem(
            flag="conflict", edge_rid="edge_002", observed_edge_rid="obs_002",
            from_name="payment-service", to_name="order-service",
            edge_type="CALLS", detail="프로토콜 불일치",
        )
        assert item.flag == "conflict"
        assert item.edge_rid is not None
        assert item.observed_edge_rid is not None
