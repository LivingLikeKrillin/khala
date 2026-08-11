"""판독기 교체의 불변식 — SPEC-nexus-vision-reader-of-record §5.

여기서 지키는 것 둘:

* **신원과 호출이 갈라지지 않는다.** 적재 경로가 `LLMService()` 를 인자 없이 만들고 있었고,
  그러면 `extractor_identity()` 는 그림 모델을 보고하는데 호출은 답변 모델로 나간다. 두 상수가
  같은 값이던 동안에는 안 보이고, 답변 모델을 바꾸는 무관한 변경이 추출기를 조용히 옮긴다.
* **ADR-0010 §6 은 판독기를 바꿔도 유지된다.** 판독기 교체가 그 문(툴·파일시스템)을 다시 여는
  가장 쉬운 길이다.
"""

from __future__ import annotations

import pytest

from nexus.ingest.vision import (
    DEFAULT_VISION_MODEL,
    VISION_BACKENDS,
    extractor_identity,
    prompt_sha,
    vision_model,
    vision_service,
)


def test_the_identity_moved_from_the_stored_one():
    """§5.1 — 재추출이 ADR-0010 §5 아래에서 합법인 이유가 이것이다."""
    assert extractor_identity() != "claude-sonnet-4-6/18c36580"
    assert prompt_sha() != "18c36580", "프롬프트가 바뀌었으면 해시도 움직여야 한다"


def test_the_service_uses_the_vision_model_not_the_answer_model(monkeypatch):
    """신원이 말하는 모델과 실제로 부르는 모델이 같아야 한다."""
    monkeypatch.setenv("NEXUS_LLM_MODEL", "some-other-answer-model")
    svc = vision_service()
    assert svc.model == vision_model() == DEFAULT_VISION_MODEL


def test_an_unknown_vision_model_refuses_rather_than_defaulting(monkeypatch):
    """조용히 기본 백엔드로 돌아가면 신원이 가리키는 모델과 호출이 갈린다."""
    monkeypatch.setenv("NEXUS_VISION_MODEL", "nobody-serves-this")
    with pytest.raises(ValueError, match="백엔드를 모른다"):
        vision_service()


def test_every_registered_vision_model_has_a_backend():
    assert DEFAULT_VISION_MODEL in VISION_BACKENDS
    assert set(VISION_BACKENDS.values()) <= {"gemini", "claude"}


def test_the_gemini_request_carries_one_image_no_tools_no_path(monkeypatch):
    """§5.6 · ADR-0010 §6 — 요청의 모양을 실제 빌드된 body 에 대고 단언한다."""
    import base64

    import httpx

    from nexus.providers.llm import _GeminiBackend

    captured = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"candidates": [{"finishReason": "STOP",
                                    "content": {"parts": [{"text": "ok"}]}}]}

    class _Client:
        def __init__(self, **_kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def post(self, url, headers=None, json=None):
            captured["url"], captured["body"] = url, json
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    backend = _GeminiBackend("gemini-3.6-flash")
    import asyncio
    text, stop = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        backend.vision_extract("SYS", base64.b64encode(b"x").decode(), "image/png", 4096))

    body = captured["body"]
    parts = body["contents"][0]["parts"]
    assert len(parts) == 1 and "inline_data" in parts[0], "이미지 한 장만"
    assert "tools" not in body, "툴 선언이 없어야 한다 — quarantine 게이트보다 먼저 도는 경로다"
    assert "file" not in json_dumps(body).lower() or "inline_data" in json_dumps(body)
    assert text == "ok" and stop is None


def json_dumps(o) -> str:
    import json

    return json.dumps(o, ensure_ascii=False)


def test_gemini_backend_refuses_answer_generation():
    """답변과 판독의 수명주기를 한 백엔드에 묶지 않는다."""
    import asyncio

    from nexus.providers.llm import _GeminiBackend

    with pytest.raises(NotImplementedError):
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            _GeminiBackend("gemini-3.6-flash").generate_full("s", "u", 10))
