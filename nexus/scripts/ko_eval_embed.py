"""임베딩 팔 — nomic(Ollama) · KURE-v1(sentence-transformers)
(SPEC-nexus-korean-embedding-comparison §4.3~§4.4).

**두 팔은 같은 문자열을 본다.** 프로덕션이 임베딩하는 것은 `chunk_text` 가 아니라
`get_search_text(chunk)`(섹션 경로 접두 + 본문)이고, 평가도 그것을 쓴다. 팔마다 다른 입력을 준
비교는 모델 비교가 아니다 — 그래서 행마다 `input_sha256` 을 남기고 두 팔의 집합이 같은지 본다.

**지시문 형식은 모델마다 다르다.** nomic 은 `search_document: `/`search_query: ` 를 요구하고,
KURE-v1 카드에는 지시문이 없다. 한쪽 형식을 다른 쪽에 씌우면 "그 모델을 잘못 쓴 결과" 를 재게
된다 — 토크나이저 비교에서 품사 필터가 그랬던 것과 같은 종류의 교란이다.

**절단은 재서 막는다.** KURE 는 8192 토큰까지 받지만, nomic 팔은 Ollama 가 모델 창보다 작은
컨텍스트 기본값을 씌우는 쪽이라 오히려 위험하다. 그래서 컨텍스트를 명시로 올리고, 어느 팔이든
잘릴 입력이 하나라도 있으면 **중단**한다. 잘린 팔과 온전한 팔을 비교하면 창 크기를 재게 된다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from scripts.ko_eval_vector import MODELS, input_hash

#: nomic-embed-text 의 학습 컨텍스트. Ollama 기본값(2048)보다 크므로 명시로 올린다.
NOMIC_NUM_CTX = 8192


class TruncationRisk(RuntimeError):
    """잘릴 입력이 있다. 부분적으로 잘린 팔은 결과가 아니다 (§5)."""


@dataclass
class ArmProvenance:
    """리포트에 그대로 실리는 실행 신원. 이게 없으면 재현도 반박도 못 한다 (§4.4)."""
    model: str
    backend: str
    revision: str = ""
    library: str = ""
    device: str = "cpu"
    normalized: bool | None = None
    max_seq_length: int | None = None
    observed_dim: int | None = None
    max_input_tokens: int = 0
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if v not in (None, "", {}, 0)}
        d["prefixes"] = {
            "document": MODELS[self.model]["document_prefix"] or "(없음)",
            "query": MODELS[self.model]["query_prefix"] or "(없음)",
        }
        return d


class OllamaArm:
    """nomic-embed-text — 프로덕션과 같은 백엔드, 다만 컨텍스트를 명시로 준다."""

    model = "nomic-embed-text"

    def __init__(self, base_url: str | None = None, num_ctx: int = NOMIC_NUM_CTX) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        self.num_ctx = num_ctx
        self.prov = ArmProvenance(model=self.model, backend=f"ollama num_ctx={num_ctx}")

    def _prefixed(self, text: str, kind: str) -> str:
        return MODELS[self.model][f"{kind}_prefix"] + text

    async def _embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.base_url}/api/embeddings", json={
                "model": self.model, "prompt": text, "options": {"num_ctx": self.num_ctx}})
            resp.raise_for_status()
            payload = resp.json()

        # Ollama 는 잘려도 조용히 성공한다. 토큰 수를 직접 세어 창을 넘는 입력을 잡는다.
        n = await self._count_tokens(text)
        self.prov.max_input_tokens = max(self.prov.max_input_tokens, n)
        if n > self.num_ctx:
            raise TruncationRisk(
                f"{self.model}: 입력 {n} 토큰 > 컨텍스트 {self.num_ctx} — 잘린 팔은 채점하지 않는다")
        return payload["embedding"]

    async def _count_tokens(self, text: str) -> int:
        """Ollama 는 토크나이저를 직접 노출하지 않는다. `/api/generate` 의 프롬프트 평가 수를 쓴다."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.base_url}/api/generate", json={
                "model": self.model, "prompt": text, "stream": False,
                "options": {"num_ctx": self.num_ctx, "num_predict": 0}})
            if resp.status_code != 200:
                return 0                      # 셀 수 없으면 0 — 아래 embed_documents 가 경고로 남긴다
            return int(resp.json().get("prompt_eval_count") or 0)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [await self._embed(self._prefixed(t, "document")) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return await self._embed(self._prefixed(text, "query"))


class SentenceTransformerArm:
    """KURE-v1 — 하니스 전용. `nexus/providers/` 에 배선하지 않는다 (§4.4)."""

    def __init__(self, model: str = "KURE-v1", checkpoint: str = "nlpai-lab/KURE-v1",
                 device: str = "cpu") -> None:
        from sentence_transformers import SentenceTransformer      # 하니스 컨테이너에만 있다

        self.model = model
        self.st = SentenceTransformer(checkpoint, device=device)
        self.prov = ArmProvenance(
            model=model, backend=f"sentence-transformers ({checkpoint})", device=device,
            normalized=True, max_seq_length=int(self.st.max_seq_length),
            library=_st_version(), revision=_hf_revision(self.st),
        )

    def _prefixed(self, text: str, kind: str) -> str:
        return MODELS[self.model][f"{kind}_prefix"] + text

    def _check_length(self, text: str) -> None:
        n = len(self.st.tokenizer(text)["input_ids"])
        self.prov.max_input_tokens = max(self.prov.max_input_tokens, n)
        if n > self.st.max_seq_length:
            raise TruncationRisk(
                f"{self.model}: 입력 {n} 토큰 > max_seq_length {self.st.max_seq_length} — "
                "잘린 팔은 채점하지 않는다")

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prefixed = [self._prefixed(t, "document") for t in texts]
        for t in prefixed:
            self._check_length(t)
        vecs = self.st.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)
        self.prov.observed_dim = int(vecs.shape[1])
        return [v.tolist() for v in vecs]

    async def embed_query(self, text: str) -> list[float]:
        t = self._prefixed(text, "query")
        self._check_length(t)
        return self.st.encode([t], normalize_embeddings=True,
                              show_progress_bar=False)[0].tolist()


def _st_version() -> str:
    try:
        from importlib.metadata import version
        return f"sentence-transformers {version('sentence-transformers')}, torch {version('torch')}"
    except Exception:      # noqa: BLE001 — 신원 정보는 있으면 좋고 없으면 비운다
        return ""


def _hf_revision(st_model) -> str:
    """체크포인트 커밋 sha. 같은 이름의 다른 리비전은 다른 설정이다."""
    try:
        from huggingface_hub import model_info
        return model_info(st_model.model_card_data.base_model or "nlpai-lab/KURE-v1").sha or ""
    except Exception:      # noqa: BLE001
        return ""


async def embed_pack(arm, chunk_inputs: dict[str, str]) -> list[tuple[str, str, list[float]]]:
    """`{chunk_rid: 임베딩할 문자열}` → `ko_eval_vector.replace_arm` 이 받는 행들.

    입력 문자열은 호출자가 `get_search_text` 로 만들어 넘긴다 — 양 팔이 **같은 문자열**을 보도록
    한 곳에서만 만든다.
    """
    rids = list(chunk_inputs)
    vectors = await arm.embed_documents([chunk_inputs[r] for r in rids])
    if vectors:
        arm.prov.observed_dim = arm.prov.observed_dim or len(vectors[0])
    return [(rid, input_hash(chunk_inputs[rid]), vec)
            for rid, vec in zip(rids, vectors, strict=True)]
