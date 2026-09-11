"""Graph 추출 테스트 — 엔티티 감지, 관계 추출, 부정 표현 필터."""

from nexus.index.graph_extractor import (
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


class TestRelationDirection:
    """방향은 **문장**이 정한다.

    ⛔ **왜 있나 (실측 2026-09-11).** 위 `TestRelationExtraction` 넷은 `edge_type` 과 개수만
    단언한다. 방향을 묻는 검사가 하나도 없어서, 방향을 정하는 것이 문장이 아니라 **엔티티
    이름의 길이**라는 사실이 초록 아래에 그대로 살아 있었다(`_build_entity_patterns` 가 긴
    패턴부터 정렬하고 `find_entities_in_text` 가 그 순서로 돌려줬다).

    ⭐ 아래 `test_the_opposite_sentence_gives_the_opposite_edge` 가 이 묶음의 대조군이다.
    한 문장만 보면 어떤 규칙이든 절반은 맞으므로 **뒤집은 문장과 나란히** 물어야 한다.
    """

    def test_direction_follows_the_sentence(self):
        """⚠ 별칭을 **길이가 다른 것**으로 고른다.

        처음에는 `결제 서비스가 알림 서비스를…` 로 썼는데 두 별칭의 길이가 같아,
        정렬을 빼도 원래 목록 순서 덕에 우연히 통과했다. 이름이 긴 쪽(`결제 서비스`)이
        문장에서 **뒤에** 오게 두어야 이 검사가 무언가를 묻는다.
        """
        patterns = _build_entity_patterns(SAMPLE_ENTITIES)
        text = "알림서비스가 결제 서비스를 호출한다."
        candidates = extract_relations(text, "chunk_dir_1", patterns, SAMPLE_TRIGGERS)
        calls = [c for c in candidates if c.edge_type == "CALLS"]
        assert calls, "CALLS 후보가 없다"
        assert calls[0].from_entity == "notification-service"
        assert calls[0].to_entity == "payment-service"

    def test_the_opposite_sentence_gives_the_opposite_edge(self):
        """뒤집은 문장은 뒤집힌 엣지를 내야 한다 — 같으면 문장을 안 읽고 있는 것이다."""
        patterns = _build_entity_patterns(SAMPLE_ENTITIES)

        def one_call(text: str) -> tuple[str, str]:
            cands = extract_relations(text, "chunk_dir_2", patterns, SAMPLE_TRIGGERS)
            calls = [c for c in cands if c.edge_type == "CALLS"]
            assert calls, f"CALLS 후보가 없다: {text}"
            return calls[0].from_entity, calls[0].to_entity

        forward = one_call("payment-service 가 notification-service 를 호출한다")
        backward = one_call("notification-service 가 payment-service 를 호출한다")

        assert forward == ("payment-service", "notification-service")
        assert backward == ("notification-service", "payment-service")
        assert forward != backward, "정반대 문장 둘이 같은 엣지를 냈다"

    def test_matches_come_back_in_text_order(self):
        """`notification-service` 는 이름이 더 길다. 뒤에 나오면 뒤에 와야 한다."""
        patterns = _build_entity_patterns(SAMPLE_ENTITIES)
        found = find_entities_in_text(
            "payment-service 가 notification-service 를 호출한다", patterns)
        assert [m.name for m in found] == ["payment-service", "notification-service"]
        assert [m.position for m in found] == sorted(m.position for m in found)

    def test_an_alias_and_the_canonical_name_report_the_first_position(self):
        """같은 엔티티가 두 이름으로 나오면 **먼저 나온 자리**가 그 엔티티의 자리다."""
        patterns = _build_entity_patterns(SAMPLE_ENTITIES)
        text = "결제 서비스는 주문 서비스를 호출한다. payment-service 로도 적는다."
        found = find_entities_in_text(text, patterns)
        by_name = {m.name: m.position for m in found}
        assert by_name["payment-service"] < by_name["order-service"]


class TestNegationFilter:
    def test_negation_korean(self):
        assert _check_negation("서비스를 호출하지 않는다", 10) is True

    def test_negation_english(self):
        assert _check_negation("does not call the service", 10) is True

    def test_no_negation(self):
        assert _check_negation("서비스를 호출한다", 5) is False
