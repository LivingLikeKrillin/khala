"""주기 재적재 — **돌았다는 사실**이 남는가, 그리고 잡이 엉뚱한 코퍼스를 못 먹는가.

⛔ **이 단위가 푸는 문제 하나.** 기존 적재 신호는 전부 *변경*을 기록한다
(`documents.updated_at` · `doc_reingest_events` · `doc-age`). 코퍼스가 안 바뀐 주에는 셋 다
아무것도 안 남기므로 **잡이 죽은 것**과 **바뀐 게 없는 것**이 같은 모양이다. 실측
2026-09-18: `picasso` 36건은 `origin_updated_at` 이 전부 NULL 이라 `doc-age` 도 못 가른다
(파일 적재는 frontmatter 가 시각을 선언할 때만 채운다). 그래서 실행 한 건당 한 행이다.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from nexus.health import persistence
from nexus.ingest import runs_store

_COMPOSE = pathlib.Path(__file__).resolve().parents[1] / "docker-compose.yml"


def _compose() -> dict:
    return yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))


def _reingest() -> dict:
    return _compose()["services"]["nexus-reingest"]


class _Result:
    found_files = 36
    total_files = 0
    unchanged_files = 36
    indexed = 0
    bm25_indexed = 0
    vector_indexed = 0
    quarantined = 0
    refused_vendor = 0
    failed = 0


# ── 남는 수 ────────────────────────────────────────────────────────────────

def test_a_run_that_changed_nothing_still_says_what_it_saw():
    """⛔ 이 단위의 전부. 0 만 남기면 "안 돌았다" 와 구분이 안 된다."""
    c = runs_store.summarize(_Result())
    assert c["found"] == 36 and c["unchanged"] == 36 and c["changed"] == 0


def test_found_and_changed_and_unchanged_are_three_numbers():
    """⛔ 하나로 덮으면 *"못 봤다"* 와 *"안 바뀌었다"* 가 같은 수가 된다 — 2026-08-28 에
    그 줄 하나 때문에 없는 결함을 보고했다. `unchanged` 가 갑자기 0 이면 원본이 안 보이는
    것이고, `found` 가 0 이면 마운트가 빈 것이다. 처방이 다르다."""
    assert {"found", "changed", "unchanged"} <= set(runs_store.summarize(_Result()))


def test_the_refusal_count_is_not_folded_into_failures():
    assert "refused_vendor" in runs_store.summarize(_Result())


# ── 기록이 적재를 죽이지 않는가 ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_dead_recorder_does_not_kill_the_ingest(monkeypatch):
    """⚠ 기록하려고 적재를 죽이면 기록이 적재를 망가뜨린 것이다."""
    async def boom(*a, **k):
        raise RuntimeError("표가 없다")

    monkeypatch.setattr(runs_store.db, "execute", boom)
    assert await runs_store.start("picasso", "/ingest-src") is None
    await runs_store.finish("some-run-id", status="succeeded")     # 조용히 넘어간다


@pytest.mark.asyncio
async def test_finishing_a_run_that_never_started_is_a_no_op(monkeypatch):
    """`start` 가 None 을 돌려준 뒤에도 호출자는 평소대로 `finish` 를 부른다."""
    calls = []

    async def spy(*a, **k):
        calls.append(a)

    monkeypatch.setattr(runs_store.db, "execute", spy)
    await runs_store.finish(None, status="succeeded")
    assert calls == [], "없는 실행을 닫으려 들면 안 된다"


# ── 죽은 잡이 보이는가 ─────────────────────────────────────────────────────

def test_the_run_record_is_on_the_health_list():
    """⛔ 기록만 남기고 아무도 안 보면 2026-09-02 의 `search_log` 34시간 침묵과 같다 —
    그때도 경고는 찍혀 있었고, 읽는 곳이 없었다."""
    tables = {t for t, _c, _w, _d in persistence.SINKS}
    assert "ingest_runs" in tables


def test_the_health_row_says_what_makes_it_write():
    """경과 시간만 내면 읽는 사람이 죽음과 조용함을 오독한다 — 이 모듈이 그렇게 데였다."""
    driven = next(d for t, _c, _w, d in persistence.SINKS if t == "ingest_runs")
    assert driven.strip(), "무엇이 쓰게 하는가가 비어 있다"


# ── 잡이 엉뚱한 코퍼스를 먹지 않는가 ───────────────────────────────────────

def test_the_job_refuses_to_start_without_a_tenant_and_a_source():
    """⛔ **가장 위험한 실패.** `INGEST_SRC_PATH` 가 비면 마운트가 `./docs`(=khala 자기
    문서)로 폴백한다. 테넌트에 기본값이 있으면 이 잡은 남의 코퍼스에 우리 문서를 **주기적으로**
    밀어 넣고, 아무도 안 본다."""
    entry = "\n".join(_reingest()["entrypoint"])
    assert "REINGEST_TENANT" in entry and "REINGEST_SRC" in entry
    assert "exit 2" in entry, "거부가 종료코드로 나와야 한다"


def test_neither_the_tenant_nor_the_source_has_a_default():
    env = _reingest()["environment"]
    assert env["REINGEST_TENANT"] == "${REINGEST_TENANT:-}"
    assert env["REINGEST_SRC"] == "${INGEST_SRC_PATH:-}"


def test_the_job_does_not_depend_on_the_profiled_sidecar():
    """⚠ **일부러 안 건다.** 사이드카는 프로파일 뒤에 있어서, `depends_on` 을 걸면 그
    프로파일을 안 켠 배포가 `depends on undefined service` 로 아예 안 뜬다 — 앱 쪽에 같은
    이유가 이미 실측으로 적혀 있다. 대신 회차마다 물어본다(아래)."""
    assert "nexus-embed" not in _reingest().get("depends_on", {})


def test_the_job_asks_the_sidecar_before_it_ingests():
    """⛔ 없는 사이드카에 대고 적재하면 조각이 전부 거부되고 코퍼스는 키워드로만 찾힌다
    (2026-09-18 실측 366/366). 그때 `nexus status` 는 말해 줬지만, 애초에 안 돌리는 게 낫다."""
    entry = "\n".join(_reingest()["entrypoint"])
    assert "NEXUS_EMBEDDING_BACKEND" in entry and "EMBED_URL" in entry
    assert "건너뜀" in entry, "건너뛴 회차가 로그에 보여야 한다"


def test_the_job_is_behind_a_profile():
    """켜지 않은 배포에서 이 잡이 저절로 돌면 안 된다."""
    assert "reingest" in _reingest().get("profiles", [])


def test_the_job_and_the_app_read_one_environment():
    """⛔ 세대 셋의 기본값이 두 자리에 따로 적히면, 한쪽만 고쳐도 아무것도 안 깨지고 그
    다음 적재가 **검색되지 않는 컬럼**에 들어간다 (2026-08-10 실측). 그래서 앵커 하나다."""
    raw = _COMPOSE.read_text(encoding="utf-8")
    assert "x-nexus-env: &nexus-env" in raw
    assert raw.count("<<: *nexus-env") >= 2, "앱과 잡이 같은 앵커를 받아야 한다"
    for key in ("NEXUS_EMBEDDING_MODEL", "NEXUS_EMBEDDING_COLUMN", "NEXUS_EMBEDDING_BACKEND"):
        assert raw.count(f"      {key}:") == 0, f"{key} 가 서비스 블록에 사본으로 남아 있다"
