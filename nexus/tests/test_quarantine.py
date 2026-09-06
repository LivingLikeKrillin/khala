"""Quarantine 테스트 — PII 감지, classification, 격리."""

from nexus.ingest.scanner import scan_content, _luhn_check
from nexus.ingest.classifier import classify, _detect_language


class TestPIIScanner:
    def test_aws_key_detected(self):
        content = "여기 AWS 키: AKIAIOSFODNN7EXAMPLE 입니다"
        result = scan_content(content, {"aws_key": r"AKIA[0-9A-Z]{16}"})
        assert result.has_pii is True
        assert "aws_key" in result.pii_types

    def test_jwt_detected(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.abc123"
        result = scan_content(f"토큰: {jwt}", {
            "jwt": r"eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_.+/=]+"
        })
        assert result.has_pii is True

    def test_korean_ssn_detected(self):
        result = scan_content("주민번호: 900101-1234567", {
            "korean_ssn": r"\b[0-9]{6}-[1-4][0-9]{6}\b"
        })
        assert result.has_pii is True

    def test_no_pii(self):
        result = scan_content("이것은 안전한 문서입니다.", {
            "aws_key": r"AKIA[0-9A-Z]{16}",
        })
        assert result.has_pii is False

    def test_credit_card_luhn_valid(self):
        assert _luhn_check("4532015112830366") is True

    def test_credit_card_luhn_invalid(self):
        assert _luhn_check("1234567890123456") is False


class TestClassifier:
    def _make_config(self):
        return {
            "path_rules": [
                {"pattern": "**/security/**", "classification": "RESTRICTED"},
                {"pattern": "**/public/**", "classification": "PUBLIC"},
            ],
            "file_type_rules": [
                {"extensions": [".pem", ".key"], "classification": "RESTRICTED"},
            ],
            "pii_patterns": {
                "aws_key": r"AKIA[0-9A-Z]{16}",
            },
        }

    def test_pii_quarantines(self):
        result = classify(
            "docs/test.md",
            "키: AKIAIOSFODNN7EXAMPLE",
            {},
            self._make_config(),
        )
        assert result.is_quarantined is True
        assert result.classification == "RESTRICTED"

    def test_path_rule_restricted(self):
        result = classify(
            "docs/security/policy.md",
            "보안 정책 문서",
            {},
            self._make_config(),
        )
        assert result.classification == "RESTRICTED"
        assert result.is_quarantined is False

    def test_path_rule_public(self):
        result = classify(
            "docs/public/guide.md",
            "공개 가이드",
            {},
            self._make_config(),
        )
        assert result.classification == "PUBLIC"

    def test_default_internal(self):
        result = classify("docs/readme.md", "일반 문서", {}, self._make_config())
        assert result.classification == "INTERNAL"

    def test_frontmatter_classification(self):
        result = classify(
            "docs/test.md",
            "문서 내용",
            {"classification": "PUBLIC"},
            self._make_config(),
        )
        assert result.classification == "PUBLIC"

    def test_frontmatter_cannot_lower_restricted(self):
        result = classify(
            "docs/security/policy.md",
            "보안 문서",
            {"classification": "PUBLIC"},
            self._make_config(),
        )
        assert result.classification == "RESTRICTED"


class TestLanguageDetection:
    def test_korean(self):
        assert _detect_language("결제 서비스가 알림을 전송한다") == "ko"

    def test_english(self):
        assert _detect_language("Payment service sends notifications") == "en"

    def test_mixed(self):
        assert _detect_language("Payment 서비스가 notification을 보낸다") == "mixed"

    def test_empty(self):
        assert _detect_language("") == "ko"


class TestChunkLevelQuarantine:
    """**문서가 아니라 조각을 뺀다.**

    2026-08-28 라이브: 148KB 짜리 설계 plan 이 2026-08-16 부터 코퍼스에서 사라져 있었다.
    자바 테스트의 16자리 사용자 ID 아홉 개 중 **하나가 우연히 Luhn 을 통과**했기 때문이다.
    같은 날 다른 문서는 *JWT 를 가리는 것을 검증하는 테스트 문서*라 예시 토큰에 걸렸다.
    한 조각의 오검출로 문서 전체가 조용히 사라지면 안 된다.
    """

    PATTERNS = {"aws_key": r"AKIA[0-9A-Z]{16}"}

    class _C:
        def __init__(self, text, idx=0):
            self.chunk_text = text
            self.chunk_index = idx
            self.section_path = "§"

    def test_only_the_chunk_that_holds_the_secret_is_picked(self):
        from nexus.ingest.classifier import quarantined_chunk_indexes
        chunks = [self._C("설계 배경과 문제 정의"),
                  self._C("키: AKIAIOSFODNN7EXAMPLE"),
                  self._C("마이그레이션 계획")]
        assert quarantined_chunk_indexes(chunks, self.PATTERNS) == {1}

    def test_a_clean_document_picks_nothing(self):
        from nexus.ingest.classifier import quarantined_chunk_indexes
        chunks = [self._C("평범한 문단"), self._C("또 다른 문단")]
        assert quarantined_chunk_indexes(chunks, self.PATTERNS) == set()

    def test_every_chunk_dirty_means_the_whole_document(self):
        """⛔ 대조군. 전부 걸린 문서까지 살리면 이 변경은 격리를 없앤 것이 된다."""
        from nexus.ingest.classifier import quarantined_chunk_indexes
        chunks = [self._C("AKIAIOSFODNN7EXAMPLE"), self._C("AKIAIOSFODNN7EXAMPLB")]
        assert quarantined_chunk_indexes(chunks, self.PATTERNS) == {0, 1}

    def test_no_patterns_configured_quarantines_nothing(self):
        from nexus.ingest.classifier import quarantined_chunk_indexes
        assert quarantined_chunk_indexes([self._C("AKIAIOSFODNN7EXAMPLE")], {}) == set()

    def test_the_position_is_what_selects_a_chunk_not_chunk_index(self):
        """`chunk_index` 는 절마다 0 부터 다시 센다 — 문서 안에서 고유하지 않다.
        그것으로 조각을 고르면 엉뚱한 조각이 빠진다."""
        from nexus.ingest.classifier import quarantined_chunk_indexes
        chunks = [self._C("깨끗한 절의 첫 조각", idx=0),
                  self._C("다음 절 첫 조각: AKIAIOSFODNN7EXAMPLE", idx=0)]
        assert quarantined_chunk_indexes(chunks, self.PATTERNS) == {1}

    def test_a_withheld_chunk_keeps_its_seat_but_not_its_text(self, monkeypatch):
        """⛔ 문서 단위 격리는 청크를 아예 안 만들어서 비밀이 DB 에 안 들어갔다.
        조각 단위로 바꾸면서 그 성질을 잃으면, 오검출을 살리려다 진짜 비밀을 테이블에 앉힌다.

        **소스 문자열이 아니라 실제로 넘어가는 값을 본다** — 이 리포는 소스 검사로 거짓
        초록을 받은 적이 있다."""
        import asyncio

        from nexus.ingest import pipeline
        from nexus.ingest.classifier import ClassificationResult

        written = []

        # ⭐ **이 스텁은 `_save_chunks` 가 써도 되는 db 표면의 화이트리스트다.** 프로덕션이
        # 새 호출을 더하면 여기서 `AttributeError` 로 터진다 — 2026-09-06 에 041(재적재 청크
        # 수)이 `fetch_val` 을 더하면서 실제로 그렇게 됐다. 그 터짐이 결함이 아니라 **신호**다:
        # 이 경로는 비밀이 테이블에 앉지 않는 것을 지키는 자리라, 무엇을 더 부르는지 눈에
        # 띄어야 한다. 조용히 통과시키는 `Mock` 으로 바꾸지 마라.
        class _DB:
            @staticmethod
            async def fetch_one(*a, **k):
                return {"status": "active", "title": "T"}

            @staticmethod
            async def fetch_val(*a, **k):
                return 0          # 재적재 전 active 청크 수 — 이 검사가 보는 값이 아니다

            @staticmethod
            async def execute(sql, *args):
                if "INSERT INTO chunks" in sql:
                    written.append(args)

        monkeypatch.setattr(pipeline, "db", _DB)
        secret = "키: AKIAIOSFODNN7EXAMPLE"
        chunks = [self._C("깨끗한 문단", 0), self._C(secret, 1)]
        collected = type("C", (), {"canonical_uri": "t:doc.md", "content_hash": "h",
                                   "relative_path": "doc.md"})()
        cls = ClassificationResult(classification="INTERNAL")
        cls.quarantine_reason = "PII detected: aws_key"

        asyncio.run(pipeline._save_chunks(chunks, "doc_1", collected, cls, "t",
                                          quarantined_idx={1}))

        assert len(written) == 2, "격리된 조각도 자리는 남아야 한다"
        texts = [a[8] for a in written]
        assert texts[0] == "깨끗한 문단"
        assert "AKIA" not in texts[1], "격리된 조각의 원문이 그대로 저장됐다"
        assert "격리" in texts[1]
