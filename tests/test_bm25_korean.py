"""한국어 BM25 토큰화 테스트."""

from khala.index.bm25 import tokenize_korean, tokens_to_tsquery


class TestTokenizeKorean:
    def test_basic_tokenization(self):
        tokens = tokenize_korean("결제 서비스가 알림 서비스를 호출한다")
        assert len(tokens) > 0
        assert any("결제" in t for t in tokens)

    def test_english_mixed(self):
        tokens = tokenize_korean("payment-service calls notification-service")
        assert len(tokens) > 0

    def test_empty_input(self):
        tokens = tokenize_korean("")
        assert tokens == []

    def test_postposition_handling(self):
        tokens1 = tokenize_korean("서비스가")
        tokens2 = tokenize_korean("서비스를")
        assert len(tokens1) > 0
        assert len(tokens2) > 0


class TestTokensToTsquery:
    def test_basic(self):
        q = tokens_to_tsquery(["결제", "서비스"])
        assert "'결제'" in q
        assert "'서비스'" in q
        assert "&" in q

    def test_empty(self):
        assert tokens_to_tsquery([]) == ""

    def test_single_token(self):
        q = tokens_to_tsquery(["결제"])
        assert q == "'결제'"

    def test_sql_injection_safe(self):
        q = tokens_to_tsquery(["test'drop"])
        assert "test''drop" in q
