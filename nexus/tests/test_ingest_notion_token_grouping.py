"""`nexus ingest-notion` 은 루트마다 그 루트의 토큰으로 걸어야 한다.

migration 009 가 이 실패를 이름까지 붙여 예고했다:

> 위험한 것은 기능 부족이 아니라 **조용한 오독**이다: 토큰을 바꿔치면 이전 워크스페이스의 루트가
> 빈 걸음으로 보이고, `--reconcile` 이 그 문서들을 사라진 것으로 판정한다.

컬럼은 그걸 막으려고 만들어졌고 HTTP 표면은 `roots_store.group_by_token()` 으로 쓰고 있었는데
(`sources/api.py:126,294`), CLI 만 `--token-env` 하나를 모든 루트에 적용했다. 2026-08-11 에
그 경로로 정책 트리 전체가 `ObjectNotFound` 로 돌아왔고, 나는 그것을 "원본이 사라졌다" 로 읽었다.
"""

from __future__ import annotations


from nexus.a2a.server import _default_external_ingest_fn
from nexus.sources import roots_store

# `nexus.a2a` 를 여기서 명시적으로 import 하는 이유: `cli.ingest_notion` 이 그것을 끌어오므로 이
# 파일은 **a2a 를 건드리는 시험**이고, conftest 의 자동 skip 은 파일 자체의 import 문을 본다.
# 간접 의존을 숨기면 a2a extra 가 없는 CI 잡에서 ModuleNotFoundError 로 터진다(실제로 터졌다).
# 숨기는 대신 아래 단언에서 실제로 쓴다.


def test_group_by_token_splits_the_walk():
    got = roots_store.group_by_token([
        {"root_id": "a", "token_env": "NOTION_TOKEN"},
        {"root_id": "b", "token_env": "NOTION_TOKEN_OTHER"},
        {"root_id": "c", "token_env": "NOTION_TOKEN"},
    ])
    assert got == {"NOTION_TOKEN": ["a", "c"], "NOTION_TOKEN_OTHER": ["b"]}


def test_a_root_without_a_token_env_falls_back_to_the_default():
    got = roots_store.group_by_token([{"root_id": "a"}, {"root_id": "b", "token_env": None}])
    assert got == {roots_store.DEFAULT_TOKEN_ENV: ["a", "b"]}


def test_cli_walks_once_per_token_env(monkeypatch):
    """CLI 가 토큰 그룹마다 한 번씩 걷는가 — 한 번에 몰아 걷지 않는가."""
    from nexus import cli

    registered = [
        {"root_id": "a", "token_env": "NOTION_TOKEN"},
        {"root_id": "b", "token_env": "NOTION_TOKEN_OTHER"},
    ]
    monkeypatch.setattr("nexus.sources.roots_store.list_roots",
                        _async_return(registered))

    built: list[tuple[str, tuple[str, ...]]] = []

    class _Source:
        def __init__(self, token_env, roots, tenant):
            built.append((token_env, tuple(roots)))

    monkeypatch.setattr("nexus.ingest.sources.notion.NotionSource", _Source)

    walked: list[tuple[str, ...]] = []

    async def _import(source, tenant, ingest_fn, **kw):
        assert ingest_fn is _default_external_ingest_fn, "적재 함수는 그대로 넘어가야 한다"
        walked.append(built[-1][1])
        return _Report()

    monkeypatch.setattr("nexus.ingest.sources.notion_importer.import_notion", _import)

    cli.ingest_notion(tenant="default", roots="", token_env="NOTION_TOKEN",
                      since="", reconcile=False, dry_run=False, force=False,
                      threshold=0.5)

    assert sorted(built) == [("NOTION_TOKEN", ("a",)), ("NOTION_TOKEN_OTHER", ("b",))], (
        "루트를 토큰별로 갈라 걸어야 한다 — 한 토큰으로 몰아 걸으면 못 보는 쪽이 빈 걸음이 된다")
    assert len(walked) == 2


class _Report:
    ingested = idempotent = empty = skipped = 0
    watermark = ""


def _async_return(value):
    async def _fn(*_a, **_k):
        return value
    return _fn
