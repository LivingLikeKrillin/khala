"""임베딩 사이드카 — KURE-v1 을 sentence-transformers 로 서빙한다
(SPEC-nexus-kure-embedding-swap §4.1).

Ollama 가 KURE 를 싣지 않는다. 변환본을 만들어 끼우면 **측정과 프로덕션 사이에 핀 안 된 변환이
하나 낀다** — 그 변환이 무엇을 바꿨는지는 아무도 재지 않았고, 그러면 앞선 비교의 숫자가 프로덕션을
말해주지 못한다. 그래서 평가에서 쓴 것과 **같은 체크포인트·같은 라이브러리**를 그대로 서빙한다.

**프리픽스는 여기서 붙이지 않는다.** 모델별 지시문 형식은 `EmbeddingService` 의 정책이고(§4.3),
정책이 두 군데 있으면 언젠가 갈라진다. 이 서비스는 받은 문자열을 그대로 임베딩한다.

**준비 상태를 거짓말하지 않는다.** 모델 적재에 ~9초, 첫 추론에 그보다 더 걸린다. `/health` 의
`ready` 는 **워밍업 추론까지 끝난 뒤**에 켜진다 — "적재됨" 을 준비로 신고했더니 첫 질의가
클라이언트 타임아웃(10초)을 넘겼다(2026-08-04 실측). compose 가 이 신호로 앱을 띄우고, 클라이언트
타임아웃(§4.1)이 나머지 절반을 맡는다.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

MODEL_NAME = os.getenv("EMBED_MODEL", "KURE-v1")
CHECKPOINT = os.getenv("EMBED_CHECKPOINT", "nlpai-lab/KURE-v1")
#: 체크포인트는 **리비전으로 못박는다.** 같은 이름의 다른 리비전은 다른 모델이고, 차원이 같으면
#: 아무 경고 없이 벡터만 달라진다 — 색인 절반이 옛 리비전인 상태를 만들 수 있다.
REVISION = os.getenv("EMBED_REVISION", "")
DEVICE = os.getenv("EMBED_DEVICE", "cpu")

_state: dict = {"model": None, "error": None, "dim": None, "max_seq": None}


async def _load() -> None:
    def _blocking():
        from sentence_transformers import SentenceTransformer

        kwargs = {"device": DEVICE}
        if REVISION:
            kwargs["revision"] = REVISION
        model = SentenceTransformer(CHECKPOINT, **kwargs)
        dim = int(model.get_sentence_embedding_dimension())
        # **적재됐다는 것과 답할 수 있다는 것은 다르다.** 첫 추론은 이후 요청보다 몇 배 느리고,
        # 준비 신호가 그 전에 켜지면 클라이언트 타임아웃이 첫 질의에서 터진다 — 실제로 그렇게
        # 터졌다(10초 타임아웃 초과, 2026-08-04). 그래서 워밍업 추론까지 마친 뒤에 켠다.
        model.encode(["워밍업"], normalize_embeddings=True, show_progress_bar=False)
        model.tokenizer("워밍업")          # 토크나이저도 첫 호출에 자산을 더 연다
        return model, dim, int(model.max_seq_length)

    try:
        _state["model"], _state["dim"], _state["max_seq"] = await asyncio.to_thread(_blocking)
    except Exception as e:                      # noqa: BLE001 — 어떤 실패든 준비되지 않은 것이다
        _state["error"] = f"{type(e).__name__}: {e}"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_load())         # 적재를 기다리지 않고 뜬다 — /health 가 진실을 말한다
    yield
    task.cancel()


app = FastAPI(title="nexus-embed", lifespan=lifespan)


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1)


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    model: str
    dim: int


@app.get("/health")
async def health() -> dict:
    return {
        "ready": _state["model"] is not None,
        "model": MODEL_NAME,
        "checkpoint": CHECKPOINT,
        "revision": REVISION or "(unpinned)",
        "device": DEVICE,
        "dim": _state["dim"],
        "max_seq_length": _state["max_seq"],
        "error": _state["error"],
    }


@app.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest) -> EmbedResponse:
    model = _state["model"]
    if model is None:
        # 503 이라야 클라이언트가 "아직" 과 "고장" 을 구분할 수 있다.
        raise HTTPException(status_code=503, detail=_state["error"] or "모델 적재 중")

    too_long = [t for t in req.texts if len(model.tokenizer(t)["input_ids"]) > model.max_seq_length]
    if too_long:
        # **조용히 자르지 않는다.** sentence-transformers 의 기본 동작이 그것이고, 잘린 벡터는
        # 잘렸다는 사실조차 남기지 않는다 (SPEC §4.3 의 절단 규칙).
        raise HTTPException(
            status_code=413,
            detail=f"입력 {len(too_long)}건이 max_seq_length({model.max_seq_length})를 넘는다")

    vectors = await asyncio.to_thread(
        lambda: model.encode(req.texts, normalize_embeddings=True, show_progress_bar=False))
    return EmbedResponse(embeddings=[v.tolist() for v in vectors],
                         model=MODEL_NAME, dim=_state["dim"])
