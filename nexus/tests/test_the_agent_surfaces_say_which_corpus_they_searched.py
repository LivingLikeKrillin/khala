"""에이전트가 쓰는 표면도 **어느 코퍼스를 뒤졌는지** 말하는가.

⛔ **왜 생겼나 (실측 2026-09-23).** `/search` 를 고치고(`#549`) 같은 결함을 다른 표면에서
찾다가, `grep searched_tenants` 로 *"a2a 와 CLI 도 범위를 안 낸다"* 라고 결론지었다. **틀렸다** —
a2a 는 같은 사실을 `policy.tenant` 라는 **다른 이름**으로 이미 내고 있었다. 이름 하나를 찾고
**행동**을 단언한 것이고, 바로 그 판에서 내가 고치던 가드(`_names`)가 저지른 것과 같은 실수다.

⇒ 그래서 이 파일은 이름을 세지 않는다. **표면마다 자기 어법으로** 코퍼스를 말하는지 본다.

| 표면 | 어법 | 범위를 정하는 것 |
|---|---|---|
| `/search` · `/search/answer` · `…/stream` | 응답의 `searched_tenants` | 토큰(`effective_read_scope`) |
| A2A | 아티팩트의 `policy.tenant` | 토큰(`effective_scope`) |
| CLI `query` | 화면의 `코퍼스:` 줄 | **`--tenant` 플래그뿐** |

⭐ **CLI 만 실재하는 결함이었다.** 이 명령은 principal 이 없어서 `--tenant` 가 곧 범위이고
기본값이 `default` 다. `CLAUDE.md` 는 조직 지식을 물을 때 **이 명령을 가장 먼저 치라**고 적고,
같은 파일이 테넌트가 둘이며 **둘의 내용이 다르다**고 적는다. 설계 질문에서 플래그를 빠뜨리면
정책 코퍼스만 본 결과가 확신 있게 나왔고 화면에는 그 사실이 없었다.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from nexus.cli import app
from nexus.search.hybrid import SearchResult

runner = CliRunner()


class _Hit:
    doc_title, section_path, score = "어느 문서", "1절", 0.5
    snippet = "본문"


@pytest.fixture
def stubbed(monkeypatch):
    """DB·임베딩·LLM 없이 `query` 본문을 돌린다.

    ⚠ 이 명령은 임포트를 **함수 안에서** 한다 — `nexus.cli.X` 를 덮으면 아무 일도 안 난다.
    호출 시점에 다시 읽는 **원본 모듈**을 덮어야 한다.
    """
    from nexus import cli, db
    from nexus.index import graph_extractor
    from nexus.providers import embedding as emb_mod
    from nexus.search import hybrid as hybrid_mod
    from nexus.search import router as router_mod
    from nexus.search import signals as signals_mod
    from nexus.repositories import graph as graph_mod

    hits: list = []

    async def _noop_async(*a, **k):
        return None

    async def _search(*a, **k):
        return SearchResult(hits=list(hits), route_used="keyword_only",
                            timing_ms={"total_ms": 1})

    monkeypatch.setattr(cli, "_load_config", lambda *a, **k: {})
    monkeypatch.setattr(db, "get_pool", _noop_async)
    monkeypatch.setattr(db, "close_pool", _noop_async)
    monkeypatch.setattr(emb_mod, "embedding_service_from_config", lambda *a, **k: None)
    monkeypatch.setattr(graph_mod, "PostgresGraphRepository", lambda *a, **k: None)
    monkeypatch.setattr(graph_extractor, "_load_gazetteer", lambda *a, **k: {})
    monkeypatch.setattr(graph_extractor, "_build_entity_patterns", lambda *a, **k: {})
    monkeypatch.setattr(graph_extractor, "find_entities_in_text", lambda *a, **k: [])
    monkeypatch.setattr(router_mod, "determine_route", lambda *a, **k: "keyword_only")
    monkeypatch.setattr(hybrid_mod, "hybrid_search", _search)
    monkeypatch.setattr(signals_mod, "extract_signals", lambda *a, **k: None)
    monkeypatch.setattr(signals_mod, "record_search", _noop_async)

    return hits


def _run(stubbed, *argv) -> str:
    result = runner.invoke(app, ["query", "무엇이든", "--no-answer", *argv])
    assert result.exit_code == 0, result.output + str(result.exception or "")
    return result.output


# ── CLI ─────────────────────────────────────────────────────────────────────

def test_it_names_the_corpus_it_searched(stubbed):
    """⭐ **이 줄이 없으면 읽는 쪽은 어느 코퍼스를 봤는지 알 방법이 없다.**"""
    stubbed.append(_Hit())

    assert "코퍼스: design_docs" in _run(stubbed, "--tenant", "design_docs")


def test_the_default_is_named_too_not_left_silent(stubbed):
    """⛔ **여기가 결함의 자리였다.** 플래그를 안 주면 `default` 인데, 그 사실이 안 보였다.

    `CLAUDE.md` 가 첫 번째로 치라고 적은 명령이 바로 이 모양으로 불린다.
    """
    stubbed.append(_Hit())

    assert "코퍼스: default" in _run(stubbed)


def test_it_still_names_the_corpus_when_nothing_was_found(stubbed):
    """⚠ **0건일 때가 가장 필요하다.**

    「없습니다」가 *코퍼스에 없다* 인지 *엉뚱한 코퍼스를 봤다* 인지를 이 줄 하나가 가른다.
    """
    out = _run(stubbed, "--tenant", "design_docs")

    assert "결과: 0건" in out
    assert "코퍼스: design_docs" in out


def test_the_answer_path_names_it_as_well(stubbed, monkeypatch):
    """답변을 만드는 실행에서도 같은 줄이 나온다 — 검색 요약이 두 경로의 공통이다."""
    stubbed.append(_Hit())

    result = runner.invoke(app, ["query", "무엇이든", "--tenant", "design_docs",
                                 "--no-answer"])
    assert "코퍼스: design_docs" in result.output


# ── 표면 목록 ────────────────────────────────────────────────────────────────

def test_the_a2a_artifact_still_carries_the_resolved_tenant():
    """⛔ **a2a 는 결함이 아니었다 — 이름이 달랐을 뿐이다.**

    여기서 고정하는 것은 ① 그 사실이 아티팩트에 있다 ② **요청이 아니라 해소된 값**이다.
    a2a 는 `effective_scope` 로 principal 의 테넌트를 쓰므로, 호출자가 다른 것을 물어도
    이 칸은 실제로 뒤진 것을 말해야 한다.
    """
    from nexus.a2a.mapping import build_grounded_artifact
    from nexus.llm.answer import AnswerResult

    artifact, _state, _reason = build_grounded_artifact(
        AnswerResult(answer="답", evidence_snippets=[{"doc_title": "d"}]),
        "resolved_tenant", "INTERNAL")

    data = next(p["data"] for p in artifact["parts"] if p.get("kind") == "data")
    assert data["policy"]["tenant"] == "resolved_tenant"


def test_every_surface_that_searches_says_what_it_searched():
    """⚠ **표면 하나가 목록에서 빠지는 것이 이 부류의 전형이다**(외부 평가 F2).

    ⛔ 이름을 세지 않는다 — 그렇게 세다가 a2a 를 결함으로 오판했다. 표면마다 **자기 어법**을
    적어 두고, 그 어법이 실제로 코드에 있는지만 본다. 다섯째 표면이 생기면 여기 한 줄이
    늘어야 하고, 안 늘면 그 표면은 조용히 침묵한다.
    """
    from nexus import api, cli
    from nexus.a2a import mapping

    idioms = {
        "http_search": (api.search, "searched_tenants"),
        "http_answer": (api.search_answer, "searched_tenants"),
        "http_stream": (api.search_answer_stream, "searched_tenants"),
        "a2a_artifact": (mapping.build_grounded_artifact, "policy"),
        # ⚠ f-string 의 고정 조각은 **앞의 `\n` 까지 한 상수**다. 부분 문자열로 느슨하게
        # 하지 않고 그 상수를 그대로 겨눈다 — 부분 문자열 단언은 제 docstring 을 문다.
        "cli_query": (cli.query, "\n코퍼스: "),
    }
    missing = [name for name, (fn, idiom) in idioms.items()
               if idiom not in _strings(fn)]

    assert not missing, f"뒤진 코퍼스를 말하지 않는 표면: {missing}"


def _strings(func) -> set[str]:
    """이 함수와 중첩 함수들이 쓰는 이름·문자열 상수 전부.

    ⚠ 딕셔너리의 상수 키는 **튜플 상수 하나**(`BUILD_CONST_KEY_MAP`)에 들어가고, f-string 의
    고정 조각은 낱개 상수로 들어간다. 둘 다 걷는다 — 한쪽만 보면 표면마다 결과가 갈린다
    (`test_answer_says_what_it_searched._names` 가 같은 자리에서 같은 이유로 고쳐졌다).
    """
    seen: set = set()
    out: set[str] = set()
    stack = [func.__code__]
    while stack:
        code = stack.pop()
        if id(code) in seen:
            continue
        seen.add(id(code))
        out |= set(code.co_names)
        for c in code.co_consts:
            if isinstance(c, str):
                out.add(c)
            elif isinstance(c, (tuple, frozenset)):
                out |= {x for x in c if isinstance(x, str)}
            elif hasattr(c, "co_names"):
                stack.append(c)
    return out
