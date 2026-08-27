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
import structlog

logger = structlog.get_logger(__name__)

#: 모델별 기본 지시문 형식. 값은 모델 카드에서 온다 — 추측이 아니다.
#: `("", "")` 는 "이 모델은 지시문을 쓰지 않는다" 는 **적극적 사실**이고, 미지정과 다르다.
MODEL_PREFIXES: dict[str, tuple[str, str]] = {
    "nomic-embed-text": ("search_document: ", "search_query: "),
    "KURE-v1": ("", ""),
}

#: 모델의 출력 차원. **설정이 아니라 모델의 사실**이므로 여기 산다
#: (SPEC-nexus-embedding-cutover-seam §4.1). 설정에 같은 숫자를 또 적으면 세 번째 진실이 생긴다.
MODEL_DIMENSIONS: dict[str, int] = {
    "nomic-embed-text": 768,
    "KURE-v1": 1024,
}

#: 이 시스템에서 **오늘** 각 모델을 서빙하는 방식. 모델의 속성이 아니라 배포의 사실이다 —
#: GGUF 변환본을 Ollama 로 띄우는 길은 이 표가 막고, 그 마찰은 의도된 것이다(변환이 곧 핀 안 된
#: 한 단계다, swap SPEC §4.1). 뚫으려면 테스트와 함께 코드를 고친다. 설정 키가 아니다.
MODEL_BACKENDS: dict[str, str] = {
    "nomic-embed-text": "ollama",
    "KURE-v1": "sidecar",
}

_UNSET = object()      # "설정에 키가 없음" 과 "빈 문자열로 지정됨" 을 구분하기 위한 표식


class UnknownEmbeddingModel(ValueError):
    """레지스트리에 없는 모델. 조용히 nomic 형식을 물려주면 그 모델을 잘못 쓰게 된다."""


class ConflictingPrefixConfig(ValueError):
    """카드에 지시문이 없는 모델에 지시문을 설정했다. 기동을 막는다 — 이게 그 교란의 재유입 경로다."""


class InconsistentEmbeddingGeneration(ValueError):
    """모델·컬럼·백엔드가 한 세대를 가리키지 않는다.

    컷오버는 셋을 함께 움직이는 일이고, 하나만 움직인 상태는 **조용히 틀린다**: 빈 컬럼일 때는
    조회 조건이 0행이라 아무 일도 안 일어나다가, 재임베딩이 끝나 행이 차는 순간 pgvector 가
    `different vector dimensions` 를 낸다. 그래서 여기서 막는다 (SPEC-nexus-embedding-cutover-seam §4.2).
    """


class WrongVectorDimensions(ValueError):
    """백엔드가 이 모델의 차원이 아닌 벡터를 돌려줬다.

    `MODEL_DIMENSIONS` 는 **재기 전까지 가정**이다. Matryoshka 절단, 잘못 띄운 사이드카, 헤드가
    바뀐 체크포인트가 전부 이 모양으로 온다 — 안 세면 pgvector 오류나 조용한 랭킹 저하로 나타난다.
    """


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
        # **질의와 문서 배치는 다른 예산을 쓴다.** 질의 타임아웃은 검색 지연을 지키는 장치라
        # 짧아야 하고, 문서 배치는 오프라인이라 길어야 한다. 하나로 묶었더니 16건 배치(≈35초)가
        # 질의용 10초에 걸려 전부 ReadTimeout 났다 (2026-08-04 실측).
        self.timeout = timeout if timeout is not None else float(
            os.getenv("EMBEDDING_TIMEOUT", "10" if self.backend == "sidecar" else "60"))
        self.batch_timeout = float(os.getenv("EMBEDDING_BATCH_TIMEOUT", "600"))

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """문서/chunk용 임베딩 생성. document_prefix 자동 적용.

        **배치 예산을 쓴다** — 문서 임베딩은 요청 경로가 아니라 적재/마이그레이션 경로다.
        """
        prefixed = [f"{self.document_prefix}{t}" for t in texts]
        return await self._embed_batch(prefixed, timeout=self.batch_timeout)

    async def embed_query(self, query: str) -> list[float]:
        """검색 쿼리용 임베딩 생성. query_prefix 자동 적용."""
        prefixed = f"{self.query_prefix}{query}"
        results = await self._embed_batch([prefixed])
        return results[0]

    async def _embed_batch(self, texts: list[str], timeout: float | None = None) -> list[list[float]]:
        if self.backend == "sidecar":
            vectors = await self._embed_batch_sidecar(texts, timeout)
        else:
            vectors = await self._embed_batch_ollama(texts, timeout)
        return self._checked(vectors)

    def _checked(self, vectors: list[list[float]]) -> list[list[float]]:
        """차원을 **센다**. 표가 맞다고 믿고 넘기면 그 거짓말은 DB 나 랭킹에서 드러난다."""
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise WrongVectorDimensions(
                    f"{self.model!r}({self.backend}) 가 {len(vector)} 차원 벡터를 돌려줬다 — "
                    f"기대는 {self.dimensions} 차원이다. 체크포인트·차원 설정·서빙 중 하나가 "
                    "다른 모델을 가리키고 있다.")
        return vectors

    async def _embed_batch_sidecar(self, texts: list[str],
                                   timeout: float | None = None) -> list[list[float]]:
        """사이드카 한 번 호출로 배치. 프리픽스는 이미 붙어서 들어온다."""
        async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
            resp = await client.post(f"{self.base_url}/embed", json={"texts": texts})
        if resp.status_code == 503:
            raise RuntimeError(f"임베딩 사이드카가 아직 준비되지 않았다: {resp.text[:200]}")
        resp.raise_for_status()
        return resp.json()["embeddings"]

    async def _embed_batch_ollama(self, texts: list[str],
                                  timeout: float | None = None) -> list[list[float]]:
        """Ollama API 배치 호출. retry 3회."""
        results = []
        async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
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


# ── 세대 seam: 어느 모델이·어느 컬럼에·어느 백엔드로 ─────────────────────────
#
# 프로덕션의 여섯 군데가 각자 `EmbeddingService()` 를 기본값으로 만들고 있었다. 그래서 설정의
# `search.embedding_column` 을 바꿔도 질의 벡터는 nomic 768 차원 그대로였다. 세대를 정하는 곳은
# 여기 하나여야 하고, 세대는 **셋이 함께**여야 한다 (SPEC-nexus-embedding-cutover-seam §4.1~4.2).

#: 배포가 세대를 움직이는 식별자. `NEXUS_` 접두는 공용 `.env` 에서의 충돌·오타 때문이다.
#: 백엔드만 접두 없는 옛 이름(`EMBEDDING_BACKEND`)도 계속 읽는다 — 이미 쓰이고 있어서,
#: 조용히 무시하면 배포는 자기가 무시당한 줄 모른다. 접두 있는 쪽이 이긴다.
ENV_MODEL = "NEXUS_EMBEDDING_MODEL"
ENV_BACKEND = "NEXUS_EMBEDDING_BACKEND"
ENV_BACKEND_LEGACY = "EMBEDDING_BACKEND"


def _pick(env_names: tuple[str, ...], config_value, default):
    """(값, 출처). env 가 설정을 이긴다 — 이 배포는 `config.yaml` 을 git 워킹트리에서 읽는다."""
    for name in env_names:
        raw = os.getenv(name)
        if raw is not None and raw.strip():
            return raw.strip(), f"env:{name}"
    if config_value is not None and str(config_value).strip():
        return str(config_value).strip(), "config"
    return default, "default"


def embedding_service_from_config(cfg: dict | None = None) -> EmbeddingService:
    """설정+env 로 임베딩 서비스를 만든다. **모순이면 만들지 않는다.**

    프로덕션에서 `EmbeddingService()` 를 직접 만들지 말 것 — 그러면 그 프로세스만 다른 세대를 쓰게
    되고, 적재 경로가 그러면 **다른 세대의 컬럼에 벡터를 쓴다**.
    """
    from nexus.index.vector_index import configured_column, dimensions_of

    cfg = cfg or {}
    embed_cfg = cfg.get("embedding") or {}

    model, model_src = _pick((ENV_MODEL,), embed_cfg.get("model"), "nomic-embed-text")
    backend, backend_src = _pick((ENV_BACKEND, ENV_BACKEND_LEGACY), embed_cfg.get("backend"),
                                 "ollama")
    column = configured_column(cfg)                      # 화이트리스트를 통과한 이름만 나온다

    if model not in MODEL_DIMENSIONS:                    # 프리픽스 레지스트리와 같은 규칙
        raise UnknownEmbeddingModel(
            f"{model!r} 의 차원을 모른다. MODEL_DIMENSIONS 에 모델 카드가 말하는 값을 추가하라.")

    expected_dim = MODEL_DIMENSIONS[model]
    column_dim = dimensions_of(column)
    expected_backend = MODEL_BACKENDS[model]

    if column_dim != expected_dim or backend != expected_backend:
        raise InconsistentEmbeddingGeneration(
            f"임베딩 세대가 어긋났다: model={model!r} ({expected_dim}d, {expected_backend} 로 "
            f"서빙됨) · column={column!r} ({column_dim}d) · backend={backend!r}. "
            "컷오버는 셋을 함께 움직이는 일이다 — 이 배포는 일부만 움직였다.")

    declared = embed_cfg.get("dimensions")
    if declared is not None and int(declared) != expected_dim:
        raise InconsistentEmbeddingGeneration(
            f"embedding.dimensions={declared} 가 model={model!r} 의 차원 {expected_dim} 과 "
            "다르다. 이 키는 모델이 결정하므로 설정에서 지워라 — 남겨 두면 세 번째 진실이 된다.")

    logger.info("embedding_generation_resolved", model=model, model_source=model_src,
                column=column, backend=backend, backend_source=backend_src,
                dimensions=expected_dim)

    return EmbeddingService(
        model=model, backend=backend, dimensions=expected_dim,
        document_prefix=embed_cfg.get("document_prefix", _UNSET),
        query_prefix=embed_cfg.get("query_prefix", _UNSET),
    )
