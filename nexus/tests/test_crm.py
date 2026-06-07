"""CRM 모델 테스트 — rid 생성, canonicalize, 접근 통제, base_filter."""

from khala.models.resource import KhalaResource, is_accessible, CLASSIFICATION_LEVELS
from khala.rid import (
    make_rid, doc_rid, chunk_rid, entity_rid, edge_rid,
    observed_edge_rid, evidence_rid, canonicalize_entity_name,
)


class TestMakeRid:
    def test_deterministic(self):
        r1 = make_rid("doc", "test/path.md")
        r2 = make_rid("doc", "test/path.md")
        assert r1 == r2

    def test_different_inputs(self):
        r1 = make_rid("doc", "a.md")
        r2 = make_rid("doc", "b.md")
        assert r1 != r2

    def test_prefix_preserved(self):
        r = make_rid("doc", "test.md")
        assert r.startswith("doc_")

    def test_hash_length(self):
        r = make_rid("doc", "test.md")
        hash_part = r.split("_", 1)[1]
        assert len(hash_part) == 12


class TestSpecializedRids:
    def test_doc_rid_stable(self):
        r = doc_rid("default:docs/test.md")
        assert r.startswith("doc_")

    def test_chunk_rid_depends_on_doc(self):
        parent = doc_rid("default:test.md")
        c1 = chunk_rid(parent, "H1", 0)
        c2 = chunk_rid(parent, "H1", 1)
        assert c1 != c2

    def test_entity_rid(self):
        r = entity_rid("default", "Service", "payment-service")
        assert r.startswith("ent_")

    def test_edge_rid_idempotent(self):
        r1 = edge_rid("default", "CALLS", "ent_a", "ent_b")
        r2 = edge_rid("default", "CALLS", "ent_a", "ent_b")
        assert r1 == r2

    def test_evidence_rid(self):
        r = evidence_rid("edge_abc", "chunk_xyz")
        assert r.startswith("evi_")


class TestCanonicalizeEntityName:
    def test_basic(self):
        assert canonicalize_entity_name("Payment_Service", "Service") == "payment-service"

    def test_spaces(self):
        assert canonicalize_entity_name("  Order  Service ", "Service") == "order-service"

    def test_mixed(self):
        assert canonicalize_entity_name("My_Cool  Service", "Service") == "my-cool-service"

    def test_already_canonical(self):
        assert canonicalize_entity_name("payment-service", "Service") == "payment-service"

    def test_korean(self):
        assert canonicalize_entity_name("결제 서비스", "Service") == "결제-서비스"


class TestAccessControl:
    def _make_resource(self, **kwargs) -> KhalaResource:
        defaults = {
            "rid": "test_rid",
            "rtype": "document",
            "tenant": "default",
            "classification": "INTERNAL",
        }
        defaults.update(kwargs)
        return KhalaResource(**defaults)

    def test_accessible(self):
        r = self._make_resource()
        assert is_accessible(r, "INTERNAL", "default") is True

    def test_higher_clearance(self):
        r = self._make_resource(classification="PUBLIC")
        assert is_accessible(r, "INTERNAL", "default") is True

    def test_insufficient_clearance(self):
        r = self._make_resource(classification="RESTRICTED")
        assert is_accessible(r, "INTERNAL", "default") is False

    def test_quarantined_blocked(self):
        r = self._make_resource(is_quarantined=True)
        assert is_accessible(r, "RESTRICTED", "default") is False

    def test_wrong_tenant(self):
        r = self._make_resource(tenant="other")
        assert is_accessible(r, "INTERNAL", "default") is False

    def test_inactive_blocked(self):
        r = self._make_resource(status="superseded")
        assert is_accessible(r, "INTERNAL", "default") is False


class TestClassificationLevels:
    def test_ordering(self):
        assert CLASSIFICATION_LEVELS["PUBLIC"] < CLASSIFICATION_LEVELS["INTERNAL"]
        assert CLASSIFICATION_LEVELS["INTERNAL"] < CLASSIFICATION_LEVELS["RESTRICTED"]
