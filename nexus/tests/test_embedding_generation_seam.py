"""임베딩 세대 seam — 어느 모델이·어느 컬럼에·어느 백엔드로 (SPEC-nexus-embedding-cutover-seam §4.1, §4.2).

컷오버가 "설정 한 줄" 이라고 적혀 있었지만, 질의 경로 여섯 곳이 전부 `EmbeddingService()` 기본값을
만들고 있어서 컬럼만 바뀌면 **768 차원 질의 벡터가 vector(1024) 컬럼에 부딪혔다**. 여기서 지키는
것은 그 seam 의 네 갈래다:

- 세대는 **한 곳**(팩토리)에서 결정된다 — 여섯 곳이 각자 기본값을 만들면 설정은 장식이다
- 배포는 **env 로** 움직인다 — 이 배포는 `config.yaml` 을 git 워킹트리에서 읽는다(§1.9)
- **셋 중 하나만 움직이면 구성 자체가 거부된다** — 모델·컬럼·백엔드는 함께만 유효하다
- 차원은 모델의 사실이지만 **재기 전까지는 가정**이다 — 백엔드가 돌려준 벡터를 실제로 센다
"""

from __future__ import annotations

import httpx
import pytest

from nexus.index.vector_index import UnknownVectorColumn, configured_column
from nexus.providers.embedding import (
    MODEL_BACKENDS,
    MODEL_DIMENSIONS,
    MODEL_PREFIXES,
    EmbeddingService,
    InconsistentEmbeddingGeneration,
    WrongVectorDimensions,
    embedding_service_from_config,
)

KURE_CFG = {"embedding": {"model": "KURE-v1", "backend": "sidecar"},
            "search": {"embedding_column": "embedding_1024"}}


@pytest.fixture(autouse=True)
def _no_ambient_env(monkeypatch):
    """세대 env 는 배포의 것이다 — 테스트가 호스트 환경을 물려받으면 아무것도 증명하지 못한다."""
    for var in ("NEXUS_EMBEDDING_MODEL", "NEXUS_EMBEDDING_COLUMN",
                "NEXUS_EMBEDDING_BACKEND", "EMBEDDING_BACKEND"):
        monkeypatch.delenv(var, raising=False)


# ── 레지스트리 ───────────────────────────────────────────────────────────────


def test_every_model_declares_its_dimension_and_its_serving():
    """모델을 추가하면서 차원·서빙을 빠뜨리면 **테스트**가 실패해야 한다. 배포가 아니라."""
    assert set(MODEL_DIMENSIONS) == set(MODEL_PREFIXES)
    assert set(MODEL_BACKENDS) == set(MODEL_PREFIXES)
    assert MODEL_DIMENSIONS["nomic-embed-text"] == 768
    assert MODEL_DIMENSIONS["KURE-v1"] == 1024
    assert set(MODEL_BACKENDS.values()) <= {"ollama", "sidecar"}


# ── 팩토리: 설정과 env ───────────────────────────────────────────────────────


def test_an_untouched_deployment_gets_todays_behaviour():
    svc = embedding_service_from_config({})
    assert (svc.model, svc.backend, svc.dimensions) == ("nomic-embed-text", "ollama", 768)


def test_the_config_decides_when_it_says_something():
    svc = embedding_service_from_config(KURE_CFG)
    assert (svc.model, svc.backend, svc.dimensions) == ("KURE-v1", "sidecar", 1024)


def test_the_dimension_comes_from_the_model_not_from_config():
    """`embedding.dimensions` 는 모델과 **합의해야만 하는 숫자**라 별도로 적힐 이유가 없다."""
    svc = embedding_service_from_config({"embedding": {"model": "KURE-v1", "backend": "sidecar"},
                                         "search": {"embedding_column": "embedding_1024"}})
    assert svc.dimensions == MODEL_DIMENSIONS["KURE-v1"]


def test_a_surviving_dimensions_key_that_disagrees_is_refused():
    """지우기로 한 키가 남아 있을 수 있다. 조용히 무시하면 그게 세 번째 진실이 된다."""
    cfg = {"embedding": {"model": "KURE-v1", "backend": "sidecar", "dimensions": 768},
           "search": {"embedding_column": "embedding_1024"}}
    with pytest.raises(InconsistentEmbeddingGeneration) as e:
        embedding_service_from_config(cfg)
    assert "768" in str(e.value) and "1024" in str(e.value)


def test_a_surviving_dimensions_key_that_agrees_is_tolerated():
    cfg = {"embedding": {"model": "nomic-embed-text", "dimensions": 768}}
    assert embedding_service_from_config(cfg).dimensions == 768


@pytest.mark.parametrize("var,value,attr,expected", [
    ("NEXUS_EMBEDDING_MODEL", "KURE-v1", "model", "KURE-v1"),
    ("NEXUS_EMBEDDING_BACKEND", "sidecar", "backend", "sidecar"),
])
def test_env_beats_config(monkeypatch, var, value, attr, expected):
    """배포는 env 로 움직인다 — 리포의 파일을 고쳐서 flip 하면 `git checkout` 이 프로덕션을 되돌린다."""
    monkeypatch.setenv(var, value)
    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", "embedding_1024")
    monkeypatch.setenv("NEXUS_EMBEDDING_MODEL", "KURE-v1")
    monkeypatch.setenv("NEXUS_EMBEDDING_BACKEND", "sidecar")
    svc = embedding_service_from_config({"embedding": {"model": "nomic-embed-text",
                                                       "backend": "ollama"}})
    assert getattr(svc, attr) == expected


def test_the_legacy_unprefixed_backend_var_still_works_and_loses_to_the_prefixed_one(monkeypatch):
    """`EMBEDDING_BACKEND` 는 이미 쓰이고 있다. 조용히 무시하면 배포가 무시당한 줄 모른다."""
    monkeypatch.setenv("EMBEDDING_BACKEND", "sidecar")
    monkeypatch.setenv("NEXUS_EMBEDDING_MODEL", "KURE-v1")
    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", "embedding_1024")
    assert embedding_service_from_config({}).backend == "sidecar"

    monkeypatch.setenv("NEXUS_EMBEDDING_BACKEND", "sidecar")
    monkeypatch.setenv("EMBEDDING_BACKEND", "ollama")
    assert embedding_service_from_config({}).backend == "sidecar"


# ── 세대 정합성: 셋은 함께만 유효하다 ────────────────────────────────────────


@pytest.mark.parametrize("model,column,backend", [
    ("nomic-embed-text", "embedding_1024", "ollama"),   # 컬럼만 움직였다 — 원래의 그 결함
    ("KURE-v1", "embedding", "sidecar"),                # 모델·백엔드만 움직였다
    ("KURE-v1", "embedding_1024", "ollama"),            # 백엔드를 안 움직였다
])
def test_moving_fewer_than_all_three_is_refused_and_all_three_are_named(model, column, backend):
    cfg = {"embedding": {"model": model, "backend": backend},
           "search": {"embedding_column": column}}
    with pytest.raises(InconsistentEmbeddingGeneration) as e:
        embedding_service_from_config(cfg)
    message = str(e.value)
    assert model in message and column in message and backend in message


@pytest.mark.parametrize("cfg", [
    {},
    KURE_CFG,
])
def test_the_two_coherent_generations_pass(cfg):
    assert embedding_service_from_config(cfg) is not None


def test_a_column_outside_the_whitelist_is_refused_from_config_or_env(monkeypatch):
    with pytest.raises(UnknownVectorColumn):
        embedding_service_from_config({"search": {"embedding_column": "embeding_1024"}})

    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", "embeddings")
    with pytest.raises(UnknownVectorColumn):
        embedding_service_from_config({})


# ── 어느 컬럼을 읽는가: 검색 경로와 팩토리가 같은 답을 봐야 한다 ─────────────


def test_the_read_path_and_the_factory_resolve_the_same_column(monkeypatch):
    """둘이 갈라지면 팩토리는 KURE 를 만들고 검색은 옛 컬럼을 읽는다 — 조용한 절반 컷오버."""
    assert configured_column({}) == "embedding"
    assert configured_column({"search": {"embedding_column": "embedding_1024"}}) == "embedding_1024"

    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", "embedding_1024")
    assert configured_column({}) == "embedding_1024"
    assert configured_column({"search": {"embedding_column": "embedding"}}) == "embedding_1024"


# ── 여섯 곳이 각자 만들지 않는다 ─────────────────────────────────────────────


def test_no_production_path_constructs_the_service_with_defaults():
    """이 결함의 실제 모양이다 — 설정은 컬럼을 옮겼는데 여섯 곳이 각자 기본값을 만들고 있었다.

    허용되는 예외는 재임베딩 CLI 하나뿐이다: 마이그레이션 도구는 **설정을 따라가면 안 된다**(§4.3).
    컷오버 시점의 설정은 아직 옛 컬럼을 가리키므로, 설정을 따라가는 재임베딩은 보존해야 할 컬럼을
    겨눈다.
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "nexus"
    offenders = []
    for path in root.rglob("*.py"):
        # 문자열 검색이 아니라 **호출 노드**를 본다 — 주석·독스트링의 언급은 결함이 아니고,
        # 그걸 못 가리면 이 회귀 검사은 문서를 고칠 때마다 울린다.
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "EmbeddingService"
                    and not node.args and not node.keywords):
                offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    assert offenders == [], (
        "세대는 embedding_service_from_config() 한 곳에서만 결정돼야 한다. "
        f"기본값으로 만드는 곳: {offenders}")


# ── 차원은 재기 전까지 가정이다 ──────────────────────────────────────────────


def _sidecar_returning(monkeypatch, vector: list[float]) -> None:
    """사이드카가 그 길이의 벡터를 돌려주는 세상. 기존 스위트와 같은 방식으로 `httpx` 를 갈아끼운다."""

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"embeddings": [vector], "model": "KURE-v1", "dim": len(vector)}

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


@pytest.mark.asyncio
async def test_a_vector_of_the_wrong_length_is_refused_at_the_boundary(monkeypatch):
    """Matryoshka 절단·잘못 띄운 사이드카·바뀐 헤드는 전부 여기로 온다. 안 재면 pgvector 가 낸다."""
    _sidecar_returning(monkeypatch, [0.1] * 768)
    svc = EmbeddingService(model="KURE-v1", backend="sidecar", dimensions=1024)
    with pytest.raises(WrongVectorDimensions) as e:
        await svc.embed_query("결제 서비스")
    assert "1024" in str(e.value) and "768" in str(e.value)


@pytest.mark.asyncio
async def test_a_vector_of_the_right_length_passes(monkeypatch):
    """음성 대조군 — 검사가 무엇이든 거부하기만 하면 그것도 결함이다."""
    _sidecar_returning(monkeypatch, [0.1] * 1024)
    svc = EmbeddingService(model="KURE-v1", backend="sidecar", dimensions=1024)
    assert len(await svc.embed_query("결제 서비스")) == 1024
