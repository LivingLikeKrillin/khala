"""길이검사는 자기 토크나이저를 쓴다 (SPEC-nexus-embed-tokenizer-race §5).

부하에서 사이드카가 500 을 냈다(`RuntimeError: Already borrowed`, 400건 중 2건 @C=4). 원인은
길이검사가 **모델의** 토크나이저를 이벤트 루프에서 부르는 동안 워커 스레드의 `encode` 가 같은 Rust
객체를 빌린 것이다. 수정은 검사용 사본이고, 그 안전성은 두 방향의 불변식에 기댄다:

1. 이벤트 루프의 코드가 **모델의** 토크나이저를 부르지 않는다
2. 워커 스레드가 **사본을** 부르지 않는다

여기서는 둘 다 잰다. 경합 자체를 타이밍으로 재는 시험은 넣지 않는다 — 그런 시험은 흔들리다 결국
지워지고, 경합의 근거는 SPEC §1 의 마이크로벤치(양성 대조군 포함)가 댄다.
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import pathlib
import sys
import threading

import pytest
from fastapi import HTTPException

APP_SRC = pathlib.Path(__file__).resolve().parents[1] / "embed_service" / "app.py"


class _RaisingTokenizer:
    """모델의 토크나이저 — **무장한 뒤에 불리면 실패한다.**

    무장 시점이 있는 이유는 불변식이 "아무도 안 만진다" 가 아니기 때문이다: 적재 단계의 워밍업과
    파리티 검사는 한 스레드에서 도는 정상 사용이고, 금지되는 것은 **요청 핸들러가** 이걸 만지는
    것이다. 적재가 끝난 뒤 픽스처가 무장한다.

    `__deepcopy__` 가 순한 쌍둥이를 돌려주는 것이 이 가짜의 나머지 절반이다: 그게 없으면 사본도
    똑같이 터져서 "사본을 쓴다" 를 증명할 수 없다(비평이 이전 초안에서 잡은 자기모순).
    """

    def __init__(self, twin: "_CountingTokenizer"):
        self.twin, self.model_max_length, self.armed = twin, twin.model_max_length, False

    def __call__(self, text, *a, **kw):
        if self.armed:
            raise AssertionError(
                "모델의 토크나이저가 요청 경로에서 불렸다 — 이게 프로덕션에서 500 을 낸 그 호출이다")
        return {"input_ids": list(range(len(text)))}

    def __deepcopy__(self, memo):
        return self.twin


class _CountingTokenizer:
    """검사용 사본 — 호출을 세고, 텍스트 길이를 토큰 수로 쓴다."""

    def __init__(self, model_max_length: int = 8192):
        self.calls, self.model_max_length = 0, model_max_length

    def __call__(self, text, *a, **kw):
        self.calls += 1
        return {"input_ids": list(range(len(text)))}


class _FakeModel:
    def __init__(self, tokenizer, max_seq_length: int = 8192):
        self.tokenizer, self.max_seq_length = tokenizer, max_seq_length

    def get_sentence_embedding_dimension(self):
        return 1024

    def encode(self, texts, **kw):
        # 프로덕션은 numpy 배열을 돌려주고 핸들러가 `.tolist()` 를 부른다 — 가짜도 그 모양이어야
        # 핸들러의 실제 경로를 지난다.
        class _Vec(list):
            def tolist(self):
                return list(self)

        return [_Vec([0.1] * 1024) for _ in texts]


@pytest.fixture
def sidecar(monkeypatch):
    """모델을 내려받지 않고 사이드카를 적재한다 — 가짜 `sentence_transformers` 를 꽂는다."""

    def _load(tokenizer_factory=None, max_seq_length: int = 8192):
        twin = _CountingTokenizer(max_seq_length)
        tok = tokenizer_factory(twin) if tokenizer_factory else _RaisingTokenizer(twin)
        fake = type(sys)("sentence_transformers")
        fake.SentenceTransformer = lambda *a, **kw: _FakeModel(tok, max_seq_length)
        monkeypatch.setitem(sys.modules, "sentence_transformers", fake)
        sys.modules.pop("embed_service.app", None)
        mod = importlib.import_module("embed_service.app")
        asyncio.run(mod._load())
        tok.armed = True                 # 적재 끝 — 여기서부터 모델의 토크나이저는 금지다
        return mod, twin, tok

    return _load


# ── 방향 1: 루프가 모델의 토크나이저를 만지지 않는다 ─────────────────────────


def test_the_guard_uses_its_copy_and_never_the_models_tokenizer(sidecar):
    mod, twin, _ = sidecar()
    asyncio.run(mod.embed(mod.EmbedRequest(texts=["짧은 입력"])))
    assert twin.calls >= 1, "사본이 길이검사에 쓰여야 한다"


def test_no_event_loop_path_calls_the_models_tokenizer():
    """소스에서 `model.tokenizer(...)` **호출 노드**를 찾는다.

    이 검사가 못 보는 것: 별칭(`tok = model.tokenizer`), 헬퍼·다른 모듈 경유, `getattr`.
    발생했던 **모양**을 잡는 그물이지 부류 전체를 잡는 회귀 검사이 아니다 — SPEC §5 가 그렇게 적었고,
    수용 기준도 딱 거기까지다.
    """
    tree = ast.parse(APP_SRC.read_text(encoding="utf-8"))
    handler = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.AsyncFunctionDef) and n.name == "embed")
    offenders = [
        node.lineno for node in ast.walk(handler)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "tokenizer"
    ]
    assert offenders == [], f"핸들러가 모델의 토크나이저를 부른다 (line {offenders})"


def test_the_handler_is_a_coroutine():
    """동기 `def` 가 되면 FastAPI 가 스레드풀에서 돌리고, 사본이 다시 공유된다 — 키워드 하나다."""
    mod = importlib.import_module("embed_service.app")
    assert inspect.iscoroutinefunction(mod.embed)


# ── 방향 2: 워커 스레드가 사본을 만지지 않는다 ───────────────────────────────


def test_calling_the_guard_off_its_thread_fails_loudly(sidecar):
    mod, _, _ = sidecar()
    result: dict = {}

    def _from_another_thread():
        try:
            asyncio.run(mod.embed(mod.EmbedRequest(texts=["짧은 입력"])))
            result["raised"] = None
        except BaseException as e:              # noqa: BLE001 — 무엇이 났는지가 시험의 대상이다
            result["raised"] = type(e).__name__

    t = threading.Thread(target=_from_another_thread)
    t.start()
    t.join()
    assert result["raised"] == "GuardTokenizerMisuse", (
        "다른 스레드에서 부르면 조용히 경합하는 대신 즉시 죽어야 한다")


# ── 적재 시점의 계약 ─────────────────────────────────────────────────────────


def test_a_parity_mismatch_leaves_the_service_not_ready(sidecar):
    """한계만 같고 **세는 법**이 다르면 413 계약이 조용히 바뀐다 — 그건 뜨면 안 되는 상태다."""

    class _DifferentCount(_CountingTokenizer):
        def __call__(self, text, *a, **kw):
            self.calls += 1
            return {"input_ids": list(range(len(text) + 1))}   # 하나 더 센다

    mod, _, _ = sidecar(tokenizer_factory=lambda _twin: _RaisingTokenizer(_DifferentCount()))
    health = asyncio.run(mod.health())
    assert health["ready"] is False
    assert "parity" in (health["error"] or "")


def test_an_unmakeable_copy_leaves_the_service_not_ready_and_embed_503(sidecar):
    class _Uncopyable(_RaisingTokenizer):
        def __deepcopy__(self, memo):
            raise RuntimeError("cannot copy")

    mod, _, _ = sidecar(tokenizer_factory=lambda twin: _Uncopyable(twin))
    health = asyncio.run(mod.health())
    assert health["ready"] is False and health["guard_tokenizer"] is False
    with pytest.raises(HTTPException) as e:
        asyncio.run(mod.embed(mod.EmbedRequest(texts=["짧은 입력"])))
    assert e.value.status_code == 503


def test_over_length_input_still_gets_413(sidecar):
    """계약은 그대로다. **개수를 세는 부분**은 여기서 못 잰다(가짜 토크나이저) — 실서비스 검사로 뺀다."""
    mod, _, _ = sidecar(max_seq_length=10)
    with pytest.raises(HTTPException) as e:
        asyncio.run(mod.embed(mod.EmbedRequest(texts=["이 입력은 열 토큰을 넘는다"])))
    assert e.value.status_code == 413


def test_the_failure_counter_starts_at_zero_and_counts_embed_failures(sidecar):
    mod, _, _ = sidecar()
    assert asyncio.run(mod.health())["embed_errors"] == 0

    def _boom(texts, **kw):
        raise RuntimeError("Already borrowed")

    mod._state["model"].encode = _boom
    with pytest.raises(RuntimeError):
        asyncio.run(mod.embed(mod.EmbedRequest(texts=["짧은 입력"])))
    assert asyncio.run(mod.health())["embed_errors"] == 1, (
        "이 서비스가 실패한 적이 있는가 — 그 질문에 아무도 답할 수 없었던 것이 이 결함이 "
        "후속 측정으로만 발견된 이유다")


def test_the_model_is_bound_in_exactly_one_place(sidecar):
    """재적재 경로가 생기면 사본이 옛 체크포인트에 남을 수 있다 — 그 경로는 여기서 걸린다."""
    tree = ast.parse(APP_SRC.read_text(encoding="utf-8"))
    binds = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
        and target.value.id == "_state"
        and getattr(getattr(target.slice, "value", None), "__class__", None) is str.__class__
    ] + [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Tuple)
        and any(isinstance(el, ast.Subscript) and getattr(el.slice, "value", None) == "model"
                for el in node.targets[0].elts)
    ]
    assert len(binds) == 1, f"`_state['model']` 이 여러 곳에서 묶인다 (lines {binds})"
