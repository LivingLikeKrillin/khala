"""예시 엔티티 목록은 **읽히지 않는다** — 질의 검출에도, 기동에도, 적재에도.

⛔ **왜 (2026-10-01).** `nexus/entities.yaml` 은 전자상거래 예시 다섯(`order-service` 등)이었는데 모든
테넌트에 쓰였다. 질의 검출은 이름과 별칭을 **부분 문자열**로 찾아서(`order` · `payment`) 무관한 코퍼스의
질의를 엔티티로 잡았다 — 로봇 사건 질의 32건이 전부 `order-service` 로 잡혔다. 앱은 기동할 때, 적재는
돌 때마다 그 다섯을 테넌트에 심었다(출처 없음). 그래프 조회의 튜플 결함을 고치는 순간 그 이름이 진단
프롬프트의 「중심 엔티티」로 들어갈 참이었다.

목록은 이제 `entities.example.yaml` 로만 남는다. 쓰려면 `entities.yaml` 로 복사한다 — 그 파일은 리포에
올리지 않는다(배포의 서비스 이름이 들어갈 자리다). **목록이 없는 것이 기본이고, 경고가 아니다.**
"""

from __future__ import annotations

from pathlib import Path

import pytest
import structlog

from nexus.index import graph_extractor as gx

_NEXUS = Path(__file__).resolve().parents[1]
_EXAMPLE = _NEXUS / "entities.example.yaml"
_SAMPLE = {"payment-service", "notification-service", "order-service",
           "payment.completed", "order.created"}


def _warnings(caught) -> list[dict]:
    return [e for e in caught if e.get("log_level") in ("warning", "error")]


def test_the_sample_lives_only_in_the_example_file():
    """예시는 남는다(복사해서 쓸 수 있게). 기본 경로는 리포가 무시한다 — 다시 올라오지 않게."""
    assert {e["name"] for e in gx._load_gazetteer(str(_EXAMPLE))} == _SAMPLE
    ignored = (_NEXUS / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "/entities.yaml" in ignored, "기본 경로의 목록이 다시 리포에 올라올 수 있다"


def test_no_gazetteer_is_a_normal_state_not_a_warning(monkeypatch, tmp_path):
    """질의마다 부르는 함수다 — 없을 때 경고를 내면 요청마다 한 줄씩 쌓인다."""
    monkeypatch.chdir(tmp_path)
    with structlog.testing.capture_logs() as caught:
        assert gx._load_gazetteer() == []
    assert _warnings(caught) == []


def test_a_query_that_says_order_detects_nothing_by_default(monkeypatch, tmp_path):
    """⛔ 예시 목록이면 같은 문장이 `order-service` 로 잡힌다 — 그것이 고친 결함이다."""
    text = "in order to recover the lost payload"
    with_sample = gx.find_entities_in_text(
        text, gx._build_entity_patterns(gx._load_gazetteer(str(_EXAMPLE))))
    assert [m.name for m in with_sample] == ["order-service"], "전제가 깨졌다 — 결함이 재현 안 된다"

    monkeypatch.chdir(tmp_path)
    by_default = gx.find_entities_in_text(text, gx._build_entity_patterns(gx._load_gazetteer()))
    assert by_default == []


@pytest.mark.asyncio
async def test_the_startup_registers_nothing_and_says_so_once(monkeypatch, tmp_path):
    """기동이 테넌트에 무엇을 심는지가 바뀌었다 — 그 사실은 기동 로그 한 줄로 보인다."""
    from nexus import api

    calls: list = []

    async def record(*a, **k):
        calls.append(a)
        return "ent_x"

    monkeypatch.setattr(gx, "ensure_entity_exists", record)
    monkeypatch.chdir(tmp_path)
    with structlog.testing.capture_logs() as caught:
        await api._bootstrap_gazetteer()
    assert calls == []
    assert [e["event"] for e in caught] == ["gazetteer_absent"]
    assert _warnings(caught) == []


@pytest.mark.asyncio
async def test_ingest_extracts_no_graph_without_a_gazetteer_and_does_not_warn(monkeypatch, tmp_path):
    """적재는 주기적으로 돈다 — 목록이 없을 때마다 경고를 내면 그것이 소음이 된다."""
    calls: list = []

    async def record(*a, **k):
        calls.append(a)
        return "ent_x"

    monkeypatch.setattr(gx, "ensure_entity_exists", record)
    with structlog.testing.capture_logs() as caught:
        made = await gx.extract_and_save_graph(
            [("chunk_1", "payment-service 가 notification-service 를 호출한다")],
            tenant="t", config_path=str(_NEXUS / "config.yaml"),
            gazetteer_path=str(tmp_path / "entities.yaml"))
    assert made == 0
    assert calls == [], "목록이 없는데 엔티티를 심었다"
    assert _warnings(caught) == []
