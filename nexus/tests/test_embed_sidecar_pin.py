"""사이드카의 체크포인트 핀은 **기제**여야지 선언이면 안 된다
(SPEC-nexus-embedding-cutover-seam §4.5).

리비전이 안 박히면 `main` 이 가리키는 무엇이든 받는다. 차원이 같으면 **아무 경고 없이 다른 벡터**가
나오고, 컬럼 절반이 옛 체크포인트인 상태를 만들 수 있다 — 차원 검사(§4.1)도, 세대 정합성 검사(§4.2)도
그걸 못 잡는다. 그래서 여기서 지키는 것은 하나다: **env 로 준 리비전이 실제로 로더까지 가는가.**

"핀 안 하면 `(unpinned)` 이라고 보고한다" 는 음성 케이스만 증명한다 — 그래서 양성도 측정한다.
"""

from __future__ import annotations

import importlib
import sys

import pytest

PINNED = "d14c8a9423946e268a0c9952fecf3a7aabd73bd9"


@pytest.fixture
def sidecar(monkeypatch):
    """`embed_service.app` 을 env 와 함께 새로 적재한다 — 모듈 상수는 임포트 시점에 굳는다."""

    def _load(revision: str | None):
        for var, value in (("EMBED_REVISION", revision),):
            if value is None:
                monkeypatch.delenv(var, raising=False)
            else:
                monkeypatch.setenv(var, value)
        sys.modules.pop("embed_service.app", None)
        return importlib.import_module("embed_service.app")

    return _load


def test_the_pin_reaches_the_loader(sidecar, monkeypatch):
    """핵심 주장 — 이게 안 되면 compose 에 적은 커밋은 주석이나 다름없다."""
    mod = sidecar(PINNED)
    seen = {}

    class _Model:
        def get_sentence_embedding_dimension(self):
            return 1024

        max_seq_length = 8192

        def encode(self, *a, **kw):
            return [[0.0] * 1024]

        def tokenizer(self, *a, **kw):
            return {"input_ids": [0]}

    class _ST:
        def __init__(self, checkpoint, **kwargs):
            seen["checkpoint"], seen["kwargs"] = checkpoint, kwargs

        def __new__(cls, checkpoint, **kwargs):
            seen["checkpoint"], seen["kwargs"] = checkpoint, kwargs
            return _Model()

    fake = type(sys)("sentence_transformers")
    fake.SentenceTransformer = _ST
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)

    import asyncio

    asyncio.run(mod._load())

    assert seen["checkpoint"] == "nlpai-lab/KURE-v1"
    assert seen["kwargs"].get("revision") == PINNED, (
        "리비전이 로더까지 가지 않으면 핀은 문서일 뿐이고, 같은 이름의 다른 체크포인트가 "
        "조용히 섞인다")


def test_health_reports_the_pin_it_was_given(sidecar):
    import asyncio

    mod = sidecar(PINNED)
    assert asyncio.run(mod.health())["revision"] == PINNED


def test_an_unpinned_sidecar_says_so_rather_than_looking_pinned(sidecar):
    """음성 대조군. 빈 값이 조용히 '핀 됨' 처럼 보이면 운영자는 확인할 방법이 없다."""
    import asyncio

    mod = sidecar(None)
    assert asyncio.run(mod.health())["revision"] == "(unpinned)"
