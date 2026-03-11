"""Graph 추출 테스트 — 엔티티 감지, 관계 추출, 부정 표현 필터."""

from khala.index.graph_extractor import (
    find_entities_in_text,
    extract_relations,
    _build_entity_patterns,
    _check_negation,
)


SAMPLE_ENTITIES = [
    {"name": "payment-service", "type": "Service", "aliases": ["결제 서비스", "결제서비스"]},
    {"name": "notification-service", "type": "Service", "aliases": ["알림 서비스", "알림서비스"]},
    {"name": "order-service", "type": "Service", "aliases": ["주문 서비스"]},
    {"name": "payment.completed", "type": "Topic", "aliases": ["결제 완료 이벤트"]},
]

SAMPLE_TRIGGERS = {
    "CALLS": {
        "ko": ["호출한다", "호출하는", "요청한다"],
        "en": ["calls", "invokes"],
    },
    "PUBLISHES": {
        "ko": ["발행한다", "발행하는"],
        "en": ["publishes", "emits"],
    },
    "SUBSCRIBES": {
        "ko": ["구독한다", "구독하는"],
        "en": ["subscribes", "consumes"],
    },
}


class TestEntityDetection:
    def test_canonical_name_match(self):
        patterns = _build_entity_patterns(SAMPLE_ENTITIES)
        found = find_entities_in_text("payment-service는 중요합니다", patterns)
        assert len(found) == 1
        assert found[0].name == "payment-service"

    def test_korean_alias_match(self):
        patterns = _build_entity_patterns(SAMPLE_ENTITIES)
        found = find_entities_in_text("결제 서비스가 알림 서비스를 호출한다", patterns)
        names = {f.name for f in found}
        assert "payment-service" in names
        assert "notification-service" in names

    def test_no_match(self):
        patterns = _build_entity_patterns(SAMPLE_ENTITIES)
        found = find_entities_in_text("이것은 관련 없는 문서입니다", patterns)
        assert len(found) == 0

    def test_multiple_entities(self):
        patterns = _build_entity_patterns(SAMPLE_ENTITIES)
        text = "주문 서비스가 결제 서비스를 호출하고, 알림 서비스에 통보한다"
        found = find_entities_in_text(text, patterns)
        assert len(found) == 3


class TestRelationExtraction:
    def test_calls_relation(self):
        patterns = _build_entity_patterns(SAMPLE_ENTITIES)
        text = "결제 서비스가 알림 서비스를 호출한다."
        candidates = extract_relations(text, "chunk_001", patterns, SAMPLE_TRIGGERS)
        assert len(candidates) >= 1
        assert candidates[0].edge_type == "CALLS"

    def test_publishes_relation(self):
        patterns = _build_entity_patterns(SAMPLE_ENTITIES)
        text = "결제 서비스가 결제 완료 이벤트를 발행한다."
        candidates = extract_relations(text, "chunk_002", patterns, SAMPLE_TRIGGERS)
        types = {c.edge_type for c in candidates}
        assert "PUBLISHES" in types

    def test_english_trigger(self):
        patterns = _build_entity_patterns(SAMPLE_ENTITIES)
        text = "payment-service calls notification-service"
        candidates = extract_relations(text, "chunk_003", patterns, SAMPLE_TRIGGERS)
        assert len(candidates) >= 1

    def test_no_trigger_no_relation(self):
        patterns = _build_entity_patterns(SAMPLE_ENTITIES)
        text = "결제 서비스와 알림 서비스가 있다."
        candidates = extract_relations(text, "chunk_004", patterns, SAMPLE_TRIGGERS)
        assert len(candidates) == 0


class TestNegationFilter:
    def test_negation_korean(self):
        assert _check_negation("서비스를 호출하지 않는다", 10) is True

    def test_negation_english(self):
        assert _check_negation("does not call the service", 10) is True

    def test_no_negation(self):
        assert _check_negation("서비스를 호출한다", 5) is False
