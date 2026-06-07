"""API 엔드포인트 테스트 — Request 모델 검증, 라우팅 로직, 응답 구조."""

from khala.api import (
    SearchRequest,
    AnswerRequest,
    IngestRequest,
    OtelAggregateRequest,
    KhalaResponse,
)


class TestSearchRequest:
    def test_defaults(self):
        req = SearchRequest(query="테스트 쿼리")
        assert req.top_k == 10
        assert req.route == "auto"
        assert req.classification_max == "INTERNAL"
        assert req.tenant == "default"
        assert req.include_graph is True
        assert req.include_evidence is True

    def test_custom_tenant(self):
        req = SearchRequest(query="쿼리", tenant="team-a")
        assert req.tenant == "team-a"

    def test_all_fields(self):
        req = SearchRequest(
            query="결제 서비스",
            top_k=5,
            route="graph_then_hybrid",
            classification_max="RESTRICTED",
            tenant="ops",
            include_graph=False,
            include_evidence=False,
        )
        assert req.query == "결제 서비스"
        assert req.top_k == 5
        assert req.route == "graph_then_hybrid"
        assert req.include_graph is False


class TestAnswerRequest:
    def test_defaults(self):
        req = AnswerRequest(query="질문")
        assert req.tenant == "default"
        assert req.top_k == 10

    def test_custom_values(self):
        req = AnswerRequest(query="질문", tenant="dev", top_k=3)
        assert req.tenant == "dev"
        assert req.top_k == 3


class TestIngestRequest:
    def test_defaults(self):
        req = IngestRequest(path="./docs")
        assert req.force is False
        assert req.tenant == "default"

    def test_force_mode(self):
        req = IngestRequest(path="./docs", force=True)
        assert req.force is True


class TestOtelAggregateRequest:
    def test_defaults(self):
        req = OtelAggregateRequest()
        assert req.window_minutes == 5
        assert req.lookback_minutes == 60
        assert req.tenant == "default"


class TestKhalaResponse:
    def test_success(self):
        resp = KhalaResponse(data={"key": "value"})
        assert resp.success is True
        assert resp.data == {"key": "value"}
        assert resp.error is None

    def test_error(self):
        resp = KhalaResponse(success=False, error="DB 연결 실패")
        assert resp.success is False
        assert resp.error == "DB 연결 실패"
        assert resp.data is None

    def test_meta(self):
        resp = KhalaResponse(data=[], meta={"total": 42, "offset": 0})
        assert resp.meta["total"] == 42
