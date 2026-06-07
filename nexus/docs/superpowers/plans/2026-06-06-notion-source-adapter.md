# Notion 소스 어댑터 — 구현 계획

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** Notion 기획문서를 증분 동기화로 Nexus에 적재해, 기획자가 개념·정의를 자연어로 조회(grounding)할 수 있게 한다.

**Architecture:** 소스-무관 `DocumentSource` Protocol + `NotionSource`(블록→Markdown+frontmatter, 텍스트우선·이미지갭표기, last_edited_time 증분). 기존 `run_ingest` 재사용. `_save_document`/`_save_chunks`를 frontmatter 오버라이드 가능하게 소폭 수정(git 적재 불변). `nexus notion-sync` CLI.

**Tech Stack:** Python 3.11+, `notion-client` SDK(신규 의존성), 기존 Nexus ingest, pytest.

**Spec:** `docs/superpowers/specs/2026-06-06-notion-source-adapter-design.md`

---

## P0 — 시작 전 확인 (코드 아님)

- [ ] `nexus/ingest/pipeline.py`의 `_save_document`(L50-92)·`_save_chunks`(L95-) INSERT/ON CONFLICT 실제 컬럼·`$`번호 재확인. `classifier.py`의 frontmatter 우선순위(`doc_type`/`classification`/`owner`) 확인. `cli.py` Typer 패턴·`run_ingest` 시그니처(`docs_path, force, tenant, config_path`) 확인.
- [ ] `pyproject.toml`에 `notion-client>=2.2.1` 추가 후 설치.

## 파일 구조

| 파일 | 책임 | 신규/수정 |
|---|---|---|
| `nexus/ingest/sources/__init__.py` | 패키지 | 신규 |
| `nexus/ingest/sources/base.py` | `DocumentSource` Protocol + `PageRef`/`ConvertedDoc` | 신규 |
| `nexus/ingest/sources/notion_convert.py` | 블록→Markdown + image_count (순수함수, 단위테스트 핵심) | 신규 |
| `nexus/ingest/sources/notion.py` | `NotionSource` (API 폴링·fetch·live_ids) | 신규 |
| `nexus/ingest/pipeline.py` | `_save_document`/`_save_chunks` frontmatter 오버라이드 + chunks metadata | 수정 |
| `nexus/ingest/sync_state.py` | 마지막 동기화 시각 저장/로드 | 신규 |
| `nexus/cli.py` | `notion-sync` 커맨드 | 수정 |
| `config.yaml` | `notion:` 블록 | 수정 |
| `pyproject.toml` | notion-client 의존성 | 수정 |

---

## Chunk 1: Protocol + 블록 변환 (인프라 무관, 순수 단위테스트)

### Task 1: DocumentSource Protocol + 타입

**Files:** Create `nexus/ingest/sources/__init__.py`, `nexus/ingest/sources/base.py`; Test `tests/test_document_source.py`

- [ ] **Step 1: 실패 테스트** — `PageRef`/`ConvertedDoc` 생성 + `DocumentSource` Protocol을 만족하는 더미 클래스가 런타임 체크 통과.

```python
# tests/test_document_source.py
from nexus.ingest.sources.base import PageRef, ConvertedDoc, DocumentSource

def test_types_and_protocol():
    ref = PageRef(id="p1", url="https://notion.so/p1", last_edited="2026-06-06T00:00:00Z")
    cd = ConvertedDoc(page_id="p1", markdown="# t", frontmatter={"title": "t"}, image_count=2)
    assert ref.id == "p1" and cd.image_count == 2

    class Dummy:
        def list_changed(self, since): return []
        def fetch_markdown(self, ref): return ConvertedDoc(ref.id, "", {}, 0)
        def live_ids(self): return set()
    assert isinstance(Dummy(), DocumentSource)  # runtime_checkable
```

- [ ] **Step 2: 실패 확인** → FAIL
- [ ] **Step 3: 구현**

```python
# nexus/ingest/sources/base.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

@dataclass
class PageRef:
    id: str
    url: str
    last_edited: str

@dataclass
class ConvertedDoc:
    page_id: str
    markdown: str
    frontmatter: dict = field(default_factory=dict)
    image_count: int = 0

@runtime_checkable
class DocumentSource(Protocol):
    def list_changed(self, since: str | None) -> list[PageRef]: ...
    def fetch_markdown(self, ref: PageRef) -> ConvertedDoc: ...
    def live_ids(self) -> set[str]: ...
```

- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat(sources): DocumentSource Protocol + 타입"`

### Task 2: 블록 → Markdown 변환 (단위테스트 핵심)

**Files:** Create `nexus/ingest/sources/notion_convert.py`; Test `tests/test_notion_convert.py`

- [ ] **Step 1: 실패 테스트** (Notion 블록 dict 픽스처 — 토큰 불필요)

```python
# tests/test_notion_convert.py
from nexus.ingest.sources.notion_convert import blocks_to_markdown

def _rt(text, **ann):
    return {"type": "text", "text": {"content": text},
            "annotations": {"bold": False, "italic": False, "code": False, **ann},
            "plain_text": text, "href": None}

def test_heading_paragraph_list():
    blocks = [
        {"type": "heading_1", "heading_1": {"rich_text": [_rt("제목")]}},
        {"type": "paragraph", "paragraph": {"rich_text": [_rt("본문 ")]}},
        {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [_rt("항목")]}},
    ]
    md, imgs = blocks_to_markdown(blocks)
    assert "# 제목" in md and "- 항목" in md and imgs == 0

def test_bold_and_code_annotations():
    blocks = [{"type": "paragraph", "paragraph": {"rich_text": [_rt("강조", bold=True)]}}]
    md, _ = blocks_to_markdown(blocks)
    assert "**강조**" in md

def test_image_is_counted_and_placeholdered():
    blocks = [{"type": "image", "image": {"type": "external",
              "external": {"url": "http://x/y.png"}}}]
    md, imgs = blocks_to_markdown(blocks)
    assert imgs == 1 and "y.png" in md  # 플레이스홀더 링크는 남기되 의미는 미캡처

def test_code_block():
    blocks = [{"type": "code", "code": {"language": "java",
              "rich_text": [_rt("int x = 5;")]}}]
    md, _ = blocks_to_markdown(blocks)
    assert "```" in md and "int x = 5;" in md
```

- [ ] **Step 2: 실패 확인** → FAIL
- [ ] **Step 3: 구현** (텍스트 충실 / 이미지 카운트. best-effort, 미지원 블록은 무시+무손실로 텍스트만.)

```python
# nexus/ingest/sources/notion_convert.py
from __future__ import annotations

def _rich_to_md(rich: list[dict]) -> str:
    out = []
    for r in rich or []:
        t = r.get("plain_text", r.get("text", {}).get("content", ""))
        ann = r.get("annotations", {})
        if ann.get("code"): t = f"`{t}`"
        if ann.get("bold"): t = f"**{t}**"
        if ann.get("italic"): t = f"*{t}*"
        href = r.get("href")
        if href: t = f"[{t}]({href})"
        out.append(t)
    return "".join(out)

def blocks_to_markdown(blocks: list[dict]) -> tuple[str, int]:
    """Notion 블록 리스트 → (markdown, image_count). 텍스트 충실, 이미지는 카운트+플레이스홀더."""
    lines: list[str] = []
    image_count = 0
    for b in blocks or []:
        bt = b.get("type")
        data = b.get(bt, {}) if bt else {}
        rich = data.get("rich_text", [])
        if bt == "heading_1":
            lines.append(f"# {_rich_to_md(rich)}")
        elif bt == "heading_2":
            lines.append(f"## {_rich_to_md(rich)}")
        elif bt == "heading_3":
            lines.append(f"### {_rich_to_md(rich)}")
        elif bt == "paragraph":
            lines.append(_rich_to_md(rich))
        elif bt == "bulleted_list_item":
            lines.append(f"- {_rich_to_md(rich)}")
        elif bt == "numbered_list_item":
            lines.append(f"1. {_rich_to_md(rich)}")
        elif bt == "to_do":
            mark = "x" if data.get("checked") else " "
            lines.append(f"- [{mark}] {_rich_to_md(rich)}")
        elif bt in ("quote", "callout"):
            lines.append(f"> {_rich_to_md(rich)}")
        elif bt == "code":
            lang = data.get("language", "")
            lines.append(f"```{lang}\n{_rich_to_md(rich)}\n```")
        elif bt == "divider":
            lines.append("---")
        elif bt == "image":
            image_count += 1
            src = data.get("external", {}).get("url") or data.get("file", {}).get("url", "")
            lines.append(f"![image]({src})")  # 의미는 미캡처(후속 비전 강화)
        else:
            # 미지원 블록: 텍스트가 있으면 살리고 아니면 무시 (무손실)
            if rich:
                lines.append(_rich_to_md(rich))
        lines.append("")
    return "\n".join(lines).strip() + "\n", image_count
```

- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat(sources): Notion 블록→Markdown 변환 (텍스트우선+이미지카운트)"`

### Task 3: NotionSource (fake client 단위테스트)

**Files:** Create `nexus/ingest/sources/notion.py`; Test `tests/test_notion_source.py`

- [ ] **Step 1: 실패 테스트** (notion 클라이언트 주입 → API 불필요)

```python
# tests/test_notion_source.py
from nexus.ingest.sources.notion import NotionSource
from nexus.ingest.sources.base import PageRef

class FakeClient:
    def __init__(self):
        self.blocks = type("B", (), {"children": self})()
    # client.blocks.children.list(block_id=..., start_cursor=...)
    def list(self, block_id, start_cursor=None):
        return {"results": [
            {"type": "heading_1", "heading_1": {"rich_text":
              [{"plain_text": "준회원 정책", "annotations": {}, "text": {"content": "준회원 정책"}}]}}
        ], "has_more": False, "next_cursor": None}

def test_fetch_markdown_builds_frontmatter_and_counts():
    src = NotionSource(client=FakeClient(), roots=[], tenant="default",
                       classification="INTERNAL", owner="@planner")
    ref = PageRef(id="pid1", url="https://notion.so/pid1", last_edited="2026-06-06T00:00:00Z")
    cd = src.fetch_markdown(ref)
    assert "# 준회원 정책" in cd.markdown
    fm = cd.frontmatter
    assert fm["source_kind"] == "wiki"
    assert fm["origin_url"] == "https://notion.so/pid1"
    assert fm["origin_last_edited"] == "2026-06-06T00:00:00Z"
    assert fm["owner"] == "@planner"
    assert fm["classification"] == "INTERNAL"
    assert fm["doc_type"]            # classifier 경로판정 보완용 채워짐
    assert "image_count" in fm
```

- [ ] **Step 2: 실패 확인** → FAIL
- [ ] **Step 3: 구현** (`list_changed`/`live_ids`는 실제 search/query API; 단위테스트는 `fetch_markdown` 위주. 블록 페이지네이션 처리.)

```python
# nexus/ingest/sources/notion.py
from __future__ import annotations
import os
from nexus.ingest.sources.base import PageRef, ConvertedDoc
from nexus.ingest.sources.notion_convert import blocks_to_markdown

class NotionSource:
    def __init__(self, client=None, token_env="NOTION_TOKEN", roots=None,
                 tenant="default", classification="INTERNAL", owner="unknown"):
        if client is None:
            from notion_client import Client  # 지연 임포트 (의존성)
            client = Client(auth=os.environ[token_env])
        self.client = client
        self.roots = roots or []
        self.tenant = tenant
        self.classification = classification
        self.owner = owner

    def _all_blocks(self, page_id) -> list[dict]:
        blocks, cursor = [], None
        while True:
            resp = self.client.blocks.children.list(block_id=page_id, start_cursor=cursor)
            blocks.extend(resp.get("results", []))
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
        return blocks

    def fetch_markdown(self, ref: PageRef) -> ConvertedDoc:
        blocks = self._all_blocks(ref.id)
        md, image_count = blocks_to_markdown(blocks)
        first = md.splitlines()[0] if md.strip() else ""
        title = first.removeprefix("### ").removeprefix("## ").removeprefix("# ").strip() or ref.id
        fm = {
            "title": title,
            "doc_type": "wiki",          # classifier 경로판정 무력화 보완
            "origin_url": ref.url,
            "origin_last_edited": ref.last_edited,
            "source_kind": "wiki",
            "owner": self.owner,
            "classification": self.classification,
            "image_count": image_count,
        }
        return ConvertedDoc(page_id=ref.id, markdown=md, frontmatter=fm, image_count=image_count)

    def list_changed(self, since: str | None) -> list[PageRef]:
        # 실제: client.search 또는 databases.query + last_edited_time 필터.
        # roots 각각 순회. (통합 단계에서 실제 API로 구현/검증.)
        raise NotImplementedError  # Task 6 통합에서 구현

    def live_ids(self) -> set[str]:
        raise NotImplementedError  # Task 6 통합에서 구현
```

- [ ] **Step 4: 통과 확인** → PASS (fetch_markdown 단위)
- [ ] **Step 5: 커밋** — `git commit -m "feat(sources): NotionSource fetch_markdown + frontmatter"`

---

## Chunk 2: 파이프라인 frontmatter 오버라이드 (integration)

### Task 4: _save_document / _save_chunks 수정 + git 불변 회귀

**Files:** Modify `nexus/ingest/pipeline.py`; Test `tests/test_pipeline_frontmatter_override.py` (integration)

- [ ] **Step 1: 실패 통합테스트** (`@pytest.mark.integration`)
  - (a) **git 회귀:** frontmatter 없는 .md 적재 → documents.source_kind='git', owner='indexer' (현행 유지). **+ 동일 문서 재적재(ON CONFLICT 경로)에서도 git/indexer 유지** 케이스 포함.
  - (b) **wiki 오버라이드:** frontmatter에 source_kind=wiki/owner/origin_url 있는 .md 적재 → documents.source_kind='wiki', owner=그 값; chunks.metadata에 origin_url 보존.

```python
# tests/test_pipeline_frontmatter_override.py
import pytest
pytestmark = pytest.mark.integration
# run_ingest로 staging 디렉터리 적재 후 documents/chunks 행을 조회해 source_kind/owner/metadata 검증.
# (구체 픽스처·조회는 기존 통합테스트 패턴 따름)
```

- [ ] **Step 2: 실패 확인** → FAIL
- [ ] **Step 3: 구현** (P0에서 확인한 실제 INSERT에 맞춰):
  - `_save_document`: SQL 본문의 **인라인 리터럴 `'git'`(source_kind)·`'indexer'`(owner)를 플레이스홀더로 교체** → `collected.frontmatter.get("source_kind","git")` / `.get("owner","indexer")`. `$`번호 시프트. **ON CONFLICT DO UPDATE에 source_kind/owner SET 신규 추가**(재동기화 값 갱신 — 현재 절엔 없음).
  - `_save_chunks`: INSERT에 **`metadata` 컬럼·플레이스홀더 신규 추가** + `json.dumps({origin_url, origin_last_edited, image_count})`(없으면 `{}`), 인라인 `'git'`/`'indexer'`도 파라미터화. **단 `_save_chunks`는 매번 기존 청크를 `superseded` 처리 후 신규 rid로 INSERT라 ON CONFLICT 경로를 거의 안 탐 → ON CONFLICT 손질 불필요(INSERT 값에만 반영).**
  - **`classification`은 손대지 않음** — classifier가 frontmatter `classification`을 읽어 이미 반영(`$3::classification_level`). 중복 파라미터화 금지.
  - frontmatter 없으면 전부 기존 기본값 → **git 경로 무변경**(재적재 포함).

- [ ] **Step 4: 통과 확인** (DB 환경) → PASS (a·b 모두)
- [ ] **Step 5: 커밋** — `git commit -m "feat(ingest): frontmatter로 source_kind/owner/metadata 오버라이드 (git 불변)"`

---

## Chunk 3: 동기화 상태 + CLI (integration)

### Task 5: sync_state (단위)

**Files:** Create `nexus/ingest/sync_state.py`; Test `tests/test_sync_state.py`

- [ ] **Step 1~5:** 마지막 동기화 시각을 JSON 파일에 저장/로드(`load(source)->ts|None`, `save(source, ts)`). 기본 경로 `.nexus/sync_state.json`(없으면 생성). `load`가 None이면 호출측에서 full 동기화로 폴백. tmp_path로 단위테스트. 커밋.

### Task 6: NotionSource.list_changed / live_ids (실제 API — integration)

**Files:** Modify `nexus/ingest/sources/notion.py`; Test `tests/test_notion_source.py` (integration, NOTION_TOKEN 필요)

- [ ] **Step 1: 실패 테스트** — `@pytest.mark.integration` + `NOTION_TOKEN` 없으면 skip. roots 1개로 list_changed(None)이 PageRef 반환, live_ids가 비지 않음.
- [ ] **Step 2~4:** **root별 object type을 먼저 조회**(`client.pages.retrieve`/`databases.retrieve` 또는 search의 object 필드)해 분기 — **database면 `databases.query`(`last_edited_time` 필터·정렬 지원), page면 `search` 또는 자식 재귀**. 페이지네이션·백오프. last_edited_time으로 since 필터. live_ids는 roots 전체 열거(증분 아님 → --full 시).
- [ ] **Step 5: 커밋**

### Task 7: `nexus notion-sync` CLI

**Files:** Modify `nexus/cli.py`, `config.yaml`, `pyproject.toml`

- [ ] **Step 1: config + 의존성**

```yaml
# config.yaml
notion:
  token_env: NOTION_TOKEN
  roots: []            # database_id/page_id 목록 (사용자가 채움)
  tenant: default
  classification: INTERNAL
  owner: "@planner"
```

- [ ] **Step 2: CLI** — `notion-sync(--since auto|<ts>, --full, --staging)`:
  - `--since auto`면 `sync_state.load("notion")`; None이면 full(전체).
  - NotionSource 구성(config) → `list_changed(since)` → 각 `fetch_markdown` → **staging/notion/<page_id>.md 작성**. frontmatter 직렬화는 `python-frontmatter` 사용(collector가 그걸로 파싱):
    ```python
    import frontmatter
    post = frontmatter.Post(cd.markdown, **cd.frontmatter)
    (staging / "notion" / f"{cd.page_id}.md").write_text(frontmatter.dumps(post), encoding="utf-8")
    ```
  - `run_ingest(staging, force=bool(--full), tenant=config.notion.tenant)` → `sync_state.save("notion", now)`.
  - `--full`이면 `live_ids()`로 삭제 감지 → 사라진 doc soft_delete.
- [ ] **Step 3: 수동 검증** (사용자 토큰·roots 설정 후): `nexus notion-sync --full` → 적재 → `nexus query "준회원 정책"` 근거 답변.
- [ ] **Step 4: 커밋**

---

## Chunk 4: 가치 테스트 연결 (운영)

### Task 8: 실제 동기화 → 값/개념 조회 가치 테스트 투입

- [ ] 사용자: Notion integration 토큰 발급 + 기획 페이지 공유 + `config.notion.roots` 설정.
- [ ] `nexus notion-sync --full`로 기획문서 적재.
- [ ] 가치 검증 프로토콜(`specs/2026-06-06-value-validation-protocol.md`)에 **개념·정의 질문**을 포함해 실행. miss 분석에서 **"이미지-only 내용 때문에 막힌 비율"**을 별도 집계 → 비전 강화(후속) 필요성 판단.

---

## 범위 밖 (YAGNI — 별도 계획)

이미지 비전 강화 · ConfluenceSource(Protocol 경계는 이번에 마련) · 문서→claim 추출 · 모순·모호 탐지 · 실시간 webhook · documents 스키마 확장.
