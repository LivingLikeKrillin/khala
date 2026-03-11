"""Quarantine 테스트 — PII 감지, classification, 격리."""

from khala.ingest.scanner import scan_content, _luhn_check
from khala.ingest.classifier import classify, _detect_language


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
