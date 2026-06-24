# Notion Importer (S4) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Notion 페이지를 CSF로 변환해 S3 타입-인지 intake로 적재하는 importer + CLI. Path B(provenance+doc_type+승격가능).

**Architecture:** importer는 `ingest_fn` 주입받는 순수 오케스트레이터(a2a 무의존). CLI(합성 루트)가 `NotionSource`(live client)와 `_default_external_ingest_fn`(a2a)을 와이어. 리팩터 없음 — 의존성 역전으로 레이어링 해결. 라이브는 NOTION_TOKEN+notion-client(lazy, optional); 단위는 가짜 client/ingest로 DB·토큰 불필요.

**Tech Stack:** Python, Typer, pytest. 기존 `NotionSource`/`run_ingest`/S3 intake 재사용.

**Spec:** `docs/superpowers/specs/2026-06-25-notion-importer-s4-design.md`

---

## File Structure

| 파일 | 변경 |
|---|---|
| `nexus/nexus/ingest/sources/notion_importer.py` (생성) | `build_csf` + `ImportReport` + `import_notion`(주입 ingest_fn) |
| `nexus/tests/test_notion_importer.py` (생성) | build_csf 정합 + import_notion 오케스트레이션(가짜 source+ingest) |
| `nexus/nexus/ingest/sources/notion.py` (수정) | `live_ids`/`page_ref`/`_collect`/`_db_rows` 구현(NotImplementedError 대체) |
| `nexus/tests/test_notion_source.py` (수정) | live_ids/page_ref 테스트(가짜 client 확장) |
| `nexus/nexus/cli.py` (수정) | `ingest-notion` 명령 + 친절한 에러 |
| `nexus/pyproject.toml` (수정) | `notion-client` optional 의존 |

---

## Chunk 1: importer 순수 로직 (build_csf + import_notion)

a2a/DB 무의존. 주입 ingest_fn으로 오케스트레이션만.

### Task 1: build_csf

**Files:**
- Create: `nexus/nexus/ingest/sources/notion_importer.py`
- Test: `nexus/tests/test_notion_importer.py`

- [ ] **Step 1: 실패 테스트**

`nexus/tests/test_notion_importer.py`:

```python
from __future__ import annotations

import hashlib

import pytest

from nexus.ingest.sources.base import ConvertedDoc
from nexus.ingest.sources.notion_importer import ImportReport, build_csf, import_notion


def _conv(body="# 제목\n\n본문", title="결제 기획", url="https://notion.so/p1"):
    return ConvertedDoc(
        page_id="p1", markdown=body,
        frontmatter={"title": title, "origin_url": url}, image_count=0,
    )


def test_build_csf_produces_deterministic_id_and_hash():
    csf = build_csf(_conv(), "p1")
    assert csf["id"] == "ext-notion-p1"
    assert csf["kind"] == "NOTE"
    assert csf["title"] == "결제 기획"
    prov = csf["provenance"]
    assert prov["source_tool"] == "notion"
    assert prov["source_id"] == "p1"
    assert prov["source_url"] == "https://notion.so/p1"
    assert prov["source_hash"] == hashlib.sha256(csf["body"].encode("utf-8")).hexdigest()


def test_build_csf_passes_server_side_validation():
    # importer 구성 CSF는 S3 서버측 검증을 통과하는 형태여야 한다(대칭).
    from nexus.a2a.external_ingest_skill import validate_external_spec
    assert validate_external_spec(build_csf(_conv(), "p1")) is None
```

- [ ] **Step 2: 실패 확인**

Run: `cd nexus && python -m pytest tests/test_notion_importer.py -q`
Expected: FAIL (`notion_importer` 모듈 없음)

- [ ] **Step 3: build_csf 구현**

`nexus/nexus/ingest/sources/notion_importer.py`:

```python
"""Notion importer (S4) — Notion 페이지를 CSF로 변환해 S3 타입-인지 intake로 적재.

순수 오케스트레이터: ingest_fn 을 주입받아 a2a/DB에 무의존. 구체 ingest_fn(프로덕션
_default_external_ingest_fn) 와이어링은 CLI(합성 루트)가 한다. build_csf 는 S3 서버측
validate_external_spec 을 통과하는 형태를 구성으로 보장(id 형식 + source_hash=sha256(body)).
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from nexus.ingest.sources.base import ConvertedDoc


def build_csf(conv: ConvertedDoc, page_id: str) -> dict:
    """ConvertedDoc(markdown+frontmatter) → CSF dict. kind=NOTE(default-memo)."""
    body = conv.markdown
    return {
        "id": f"ext-notion-{page_id}",
        "kind": "NOTE",
        "title": conv.frontmatter.get("title") or page_id,
        "body": body,
        "provenance": {
            "source_tool": "notion",
            "source_id": page_id,
            "source_url": conv.frontmatter.get("origin_url", ""),
            "source_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        },
    }


@dataclass
class ImportReport:
    ingested: int = 0
    idempotent: int = 0
    skipped: int = 0
    results: list[dict] = field(default_factory=list)


# IngestFn: (csf, tenant) -> outcome(awaitable). 프로덕션은 _default_external_ingest_fn.
IngestFn = Callable[[dict, str], Awaitable]


async def import_notion(source, tenant: str, ingest_fn: IngestFn) -> ImportReport:
    """source.live_ids() 페이지를 fetch→csf→ingest. per-page skip(1건 실패가 전체 중단 금지)."""
    report = ImportReport()
    for page_id in sorted(source.live_ids()):
        try:
            ref = source.page_ref(page_id)
            conv = source.fetch_markdown(ref)
            outcome = await ingest_fn(build_csf(conv, page_id), tenant)
            if getattr(outcome, "idempotent_hit", False):
                report.idempotent += 1
            else:
                report.ingested += 1
            report.results.append({"page_id": page_id, "rid": outcome.resource_rid})
        except Exception as e:  # noqa: BLE001 — per-page 격리(기존 ingest 에러 규칙)
            report.skipped += 1
            report.results.append({"page_id": page_id, "error": str(e)})
    return report
```

- [ ] **Step 4: 통과 확인**

Run: `cd nexus && python -m pytest tests/test_notion_importer.py -q`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add nexus/nexus/ingest/sources/notion_importer.py nexus/tests/test_notion_importer.py
git commit -m "feat(notion): build_csf + ImportReport (S4 Chunk 1)"
```

### Task 2: import_notion 오케스트레이션 테스트

**Files:**
- Modify: `nexus/tests/test_notion_importer.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
class _FakeSource:
    def __init__(self, ids, convs):
        self._ids, self._convs = ids, convs
    def live_ids(self):
        return set(self._ids)
    def page_ref(self, pid):
        return type("R", (), {"id": pid, "url": f"u/{pid}", "last_edited": "t"})()
    def fetch_markdown(self, ref):
        return self._convs[ref.id]


class _Outcome:
    def __init__(self, rid, idempotent=False):
        self.resource_rid, self.idempotent_hit = rid, idempotent


@pytest.mark.asyncio
async def test_import_notion_ingests_all_pages():
    convs = {"a": _conv(title="A"), "b": _conv(title="B")}
    calls = []
    async def fake_ingest(csf, tenant):
        calls.append(csf["id"])
        return _Outcome(rid=f"doc_{csf['provenance']['source_id']}")
    report = await import_notion(_FakeSource(["a", "b"], convs), "acme", fake_ingest)
    assert report.ingested == 2 and report.skipped == 0
    assert set(calls) == {"ext-notion-a", "ext-notion-b"}


@pytest.mark.asyncio
async def test_import_notion_skips_failing_page_without_aborting():
    convs = {"a": _conv(), "b": _conv()}
    async def fake_ingest(csf, tenant):
        if csf["provenance"]["source_id"] == "a":
            raise RuntimeError("boom")
        return _Outcome(rid="doc_b")
    report = await import_notion(_FakeSource(["a", "b"], convs), "acme", fake_ingest)
    assert report.ingested == 1 and report.skipped == 1


@pytest.mark.asyncio
async def test_import_notion_counts_idempotent():
    async def fake_ingest(csf, tenant):
        return _Outcome(rid="doc_a", idempotent=True)
    report = await import_notion(_FakeSource(["a"], {"a": _conv()}), "acme", fake_ingest)
    assert report.idempotent == 1 and report.ingested == 0
```

- [ ] **Step 2: asyncio 마커 확인**

Run: `cd nexus && python -m pytest tests/test_notion_importer.py -q`
Expected: PASS (5 tests). 만약 async 테스트가 skip/에러면 `pytest.ini`/`pyproject`의 `asyncio_mode` 확인(기존 a2a async 테스트가 도므로 설정 존재; 없으면 `@pytest.mark.asyncio` 대신 기존 패턴 따름).

- [ ] **Step 3: Commit**

```bash
git add nexus/tests/test_notion_importer.py
git commit -m "test(notion): import_notion 오케스트레이션(적재/skip/멱등) (S4)"
```

---

## Chunk 2: NotionSource 열거 (live_ids / page_ref)

`roots`(page id 목록) 하위 page id 열거. 가짜 client로 단위 테스트.

### Task 3: page_ref + live_ids 구현

**Files:**
- Modify: `nexus/nexus/ingest/sources/notion.py:66-70` (NotImplementedError 대체)
- Test: `nexus/tests/test_notion_source.py`

- [ ] **Step 1: 실패 테스트 추가**

`nexus/tests/test_notion_source.py` 의 `FakeClient` 를 확장하고 테스트 추가. FakeClient 에 `pages.retrieve`/`databases.query` 추가(아래) 후:

```python
class FakeTreeClient:
    """roots 하위 트리: page p_root → child_page p_child + child_database db1(행 r1)."""
    def __init__(self):
        self.blocks = type("B", (), {"children": self})()
        self.pages = type("P", (), {"retrieve": self._retrieve})()
        self.databases = type("D", (), {"query": self._query})()
        self._tree = {
            "p_root": [
                {"type": "child_page", "id": "p_child"},
                {"type": "child_database", "id": "db1"},
            ],
            "p_child": [],
        }

    def list(self, block_id, start_cursor=None):  # blocks.children.list
        return {"results": self._tree.get(block_id, []), "has_more": False, "next_cursor": None}

    def _retrieve(self, page_id):
        return {"id": page_id, "url": f"https://notion.so/{page_id}",
                "last_edited_time": "2026-06-25T00:00:00Z"}

    def _query(self, database_id, start_cursor=None):
        return {"results": [{"id": "r1"}], "has_more": False, "next_cursor": None}


def test_live_ids_enumerates_root_children_and_db_rows():
    src = NotionSource(client=FakeTreeClient(), roots=["p_root"], tenant="default")
    # db 컨테이너(db1) 자체는 페이지 아님 — 행 r1만 페이지로 수집.
    assert src.live_ids() == {"p_root", "p_child", "r1"}


def test_page_ref_builds_from_retrieve():
    src = NotionSource(client=FakeTreeClient(), roots=[], tenant="default")
    ref = src.page_ref("p_root")
    assert ref.id == "p_root"
    assert ref.url == "https://notion.so/p_root"
    assert ref.last_edited == "2026-06-25T00:00:00Z"
```

- [ ] **Step 2: 실패 확인**

Run: `cd nexus && python -m pytest tests/test_notion_source.py -q -k "live_ids or page_ref"`
Expected: FAIL (NotImplementedError / page_ref 없음)

- [ ] **Step 3: 구현**

`nexus/nexus/ingest/sources/notion.py` 의 `list_changed`/`live_ids` (NotImplementedError) 를 교체:

```python
    def page_ref(self, page_id: str) -> PageRef:
        """page id → PageRef(id/url/last_edited). client.pages.retrieve 사용."""
        p = self.client.pages.retrieve(page_id=page_id)
        return PageRef(
            id=page_id,
            url=p.get("url", f"https://notion.so/{page_id}"),
            last_edited=p.get("last_edited_time", ""),
        )

    def _db_rows(self, database_id: str) -> list[dict]:
        rows: list[dict] = []
        cursor = None
        while True:
            resp = self.client.databases.query(database_id=database_id, start_cursor=cursor)
            rows.extend(resp.get("results", []))
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
        return rows

    def _collect(self, page_id: str, ids: set[str]) -> None:
        if page_id in ids:
            return
        ids.add(page_id)
        for block in self._all_blocks(page_id):
            t = block.get("type")
            if t == "child_page":
                self._collect(block["id"], ids)
            elif t == "child_database":
                for row in self._db_rows(block["id"]):
                    self._collect(row["id"], ids)

    def live_ids(self) -> set[str]:
        """roots(page id) 하위에 도달 가능한 page id 집합(child_page 재귀 + child_database 행)."""
        ids: set[str] = set()
        for root in self.roots:
            self._collect(root, ids)
        return ids

    def list_changed(self, since: str | None) -> list[PageRef]:
        raise NotImplementedError  # 증분 sync 는 S4 비범위(후속)
```

(주: 기존 `list_changed`/`live_ids` 의 NotImplementedError 두 메서드를 위 블록으로 대체. `list_changed`는 증분 sync 후속이라 NotImplementedError 유지.)

- [ ] **Step 4: 통과 확인**

Run: `cd nexus && python -m pytest tests/test_notion_source.py -q`
Expected: PASS (기존 fetch_markdown + 신규 live_ids/page_ref)

- [ ] **Step 5: ruff + Commit**

```bash
cd nexus && python -m ruff check nexus/ingest/sources/notion.py tests/test_notion_source.py
git add nexus/nexus/ingest/sources/notion.py nexus/tests/test_notion_source.py
git commit -m "feat(notion): live_ids/page_ref 열거(roots 하위 child_page+db 행) (S4 Chunk 2)"
```

---

## Chunk 3: CLI ingest-notion + 의존성

### Task 4: notion-client optional 의존

**Files:**
- Modify: `nexus/pyproject.toml`

- [ ] **Step 1: optional 의존 추가**

`nexus/pyproject.toml` 의 `[project.optional-dependencies]` 에 추가(없으면 섹션 신설):

```toml
notion = ["notion-client>=2.2.0"]
```

- [ ] **Step 2: Commit**

```bash
git add nexus/pyproject.toml
git commit -m "build(notion): notion-client optional 의존 (S4)"
```

### Task 5: CLI ingest-notion 명령

**Files:**
- Modify: `nexus/nexus/cli.py` (새 `@app.command`)
- Test: `nexus/tests/test_notion_importer.py` (CLI smoke — 주입)

- [ ] **Step 1: 실패 테스트 추가(smoke — import 가능 + 합성)**

`nexus/tests/test_notion_importer.py` 끝에:

```python
def test_cli_ingest_notion_registered():
    from nexus.cli import app
    names = {c.name for c in app.registered_commands}
    assert "ingest-notion" in names
```

- [ ] **Step 2: 실패 확인**

Run: `cd nexus && python -m pytest tests/test_notion_importer.py -q -k cli`
Expected: FAIL (명령 미등록)

- [ ] **Step 3: CLI 명령 구현**

`nexus/nexus/cli.py` 에 새 명령 추가(기존 `@app.command()` 패턴 따라):

```python
@app.command("ingest-notion")
def ingest_notion(
    tenant: str = "default",
    roots: str = typer.Option("", help="쉼표구분 Notion page id 목록"),
    token_env: str = "NOTION_TOKEN",
) -> None:
    """Notion 페이지를 CSF로 변환해 S3 타입-인지 intake로 적재(Path B)."""
    import asyncio

    from nexus.a2a.server import _default_external_ingest_fn
    from nexus.ingest.sources.notion import NotionSource
    from nexus.ingest.sources.notion_importer import import_notion

    root_list = [r.strip() for r in roots.split(",") if r.strip()]
    if not root_list:
        typer.echo("roots 가 비었습니다 (--roots 'pageid1,pageid2')")
        raise typer.Exit(code=1)
    try:
        source = NotionSource(token_env=token_env, roots=root_list, tenant=tenant)
    except KeyError:
        typer.echo(f"환경변수 {token_env} 없음 — Notion 통합 토큰 필요")
        raise typer.Exit(code=1) from None
    except ImportError:
        typer.echo("notion-client 미설치 — `pip install nexus[notion]`")
        raise typer.Exit(code=1) from None

    report = asyncio.run(import_notion(source, tenant, _default_external_ingest_fn))
    typer.echo(
        f"ingested={report.ingested} idempotent={report.idempotent} skipped={report.skipped}"
    )
```

- [ ] **Step 4: 통과 확인**

Run: `cd nexus && python -m pytest tests/test_notion_importer.py -q`
Expected: PASS (전체)

- [ ] **Step 5: ruff + Commit**

```bash
cd nexus && python -m ruff check nexus/cli.py tests/test_notion_importer.py
git add nexus/nexus/cli.py nexus/tests/test_notion_importer.py
git commit -m "feat(notion): nexus ingest-notion CLI(합성 루트 와이어링) (S4 Chunk 3)"
```

---

## Task 6: 전체 회귀

**Files:** (없음 — 검증 전용)

- [ ] **Step 1: nexus 전체 + 외부-spec E2E**

Run: `cd nexus && python -m pytest -q`
Run (repo root): `python -m pytest tests/ -q`
Expected: 둘 다 PASS(순수 추가 — 기존 경로 불변)

- [ ] **Step 2: ruff 변경분 전체**

Run: `cd nexus && python -m ruff check nexus/ingest/sources/ nexus/cli.py tests/test_notion_importer.py tests/test_notion_source.py`
Expected: All checks passed!

## Acceptance (스펙 §8 대응)

- [ ] build_csf → 유효 CSF(validate_external_spec 통과) (Task 1)
- [ ] live_ids/page_ref 열거(가짜 client) (Task 3)
- [ ] import_notion 적재/skip/멱등 (Task 2)
- [ ] CLI ingest-notion 등록 + 친절한 에러 (Task 5)
- [ ] 전체 회귀 통과 (Task 6)
