# Notion 증분 sync + auto-classification (S4-follow-up) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Notion importer에 (1) 결정론적 제목-키워드 auto-classification(미매치 NOTE), (2) `since` 기반 증분 적재 + watermark를 추가한다.

**Architecture:** 둘 다 importer 순수 로직 + CLI 옵션. `classify_kind`(순수)로 build_csf의 kind 결정. import_notion에 `since` 필터 + watermark. NotionSource.list_changed 풀구현/검색API는 후속(importer 인라인 필터). default-memo 불변. LLM 미사용(결정론 — nexus 규율).

**Tech Stack:** Python, Typer, pytest. S4 `notion_importer.py`/`cli.py` 확장.

**Spec:** `docs/superpowers/specs/2026-06-25-notion-incremental-classify-s4f-design.md`

---

## File Structure

| 파일 | 변경 |
|---|---|
| `nexus/nexus/ingest/sources/notion_importer.py` | `classify_kind` 추가 + `build_csf`(kind=classify_kind) + `import_notion`(since/watermark) + `ImportReport.watermark` |
| `nexus/tests/test_notion_importer.py` | classify_kind + build_csf 분류 + import_notion since/watermark 테스트 |
| `nexus/nexus/cli.py` | `ingest-notion`에 `--since` + watermark 출력 |

---

## Chunk A: auto-classification (결정론)

### Task 1: classify_kind + build_csf 반영

**Files:**
- Modify: `nexus/nexus/ingest/sources/notion_importer.py`
- Test: `nexus/tests/test_notion_importer.py`

- [ ] **Step 1: 실패 테스트 추가**

`nexus/tests/test_notion_importer.py` 의 import 줄에 `classify_kind` 추가:

```python
from nexus.ingest.sources.notion_importer import build_csf, classify_kind, import_notion
```

그리고 테스트 추가(파일 끝):

```python
def test_classify_kind_maps_title_keywords():
    assert classify_kind("ADR-001: 결제 DB 선택") == "ADR"
    assert classify_kind("RFC: A2A 도입") == "RFC"
    assert classify_kind("Design Doc — 결제") == "DESIGN"
    assert classify_kind("Spec for payment") == "DESIGN"   # spec→DESIGN 정규화
    assert classify_kind("Runbook: 장애 대응") == "RUNBOOK"
    assert classify_kind("Postmortem 2026-06") == "POSTMORTEM"


def test_classify_kind_defaults_to_note():
    assert classify_kind("결제 기획") == "NOTE"          # 비키워드
    assert classify_kind("Payment PRD") == "NOTE"        # 첫 토큰만 본다(보수적)
    assert classify_kind("") == "NOTE"


def test_build_csf_uses_classification():
    csf = build_csf(_conv(title="ADR: 결제"), "p1")
    assert csf["kind"] == "ADR"
    # 비키워드 제목은 기존대로 NOTE(회귀 없음)
    assert build_csf(_conv(title="결제 기획"), "p1")["kind"] == "NOTE"
```

- [ ] **Step 2: 실패 확인**

Run: `cd nexus && python -m pytest tests/test_notion_importer.py -q -k "classify or uses_classification"`
Expected: FAIL (`classify_kind` 없음 / build_csf kind 고정 NOTE)

- [ ] **Step 3: 구현**

`nexus/nexus/ingest/sources/notion_importer.py` 의 import 에 `re` 추가하고, `build_csf` 위에 추가:

```python
# 제목 첫 토큰 → 축-A 타입(결정론적 휴리스틱; LLM 미사용 — nexus 규율). 미매치 NOTE.
_KEYWORD_TO_TYPE = {
    "adr": "ADR", "rfc": "RFC", "prd": "PRD", "design": "DESIGN",
    "spec": "DESIGN", "runbook": "RUNBOOK", "postmortem": "POSTMORTEM",
}


def classify_kind(title: str) -> str:
    """제목 첫 토큰으로 축-A 타입 추론(결정론). 미매치→NOTE(default-memo 정합)."""
    tokens = re.split(r"[^a-z0-9]+", (title or "").strip().lower(), maxsplit=1)
    return _KEYWORD_TO_TYPE.get(tokens[0] if tokens else "", "NOTE")
```

그리고 `build_csf` 의 `"kind": "NOTE",` 를:

```python
        "kind": classify_kind(conv.frontmatter.get("title", "") or ""),
```

- [ ] **Step 4: 통과 확인**

Run: `cd nexus && python -m pytest tests/test_notion_importer.py -q`
Expected: PASS(기존 + 신규). 특히 `test_build_csf_produces_deterministic_id_and_hash`(title="결제 기획"→kind NOTE) 회귀 없음.

- [ ] **Step 5: ruff + Commit**

```bash
cd nexus && python -m ruff check nexus/ingest/sources/notion_importer.py tests/test_notion_importer.py
git add nexus/nexus/ingest/sources/notion_importer.py nexus/tests/test_notion_importer.py
git commit -m "feat(notion): 결정론적 제목-키워드 auto-classification (S4f Chunk A)"
```

---

## Chunk B: 증분 sync (since/watermark) + CLI

### Task 2: import_notion since 필터 + watermark

**Files:**
- Modify: `nexus/nexus/ingest/sources/notion_importer.py` (`ImportReport`, `import_notion`)
- Test: `nexus/tests/test_notion_importer.py`

- [ ] **Step 1: 실패 테스트 추가**

`_FakeSource` 를 last_edited 주입 가능하게 확장(기존 정의 교체):

```python
class _FakeSource:
    def __init__(self, ids, convs, edits=None):
        self._ids, self._convs, self._edits = ids, convs, edits or {}

    def live_ids(self):
        return set(self._ids)

    def page_ref(self, pid):
        le = self._edits.get(pid, "t")
        return type("R", (), {"id": pid, "url": f"u/{pid}", "last_edited": le})()

    def fetch_markdown(self, ref):
        return self._convs[ref.id]
```

테스트 추가:

```python
async def test_import_notion_since_skips_unchanged():
    convs = {"a": _conv(), "b": _conv()}
    edits = {"a": "2026-06-01", "b": "2026-06-10"}
    seen = []

    async def fake_ingest(csf, tenant):
        seen.append(csf["provenance"]["source_id"])
        return _Outcome(rid="x")

    report = await import_notion(
        _FakeSource(["a", "b"], convs, edits), "acme", fake_ingest, since="2026-06-05"
    )
    assert seen == ["b"]              # a(06-01)는 since 이전 → skip
    assert report.ingested == 1
    assert report.watermark == "2026-06-10"   # 본 run 최대 last_edited


async def test_import_notion_no_since_processes_all():
    convs = {"a": _conv(), "b": _conv()}
    async def fake_ingest(csf, tenant):
        return _Outcome(rid="x")
    report = await import_notion(_FakeSource(["a", "b"], convs), "acme", fake_ingest)
    assert report.ingested == 2
```

- [ ] **Step 2: 실패 확인**

Run: `cd nexus && python -m pytest tests/test_notion_importer.py -q -k "since or processes_all"`
Expected: FAIL (`since` 인자 없음 / watermark 없음)

- [ ] **Step 3: 구현**

`ImportReport` 에 필드 추가:

```python
@dataclass
class ImportReport:
    ingested: int = 0
    idempotent: int = 0
    skipped: int = 0
    watermark: str | None = None
    results: list[dict] = field(default_factory=list)
```

`import_notion` 시그니처/루프 교체:

```python
async def import_notion(source, tenant: str, ingest_fn: IngestFn, since: str | None = None) -> ImportReport:
    """live_ids 페이지를 fetch→csf→ingest. since 이후 변경분만(증분). per-page skip.

    watermark: 본 run 에서 본 ref 의 최대 last_edited(다음 since). 주의(한계): since 범위 내에서
    실패한 변경 페이지는 watermark 가 앞서가 다음 since 로 건너뛸 수 있다 — 복구는 since 없이 재실행.
    """
    report = ImportReport()
    max_seen = since or ""
    for page_id in sorted(source.live_ids()):
        try:
            ref = source.page_ref(page_id)
            le = getattr(ref, "last_edited", "") or ""
            if le > max_seen:
                max_seen = le
            if since and le <= since:
                continue
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
    report.watermark = max_seen or None
    return report
```

- [ ] **Step 4: 통과 확인**

Run: `cd nexus && python -m pytest tests/test_notion_importer.py -q`
Expected: PASS(기존 + 신규 전부 — since=None 기본 동작 불변)

- [ ] **Step 5: ruff + Commit**

```bash
cd nexus && python -m ruff check nexus/ingest/sources/notion_importer.py tests/test_notion_importer.py
git add nexus/nexus/ingest/sources/notion_importer.py nexus/tests/test_notion_importer.py
git commit -m "feat(notion): 증분 sync(since 필터 + watermark) (S4f Chunk B)"
```

### Task 3: CLI --since + watermark 출력

**Files:**
- Modify: `nexus/nexus/cli.py` (`ingest_notion`)

- [ ] **Step 1: 옵션 추가 + 통과 확인(smoke)**

`nexus/nexus/cli.py` 의 `ingest_notion` 시그니처에 `since` 추가:

```python
def ingest_notion(
    tenant: str = "default",
    roots: str = typer.Option("", help="쉼표구분 Notion page id 목록"),
    token_env: str = "NOTION_TOKEN",
    since: str = typer.Option("", help="ISO8601 watermark — 이후 변경분만(증분)"),
) -> None:
```

`asyncio.run(import_notion(...))` 호출에 since 전달:

```python
    report = asyncio.run(
        import_notion(source, tenant, _default_external_ingest_fn, since=since or None)
    )
    typer.echo(
        f"ingested={report.ingested} idempotent={report.idempotent} "
        f"skipped={report.skipped} watermark={report.watermark or ''}"
    )
```

Run: `cd nexus && python -m pytest tests/test_notion_importer.py -q -k cli`
Expected: PASS(`ingest-notion` 등록 유지)

- [ ] **Step 2: ruff + Commit**

```bash
cd nexus && python -m ruff check nexus/cli.py
git add nexus/nexus/cli.py
git commit -m "feat(notion): ingest-notion --since + watermark 출력 (S4f Chunk B)"
```

---

## Task 4: 전체 회귀

**Files:** (없음 — 검증 전용)

- [ ] **Step 1: nexus 전체 + 외부-spec E2E**

Run: `cd nexus && python -m pytest -q`
Run (repo root): `python -m pytest tests/ -q`
Expected: 둘 다 PASS(순수 추가 — 기존 경로 불변)

- [ ] **Step 2: ruff 변경분**

Run: `cd nexus && python -m ruff check nexus/ingest/sources/notion_importer.py nexus/cli.py tests/test_notion_importer.py`
Expected: All checks passed!

## Acceptance (스펙 §6 대응)

- [ ] classify_kind 키워드 매핑 + 미매치 NOTE + spec→DESIGN (Task 1)
- [ ] build_csf 분류 반영, 한국어 비키워드 제목 NOTE 회귀 없음 (Task 1)
- [ ] import_notion since 필터 + watermark (Task 2)
- [ ] CLI --since + watermark 출력 (Task 3)
- [ ] 전체 회귀 통과 (Task 4)
