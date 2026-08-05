"""임베딩 팔 — nomic(Ollama) · KURE-v1(sentence-transformers)
(SPEC-nexus-korean-embedding-comparison §4.3~§4.4).

**두 팔은 같은 문자열을 본다.** 프로덕션이 임베딩하는 것은 `chunk_text` 가 아니라
`get_search_text(chunk)`(섹션 경로 접두 + 본문)이고, 평가도 그것을 쓴다. 팔마다 다른 입력을 준
비교는 모델 비교가 아니다 — 그래서 행마다 `input_sha256` 을 남기고 두 팔의 집합이 같은지 본다.

**지시문 형식은 모델마다 다르다.** nomic 은 `search_document: `/`search_query: ` 를 요구하고,
KURE-v1 카드에는 지시문이 없다. 한쪽 형식을 다른 쪽에 씌우면 "그 모델을 잘못 쓴 결과" 를 재게
된다 — 토크나이저 비교에서 품사 필터가 그랬던 것과 같은 종류의 교란이다.

**절단과 거부는 다르게 다룬다.** sentence-transformers 는 `max_seq_length` 에서 **조용히 자르므로**
인코딩 전에 자기 토크나이저로 세어 넘치면 중단한다 — 잘린 팔과 온전한 팔을 비교하면 창 크기를
재게 된다. Ollama 는 반대로 **거부**한다(HTTP 500 + `exceeds the context length`), 그래서 자르지
않았음이 관측으로 확인되고, 거부된 청크는 프로덕션이 그러듯 없는 것으로 두고 커버리지로 센다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from scripts.ko_eval_vector import MODELS, EmbedRow, sha256

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
    refused: int = 0
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if v not in (None, "", {}, 0)}
        d["prefixes"] = {
            "document": MODELS[self.model]["document_prefix"] or "(없음)",
            "query": MODELS[self.model]["query_prefix"] or "(없음)",
        }
        return d


class OllamaArm:
    """nomic-embed-text — 프로덕션과 같은 백엔드.

    **창은 올릴 수 없다.** `PARAMETER num_ctx 8192` 로 파생 모델을 만들어도 Ollama 의
    nomic-embed-text 는 여전히 ~2,042 한글 문자에서 거부한다(2026-08-04 이분탐색). 그리고 거부는
    조용한 절단이 아니라 HTTP 500 + `the input length exceeds the context length` 다 — 그래서
    **자르지 않았다는 것이 관측으로 확인된다.** 거부된 청크는 프로덕션에서처럼 없는 것으로 둔다.
    """

    model = "nomic-embed-text"
    REFUSAL_MARK = "exceeds the context length"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        self.prov = ArmProvenance(model=self.model, backend="ollama (창은 모델 빌드가 고정)")
        self.max_payload_chars = 0

    def prefixed(self, text: str, kind: str) -> str:
        return MODELS[self.model][f"{kind}_prefix"] + text

    async def embed_one(self, payload: str) -> tuple[list[float] | None, str | None]:
        """(벡터, 거부사유). 거부는 예외가 아니라 값으로 돌려준다 — 회계 대상이기 때문이다."""
        self.max_payload_chars = max(self.max_payload_chars, len(payload))
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(f"{self.base_url}/api/embeddings",
                                     json={"model": self.model, "prompt": payload})
        if resp.status_code == 200:
            return resp.json()["embedding"], None
        reason = resp.text.strip()[:300]
        if self.REFUSAL_MARK in reason:
            return None, reason
        raise RuntimeError(f"{self.model}: 예상 못한 실패 {resp.status_code} — {reason}")

    async def embed_query(self, text: str) -> list[float]:
        vec, reason = await self.embed_one(self.prefixed(text, "query"))
        if vec is None:
            raise RuntimeError(f"{self.model}: 질의가 거부됐다 — {reason}")
        return vec


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

    def prefixed(self, text: str, kind: str) -> str:
        return MODELS[self.model][f"{kind}_prefix"] + text

    def _check_length(self, text: str) -> None:
        n = len(self.st.tokenizer(text)["input_ids"])
        self.prov.max_input_tokens = max(self.prov.max_input_tokens, n)
        if n > self.st.max_seq_length:
            raise TruncationRisk(
                f"{self.model}: 입력 {n} 토큰 > max_seq_length {self.st.max_seq_length} — "
                "잘린 팔은 채점하지 않는다")

    async def embed_one(self, payload: str) -> tuple[list[float] | None, str | None]:
        """sentence-transformers 는 **조용히 자른다.** 그래서 인코딩 전에 자기 토크나이저로 센다."""
        self._check_length(payload)
        vec = self.st.encode([payload], normalize_embeddings=True,
                             show_progress_bar=False)[0]
        self.prov.observed_dim = int(len(vec))
        return vec.tolist(), None

    async def embed_query(self, text: str) -> list[float]:
        vec, _ = await self.embed_one(self.prefixed(text, "query"))
        return vec


def _st_version() -> str:
    try:
        from importlib.metadata import version
        return f"sentence-transformers {version('sentence-transformers')}, torch {version('torch')}"
    except Exception:      # noqa: BLE001 — 신원 정보는 있으면 좋고 없으면 비운다
        return ""


def _hf_revision(st_model) -> str:
    """체크포인트 커밋 sha. 같은 이름의 다른 리비전은 다른 설정이다.

    **로드된 스냅샷에서 읽는다.** 예전에는 `model_info()` 로 허브에 물었는데, 그건 두 가지가
    틀렸다 — 네트워크가 없으면 예외를 삼키고 **빈 문자열**을 내서, 어떤 가중치를 썼는지 식별하는
    필드가 확인이 가장 어려운 상황에서 조용히 사라진다. 그리고 물어본 것은 "허브의 main 이 **지금**
    무엇인가" 이지 "이 팔이 **무엇을 로드했는가**" 가 아니다. 캐시 스냅샷 디렉터리 이름이 곧
    커밋 sha 이므로 그쪽이 더 진실하다.
    """
    from pathlib import Path as _Path

    cfg = getattr(getattr(st_model[0], "auto_model", None), "config", None)
    repo_id = getattr(cfg, "_name_or_path", None) or "nlpai-lab/KURE-v1"
    try:
        from huggingface_hub import snapshot_download
        return _Path(snapshot_download(repo_id, local_files_only=True)).name
    except Exception:      # noqa: BLE001 — 캐시에 없으면 허브에 묻는다
        try:
            from huggingface_hub import model_info
            return model_info(repo_id).sha or ""
        except Exception:  # noqa: BLE001
            return ""


async def embed_pack(arm, chunk_inputs: dict[str, str]) -> list[EmbedRow]:
    """`{chunk_rid: 공용 입력}` → 팔의 결과 행들 (임베딩 또는 거부).

    공용 입력은 호출자가 `get_search_text` 로 **한 곳에서** 만들어 넘긴다. 프리픽스는 여기서
    팔마다 붙이고, 그 결과를 `payload_sha256` 으로 따로 남긴다 — 두 팔의 공용 입력은 같아야
    하지만 실제 보낸 문자열은 같을 수 없다.
    """
    rows: list[EmbedRow] = []
    for rid, text in chunk_inputs.items():
        payload = arm.prefixed(text, "document")
        vec, reason = await arm.embed_one(payload)
        rows.append(EmbedRow(chunk_rid=rid, input_sha256=sha256(text),
                             payload_sha256=sha256(payload),
                             embedding=vec, refusal_reason=reason))
    embedded = [r for r in rows if r.embedding is not None]
    if embedded:
        arm.prov.observed_dim = arm.prov.observed_dim or len(embedded[0].embedding)
    arm.prov.refused = sum(1 for r in rows if r.embedding is None)
    return rows
