"""Embedding 생성 래퍼.

Ollama 직접 호출을 격리하여, 2.0에서 Jina/Late Chunking/다른 프로바이더로 교체 시
이 클래스만 수정하면 된다. Ollama API를 직접 호출하지 말 것.

사용법:
    svc = EmbeddingService()
    vectors = await svc.embed(["query: 결제 서비스 의존성"])
"""

from __future__ import annotations

import os

import httpx


class EmbeddingService:
    """임베딩 생성. Ollama API 호출을 격리."""

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str | None = None,
        dimensions: int = 768,
    ) -> None:
        self.model = model
        self.base_url = base_url or os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.dimensions = dimensions
        # nomic 모델의 prefix 규칙. 이걸 안 쓰면 품질이 크게 떨어짐.
        self.document_prefix = "search_document: "
        self.query_prefix = "search_query: "

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
        """Ollama API 배치 호출. retry 3회."""
        results = []
        async with httpx.AsyncClient(timeout=60.0) as client:
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
