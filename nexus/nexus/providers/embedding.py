"""Embedding 생성 래퍼.

Ollama·사이드카 호출을 격리하여, 모델/백엔드 교체 시 이 클래스만 수정하면 된다. 외부 임베딩
API 를 직접 호출하지 말 것.

**지시문 형식은 모델마다 다르고, 그 정책은 여기 한 곳에 산다** (SPEC-nexus-kure-embedding-swap
§4.3). nomic 은 `search_document: `/`search_query: ` 를 요구하고, KURE-v1 의 카드에는 지시문이
없다. 한쪽 형식을 다른 쪽에 씌우면 "그 모델을 잘못 쓴 결과" 를 재게 된다 — 한국어 임베딩 비교가
제거한 교란을 프로덕션에서 되살리는 길이다. 그래서 모순되는 설정은 **기동 시점에 실패**한다.

사용법:
    svc = EmbeddingService()
    vectors = await svc.embed_documents(["결제 서비스 의존성"])
"""

from __future__ import annotations

import os

import httpx

#: 모델별 기본 지시문 형식. 값은 모델 카드에서 온다 — 추측이 아니다.
#: `("", "")` 는 "이 모델은 지시문을 쓰지 않는다" 는 **적극적 사실**이고, 미지정과 다르다.
MODEL_PREFIXES: dict[str, tuple[str, str]] = {
    "nomic-embed-text": ("search_document: ", "search_query: "),
    "KURE-v1": ("", ""),
}

_UNSET = object()      # "설정에 키가 없음" 과 "빈 문자열로 지정됨" 을 구분하기 위한 표식


class UnknownEmbeddingModel(ValueError):
    """레지스트리에 없는 모델. 조용히 nomic 형식을 물려주면 그 모델을 잘못 쓰게 된다."""


class ConflictingPrefixConfig(ValueError):
    """카드에 지시문이 없는 모델에 지시문을 설정했다. 기동을 막는다 — 이게 그 교란의 재유입 경로다."""


def resolve_prefixes(model: str, document_prefix=_UNSET, query_prefix=_UNSET) -> tuple[str, str]:
    """(document, query) 지시문. 우선순위와 빈 값의 의미를 여기서 못박는다 (§4.3).

    - 레지스트리에 없는 모델 → `UnknownEmbeddingModel`
    - 설정 키가 없으면 → 모델 기본값
    - 키가 **있고 빈 문자열**이면 → 지시문 없음 (기본값을 덮는다)
    - 기본값이 빈 문자열인 모델에 비어 있지 않은 지시문을 설정하면 → `ConflictingPrefixConfig`
    """
    if model not in MODEL_PREFIXES:
        raise UnknownEmbeddingModel(
            f"{model!r} 의 지시문 형식을 모른다. MODEL_PREFIXES 에 모델 카드가 말하는 값을 "
            "추가하라 — 기본값을 물려주면 그 모델을 잘못 쓰게 된다.")

    default_doc, default_query = MODEL_PREFIXES[model]
    doc = default_doc if document_prefix is _UNSET else str(document_prefix)
    query = default_query if query_prefix is _UNSET else str(query_prefix)

    if (default_doc, default_query) == ("", "") and (doc or query):
        raise ConflictingPrefixConfig(
            f"{model!r} 의 카드에는 지시문이 없는데 설정이 지시문을 준다 "
            f"(document={doc!r}, query={query!r}). 다른 모델의 형식을 씌우면 그 모델을 잘못 쓴 "
            "결과를 재게 된다.")
    return doc, query


class EmbeddingService:
    """임베딩 생성. Ollama API 호출을 격리."""

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str | None = None,
        dimensions: int = 768,
        backend: str | None = None,
        document_prefix=_UNSET,
        query_prefix=_UNSET,
        timeout: float | None = None,
    ) -> None:
        self.model = model
        self.backend = (backend or os.getenv("EMBEDDING_BACKEND", "ollama")).strip().lower()
        if self.backend not in ("ollama", "sidecar"):
            raise ValueError(f"알 수 없는 임베딩 백엔드: {self.backend!r} (ollama | sidecar)")
        default_url = (os.getenv("EMBED_URL", "http://localhost:8080") if self.backend == "sidecar"
                       else os.getenv("OLLAMA_URL", "http://localhost:11434"))
        self.base_url = (base_url or default_url).rstrip("/")
        self.dimensions = dimensions
        # 지시문은 모델 정책이다 — 여기서 결정하고, 모순이면 기동을 막는다 (§4.3).
        self.document_prefix, self.query_prefix = resolve_prefixes(
            model, document_prefix, query_prefix)
        # 타임아웃이 있어야 "느려짐" 이 "멈춤" 이 되지 않는다. 사이드카는 콜드스타트가 ~9초라
        # 준비 전에는 503 을 주는데, 그걸 기다리며 검색을 붙잡고 있으면 안 된다 (§4.1, §5).
        self.timeout = timeout if timeout is not None else float(
            os.getenv("EMBEDDING_TIMEOUT", "10" if self.backend == "sidecar" else "60"))

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """문서/chunk용 임베딩 생성. document_prefix 자동 적용."""
        prefixed = [f"{self.document_prefix}{t}" for t in texts]
        return await self._embed_batch(prefixed)

    async def embed_query(self, query: str) -> list[float]:
        """검색 쿼리용 임베딩 생성. query_prefix 자동 적용."""
        prefixed = f"{self.query_prefix}{query}"
        results = await self._embed_batch([prefixed])
        return results[0]

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        if self.backend == "sidecar":
            return await self._embed_batch_sidecar(texts)
        return await self._embed_batch_ollama(texts)

    async def _embed_batch_sidecar(self, texts: list[str]) -> list[list[float]]:
        """사이드카 한 번 호출로 배치. 프리픽스는 이미 붙어서 들어온다."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/embed", json={"texts": texts})
        if resp.status_code == 503:
            raise RuntimeError(f"임베딩 사이드카가 아직 준비되지 않았다: {resp.text[:200]}")
        resp.raise_for_status()
        return resp.json()["embeddings"]

    async def _embed_batch_ollama(self, texts: list[str]) -> list[list[float]]:
        """Ollama API 배치 호출. retry 3회."""
        results = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for text in texts:
                for attempt in range(3):
                    try:
                        resp = await client.post(
                            f"{self.base_url}/api/embeddings",
                            json={"model": self.model, "prompt": text},
                        )
                        resp.raise_for_status()
                        results.append(resp.json()["embedding"])
                        break
                    except (httpx.HTTPError, KeyError) as e:
                        if attempt == 2:
                            raise RuntimeError(f"Embedding 실패 (3회 재시도 후): {e}") from e
                        import asyncio
                        await asyncio.sleep(2 ** attempt)
        return results

    def get_model_name(self) -> str:
        return self.model

    def get_dimensions(self) -> int:
        return self.dimensions
