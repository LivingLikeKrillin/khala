"""임베딩 백엔드와 모델별 지시문 정책 (SPEC-nexus-kure-embedding-swap §4.1, §4.3, §6).

**지시문 형식이 두 군데 있으면 언젠가 갈라진다.** 그래서 정책은 `EmbeddingService` 한 곳에 있고,
사이드카는 받은 문자열을 그대로 임베딩한다. 여기서 지키는 것은 그 정책의 네 갈래다:

- 모델 기본값 (카드에서 온 값)
- 설정이 덮는다
- **빈 문자열은 "지시문 없음" 이라는 적극적 값**이고 미지정과 다르다
- 카드에 지시문이 없는 모델에 지시문을 주면 **기동을 막는다** — 그게 한국어 임베딩 비교가 제거한
  교란(한 모델 형식을 다른 모델에 씌우기)의 재유입 경로다
"""

from __future__ import annotations

import httpx
import pytest

from nexus.providers.embedding import (
    MODEL_PREFIXES,
    ConflictingPrefixConfig,
    EmbeddingService,
    UnknownEmbeddingModel,
    resolve_prefixes,
)

# ── 지시문 정책 ──────────────────────────────────────────────────────────────


def test_each_model_gets_the_format_its_card_documents():
    assert resolve_prefixes("nomic-embed-text") == ("search_document: ", "search_query: ")
    assert resolve_prefixes("KURE-v1") == ("", "")


def test_config_overrides_the_default():
    assert resolve_prefixes("nomic-embed-text", "doc: ", "q: ") == ("doc: ", "q: ")


def test_an_explicit_empty_string_means_no_prefix_and_is_not_absence():
    """빈 값과 미지정이 같아지면 KURE 의 올바른 값을 설정으로 표현할 수 없다."""
    assert resolve_prefixes("nomic-embed-text", "", "") == ("", "")
    assert resolve_prefixes("nomic-embed-text") != ("", "")


def test_giving_a_prefix_to_a_model_that_documents_none_fails_at_startup():
    """이게 그 교란의 재유입 경로다 — 조용히 받아들이면 KURE 를 잘못 쓴 결과를 측정하게 된다."""
    with pytest.raises(ConflictingPrefixConfig):
        resolve_prefixes("KURE-v1", "search_document: ", "search_query: ")


def test_an_unknown_model_fails_rather_than_inheriting_nomics_format():
    with pytest.raises(UnknownEmbeddingModel):
        resolve_prefixes("bge-m3")


def test_the_registry_values_come_from_model_cards_not_guesses():
    """레지스트리에 모델을 추가할 때 무엇을 근거로 넣었는지 잊지 않도록 형태를 고정한다."""
    for model, prefixes in MODEL_PREFIXES.items():
        assert isinstance(model, str) and len(prefixes) == 2
        assert all(isinstance(x, str) for x in prefixes)


# ── 백엔드 선택 ──────────────────────────────────────────────────────────────


def test_the_default_backend_is_unchanged(monkeypatch):
    """이 유닛은 프로덕션 동작을 바꾸지 않는다 — 사이드카는 다음 유닛이 켠다."""
    monkeypatch.delenv("EMBEDDING_BACKEND", raising=False)
    svc = EmbeddingService()
    assert svc.backend == "ollama"
    assert svc.document_prefix == "search_document: "


def test_an_unknown_backend_is_refused():
    with pytest.raises(ValueError, match="백엔드"):
        EmbeddingService(backend="magic")


def test_the_sidecar_backend_has_a_shorter_timeout_than_ollama():
    """타임아웃이 없으면 '느려짐' 이 '멈춤' 이 된다. 콜드스타트가 ~9초라 특히 그렇다 (§4.1)."""
    ollama = EmbeddingService()
    sidecar = EmbeddingService(model="KURE-v1", backend="sidecar", dimensions=1024)
    assert sidecar.timeout < ollama.timeout
    assert sidecar.base_url.endswith(":8080")


# ── 사이드카 호출 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_sidecar_path_sends_prefixed_text_and_returns_vectors(monkeypatch):
    seen = {}

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"embeddings": [[0.1] * 1024], "model": "KURE-v1", "dim": 1024}

    class _Client:
        def __init__(self, **kw):
            seen["timeout"] = kw.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json):
            seen["url"], seen["texts"] = url, json["texts"]
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    svc = EmbeddingService(model="KURE-v1", backend="sidecar", dimensions=1024)
    out = await svc.embed_documents(["파드 개요"])

    assert len(out[0]) == 1024
    assert seen["url"].endswith("/embed")
    assert seen["texts"] == ["파드 개요"], "KURE 에는 지시문이 붙지 않아야 한다"
    assert seen["timeout"] == svc.batch_timeout, (
        "문서 임베딩은 배치 예산을 써야 한다 — 질의용 10초에 묶었더니 16건 배치가 전부 "
        "ReadTimeout 났다 (2026-08-04)")

    await svc.embed_query("질의")
    assert seen["timeout"] == svc.timeout, "질의는 검색 지연을 지키는 짧은 예산을 써야 한다"


@pytest.mark.asyncio
async def test_a_not_ready_sidecar_says_so_instead_of_looking_like_a_failure(monkeypatch):
    """503 은 '아직' 이고 500 은 '고장' 이다. 둘을 뭉개면 콜드스타트가 장애로 보인다."""

    class _Resp:
        status_code = 503
        text = "모델 적재 중"

        def raise_for_status(self):
            raise AssertionError("503 은 raise_for_status 이전에 다뤄져야 한다")

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json):
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    svc = EmbeddingService(model="KURE-v1", backend="sidecar", dimensions=1024)
    with pytest.raises(RuntimeError, match="준비되지 않았다"):
        await svc.embed_query("질의")
