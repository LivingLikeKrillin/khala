"""CRM 모델 테스트 — rid 생성, canonicalize.

⚠ 접근 통제·`base_filter` 시험이 여기 있었는데 2026-09-02 에 걷어냈다. 그 대상이
`models/resource.py` 의 **사본**이었고 프로덕션 호출자가 0이었다(외부 평가 F1).
실제 통제는 SQL 의 네 절이고, 그것은 진짜 DB 를 치는 검사들이 지킨다 —
`test_graph_scope_filter.py` · `test_supersede_title_policy_filter.py` ·
`test_corpus_scope.py`. 등급 순서표가 하나뿐인지는 `test_auth_clearance.py` 가 본다.
"""

from nexus.rid import (
    make_rid, doc_rid, chunk_rid, entity_rid, edge_rid,
    evidence_rid, canonicalize_entity_name,
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
