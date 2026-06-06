# 도메인 불변식·값 거버넌스 — MVP 값조회 쐐기 구현 계획

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기획자가 자연어로 "준회원 플레이리스트 몇 개?"를 물으면, 코드 상수에서 현재값을 읽어 신뢰등급·신선도와 함께 답하는 Khala 확장 MVP를 만든다.

**Architecture:** Khala CRM에 신규 rtype `claim`(value-bearing) + `source_kind` enum에 `code` 추가. 값 조회는 claim → 코드 상수 재읽기로 *현재값*을 결정론적으로 반환하고, (파일+심볼) hash로 신선도를 판정한다. 표면은 CLI 우선 → 기존 MCP 서버에 도구 1개. 마지막 마일스톤은 가치 검증 프로토콜 실행(게이트).

**Tech Stack:** Python 3.11+, Typer CLI, PostgreSQL 16 + **asyncpg**(`$N` placeholder), dataclass CRM, pytest(integration 마커). mecab/embedding 불필요(검색 아닌 결정론 값 조회).

**Spec:** `docs/superpowers/specs/2026-06-06-domain-invariant-governance-design.md`
**검증 프로토콜:** `docs/superpowers/specs/2026-06-06-value-validation-protocol.md`

> **실행 진행 (2026-06-06):** 태스크 **1·2·3·4·5·6·7·8·9 완료** — 코어 + **DB 통합 + CLI end-to-end**. 실 Postgres(테스트 DB) + fixtures로 검증: `khala claim-value 준회원` → "현재 5", `재생곡` → "현재 360". **단위 18 + 통합 2 = 20 tests green.**
> **환경 메모:** 이 환경(Windows)에서 pytest-asyncio **async-generator fixture가 깨짐** → conftest `db_pool` 의존 통합테스트 불가. Archon 통합테스트는 자체 asyncio 루프로 우회(`tests/test_claim_integration.py`). (pytest 8.4.2 / pytest-asyncio 0.26.0로 업그레이드 — pyproject 선언 충족.)
> **태스크 10 완료:** `/claims/value` API + `archon_claim_value` MCP 도구 — TestClient로 검증(준회원→5, high, fresh). **AI/기획자 NL 경로 완성.** (Tasks 1–10 전부 완료.)
> **남음:** **11**(실제 기획자 가치검증 — pfplay 실제 상수 + 기획자 섭외). Notion 적재는 별도 계획(`2026-06-06-notion-source-adapter.md`).

---

## 확인된 실제 스키마 사실 (리뷰로 검증 완료 — 반드시 준수)

- `KhalaResource`(models/resource.py): `rid`,`rtype`는 **기본값 없는 필수 필드**. 나머지는 기본값 보유. `status` 기본 `"active"`, `source_kind` 기본 `"git"`.
- DB enum: `classification_level(PUBLIC|INTERNAL|RESTRICTED)`, `resource_status(active|superseded|soft_deleted)`, `source_kind(git|wiki|file|otel|manual)`. **컬럼은 enum 타입**.
- 각 테이블에 `CONSTRAINT chk_X_rtype CHECK (rtype='X')`.
- **드라이버 = asyncpg** (conftest `asyncpg.create_pool`). `base_filter_sql()`는 psycopg `%(..)s` 스타일이므로 **그대로 쓰지 말고**, asyncpg `$N` + `::classification_level` 캐스트로 직접 작성.
- 통합테스트: `@pytest.mark.integration` 필수 + `KHALA_TEST_DB_URL` 없으면 자동 skip. `db_pool`은 session-scope asyncpg 풀. `clean_db`는 고정 목록 TRUNCATE(**claims 미포함 → 추가 필요**).
- `rid` 생성: `make_rid(prefix, *parts)` → `f"{prefix}_{hash12}"`. **prefix에 콜론 금지**(`make_rid("claim", ...)` → `claim_<hash>`).

## 파일 구조

| 파일 | 책임 | 신규/수정 |
|---|---|---|
| `khala/models/claim.py` | `Claim(KhalaResource)` dataclass | 신규 |
| `khala/rid.py` | `claim_rid()` 추가 | 수정 |
| `init.sql` | `ALTER TYPE source_kind ADD 'code'` + `claims` 테이블 | 수정 |
| `tests/conftest.py` | `clean_db` TRUNCATE에 `claims` 추가 | 수정 |
| `khala/index/code_source.py` | 코드 상수 값+hash 추출 | 신규 |
| `khala/claims/repository.py` | claim CRUD (asyncpg, CRM 필터) | 신규 |
| `khala/claims/value_query.py` | claim → 현재값+신선도+신뢰등급 | 신규 |
| `khala/claims/answer.py` | 캘리브레이션 답변 조립 | 신규 |
| `khala/claims/seed.py` | claims.yaml 로더 (seed 시 hash 스냅샷) | 신규 |
| `khala/cli.py` | `claim-value`/`claim-seed` 커맨드 | 수정 |
| `khala/api.py` | MCP 도구 `claim_value` 1개 | 수정 |
| `claims.yaml`, `config.yaml` | 시드 + 코드경로 | 신규/수정 |
| `tests/test_claim_model.py` 등 | 테스트 | 신규 |

---

## Chunk 1: Claim 모델 + rid + 스키마

### Task 1: Claim 데이터 모델

**Files:** Create `khala/models/claim.py`; Test `tests/test_claim_model.py`

- [ ] **Step 1: 실패 테스트**

```python
# tests/test_claim_model.py
from khala.models.claim import Claim

def test_claim_defaults_and_crm_separation():
    c = Claim(
        claim_id="associate-max-playlists", kind="invariant",
        concepts=["준회원", "플레이리스트"],
        statement="준회원은 플레이리스트를 최대 N개 가질 수 있다",
        value_source="PlaylistPolicy.ASSOCIATE_MAX_PLAYLISTS",
        value_ref_kind="code_constant",
        criticality="core", owner="@backend-lead",
    )
    assert c.rtype == "claim"
    assert c.rid.startswith("claim_")        # make_rid prefix, 콜론 없음
    assert c.status == "active"               # CRM resource_status — 절대 검증상태로 오염 금지
    assert c.claim_status == "unverified"     # claim 검증상태는 별도 필드
    assert c.confidence == "low"
    assert c.source_kind == "code"            # value-bearing claim은 code 소스
    assert c.owner == "@backend-lead"
```

- [ ] **Step 2: 실패 확인** — Run: `pytest tests/test_claim_model.py -v` → FAIL (ImportError)

- [ ] **Step 3: 구현** (rid/rtype 기본값 재선언 → 키워드만으로 생성 가능. CRM `status`는 건드리지 않음.)

```python
# khala/models/claim.py
from dataclasses import dataclass, field
from khala.models.resource import KhalaResource
from khala.rid import claim_rid

@dataclass
class Claim(KhalaResource):
    # 기본값 부여로 키워드 생성 허용 (base에선 필수였음). __post_init__에서 채움.
    rid: str = ""
    rtype: str = "claim"
    source_kind: str = "code"          # value-bearing claim은 코드 소스 (CRM 기본 'git' 오버라이드)

    # claim 고유
    claim_id: str = ""
    kind: str = "invariant"           # goal | invariant | requirement
    concepts: list[str] = field(default_factory=list)
    statement: str = ""
    value_source: str | None = None
    value_ref_kind: str | None = None  # code_constant | config_key | db_default
    criticality: str = "peripheral"    # core | peripheral
    activity: str = "active"           # active | dormant | archived
    claim_status: str = "unverified"   # invariant: held|violated|unverified / requirement: reflected|partial|not-reflected|unverified
    confidence: str = "low"            # high | medium | low
    value_symbol_hash: str | None = None
    last_verified_commit: str | None = None

    def __post_init__(self):
        if not self.rid:
            self.rid = claim_rid(self.tenant, self.claim_id)
```

> 주: `status`(CRM)는 base 기본 `"active"`를 그대로 상속 — base_filter `status='active'` 가시성 보존. 검증상태는 오직 `claim_status`.

- [ ] **Step 4: 통과 확인** — Run: `pytest tests/test_claim_model.py -v` → PASS

- [ ] **Step 5: 커밋** — `git add khala/models/claim.py tests/test_claim_model.py && git commit -m "feat(claim): Claim 모델 (CRM status 분리, code source)"`

### Task 2: claim_rid

**Files:** Modify `khala/rid.py`; Test `tests/test_claim_model.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
from khala.rid import claim_rid

def test_claim_rid_stable_and_prefixed():
    a = claim_rid("default", "associate-max-playlists")
    assert a == claim_rid("default", "associate-max-playlists")
    assert a.startswith("claim_") and ":" not in a
```

- [ ] **Step 2: 실패 확인** → FAIL
- [ ] **Step 3: 구현**

```python
# khala/rid.py 에 추가 (기존 편의함수 패턴: prefix 콜론 없음)
def claim_rid(tenant: str, claim_id: str) -> str:
    return make_rid("claim", tenant, claim_id)
```

- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat(claim): claim_rid"`

### Task 3: claims 테이블 + source_kind enum 확장

**Files:** Modify `init.sql`

- [ ] **Step 1: DDL 추가** (실제 CRM 컬럼 타입/제약 패턴을 documents 테이블에서 그대로 복제)

```sql
-- init.sql 끝에 추가
-- source_kind enum에 'code' 추가 (psql 자동커밋 → 다음 문장에서 사용 가능.
--   만약 init.sql을 BEGIN/COMMIT으로 감싼다면 이 ALTER를 별도 트랜잭션으로 분리할 것)
ALTER TYPE source_kind ADD VALUE IF NOT EXISTS 'code';

CREATE TABLE claims (
    -- CRM 공통 (documents와 동일 타입/기본값)
    rid             TEXT PRIMARY KEY,
    rtype           TEXT NOT NULL DEFAULT 'claim',
    tenant          TEXT NOT NULL DEFAULT 'default',
    classification  classification_level NOT NULL DEFAULT 'INTERNAL',
    owner           TEXT NOT NULL DEFAULT 'unknown',
    source_uri      TEXT NOT NULL DEFAULT '',          -- 코드 파일 경로(상대)
    source_version  TEXT NOT NULL DEFAULT '',
    source_kind     source_kind NOT NULL DEFAULT 'code',
    hash            TEXT NOT NULL DEFAULT '',          -- value_symbol_hash 스냅샷
    labels          TEXT[] DEFAULT '{}',
    is_quarantined  BOOLEAN NOT NULL DEFAULT false,
    quality_flags   TEXT[] DEFAULT '{}',               -- claim_code_drift 등
    status          resource_status NOT NULL DEFAULT 'active',   -- CRM 수명주기 (검증상태 아님)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    prov_pipeline   TEXT NOT NULL DEFAULT 'claim-v1',
    prov_inputs     TEXT[] DEFAULT '{}',
    prov_transform  TEXT NOT NULL DEFAULT '',
    -- claim 고유
    claim_id        TEXT NOT NULL,
    kind            TEXT NOT NULL,                      -- goal|invariant|requirement
    concepts        TEXT[] DEFAULT '{}',                -- 척추 entity name(정규화형) 참조
    statement       TEXT NOT NULL,
    value_source    TEXT,
    value_ref_kind  TEXT,
    criticality     TEXT NOT NULL DEFAULT 'peripheral',
    activity        TEXT NOT NULL DEFAULT 'active',
    claim_status    TEXT NOT NULL DEFAULT 'unverified', -- 검증상태 (CRM status와 분리)
    confidence      TEXT NOT NULL DEFAULT 'low',
    value_symbol_hash    TEXT,
    last_verified_commit TEXT,
    last_verified_at     TIMESTAMPTZ,
    CONSTRAINT chk_claim_rtype CHECK (rtype = 'claim'),
    CONSTRAINT uq_claim UNIQUE (tenant, claim_id)
);
CREATE INDEX idx_claims_concepts ON claims USING gin (concepts) WHERE status = 'active';
CREATE INDEX idx_claims_quality ON claims USING gin (quality_flags) WHERE status = 'active';
CREATE INDEX idx_claims_tenant_class ON claims (tenant, classification)
    WHERE status = 'active' AND is_quarantined = false;
```

- [ ] **Step 2: 적용 확인** — Run: `docker compose up -d khala-db && docker exec khala-db psql -U khala -d khala -f /docker-entrypoint-initdb.d/init.sql` (또는 재초기화) `&& docker exec khala-db psql -U khala -d khala -c "\d claims"` → claims 테이블 + `code` enum 값 확인

- [ ] **Step 3: 커밋** — `git commit -m "feat(claim): claims 테이블 + source_kind 'code' enum"`

### Task 4: 테스트 DB 정리 목록에 claims 등록

**Files:** Modify `tests/conftest.py`

- [ ] **Step 1: TRUNCATE 목록 수정** — `clean_db`의 TRUNCATE에 `claims` 추가:

```python
# tests/conftest.py — clean_db 내 TRUNCATE 문 수정
await conn.execute("""
    TRUNCATE evidence, edges, observed_edges, chunks, documents, entities, claims
    CASCADE
""")
```

- [ ] **Step 2: 확인** — (DB 환경에서) `KHALA_TEST_DB_URL` 설정 후 빈 통합테스트 1건이 claims TRUNCATE를 타는지 확인. 또한 **테스트 DB에 claims DDL이 적용**돼야 함 — `docker-compose.test.yml`의 init 스크립트(또는 마이그레이션)가 `init.sql`을 로드하는지 확인하고, 아니면 테스트 DB에도 Task 3 DDL을 적용하는 단계를 추가.
- [ ] **Step 3: 커밋** — `git commit -m "test(claim): clean_db TRUNCATE에 claims 추가"`

---

## Chunk 2: 코드 소스 값 추출

### Task 5: CodeValueResolver — 상수 값+hash 추출

**Files:** Create `khala/index/code_source.py`; Test `tests/test_code_source.py`; Fixture `tests/fixtures/PlaylistPolicy.java`

- [ ] **Step 1: 픽스처 + 실패 테스트**

```java
// tests/fixtures/PlaylistPolicy.java
public class PlaylistPolicy {
    // 준회원 최대 플레이리스트
    public static final int ASSOCIATE_MAX_PLAYLISTS = 5;
    public static final int  TRACK_TIME_LIMIT_SECONDS  =  360 ;
}
```

```python
# tests/test_code_source.py
from pathlib import Path
from khala.index.code_source import CodeValueResolver

FIX = Path(__file__).parent / "fixtures"

def test_reads_current_int_constant():
    res = CodeValueResolver(FIX).resolve("PlaylistPolicy.ASSOCIATE_MAX_PLAYLISTS")
    assert res.found and res.value == "5"
    assert res.symbol == "ASSOCIATE_MAX_PLAYLISTS"
    assert res.rel_path.endswith("PlaylistPolicy.java")
    assert res.symbol_hash

def test_tolerates_extra_whitespace():
    res = CodeValueResolver(FIX).resolve("PlaylistPolicy.TRACK_TIME_LIMIT_SECONDS")
    assert res.value == "360"

def test_hash_changes_with_value(tmp_path):
    f = tmp_path / "P.java"
    f.write_text("class P { public static final int X = 5; }")
    h1 = CodeValueResolver(tmp_path).resolve("P.X").symbol_hash
    f.write_text("class P { public static final int X = 10; }")
    h2 = CodeValueResolver(tmp_path).resolve("P.X").symbol_hash
    assert h1 != h2

def test_missing_symbol_not_found():
    assert CodeValueResolver(FIX).resolve("PlaylistPolicy.NOPE").found is False
```

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: 구현** (hash 입력에 **repo 상대경로 전체** 사용 → 동명파일 충돌 방지)

```python
# khala/index/code_source.py
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

@dataclass
class ResolvedValue:
    found: bool
    value: str | None = None
    rel_path: str | None = None
    symbol: str | None = None
    symbol_hash: str | None = None

class CodeValueResolver:
    """코드 상수의 *현재값*을 읽고 (상대경로+심볼) hash를 낸다.
    MVP: Java `static final` 상수. System decides — 파싱은 결정론, LLM 미개입."""

    def __init__(self, repo_path):
        self.repo_path = Path(repo_path)

    def resolve(self, source: str) -> ResolvedValue:
        _, _, symbol = source.rpartition(".")
        if not symbol:
            return ResolvedValue(found=False)
        pat = re.compile(r"static\s+final\s+\w+\s+" + re.escape(symbol) + r"\s*=\s*([^;]+);")
        for path in self.repo_path.rglob("*.java"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            m = pat.search(text)
            if m:
                value = m.group(1).strip()
                rel = str(path.relative_to(self.repo_path)).replace("\\", "/")
                symbol_hash = hashlib.sha256(
                    (rel + "::" + symbol + "::" + m.group(0)).encode("utf-8")
                ).hexdigest()[:12]
                return ResolvedValue(True, value, rel, symbol, symbol_hash)
        return ResolvedValue(found=False)
```

- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat(code-source): Java 상수 현재값+상대경로 심볼 hash"`

---

## Chunk 3: 저장 + 값조회

### Task 6: ClaimRepository (asyncpg, CRM 필터)

**Files:** Create `khala/claims/repository.py`; Test `tests/test_claim_integration.py`

- [ ] **Step 1: 실패 통합테스트** (integration 마커 필수)

```python
# tests/test_claim_integration.py
import pytest
from khala.models.claim import Claim
from khala.claims.repository import ClaimRepository

pytestmark = pytest.mark.integration   # KHALA_TEST_DB_URL 없으면 자동 skip

@pytest.mark.asyncio
async def test_upsert_and_find_by_concept(db_pool):
    repo = ClaimRepository(db_pool)
    c = Claim(claim_id="associate-max-playlists", kind="invariant",
              concepts=["준회원", "플레이리스트"], statement="준회원 최대 N개",
              value_source="PlaylistPolicy.ASSOCIATE_MAX_PLAYLISTS",
              value_ref_kind="code_constant", owner="@be",
              value_symbol_hash="abc123", last_verified_commit="deadbee")
    await repo.upsert(c)
    found = await repo.find_by_concept("준회원", tenant="default", clearance="INTERNAL")
    got = next(x for x in found if x.claim_id == "associate-max-playlists")
    assert got.value_source.endswith("ASSOCIATE_MAX_PLAYLISTS")
    assert got.value_symbol_hash == "abc123"     # 신선도용 hash 왕복 보존
    assert got.claim_status == "unverified"
```

- [ ] **Step 2: 실패 확인** → FAIL (또는 DB 없으면 skip — DB 환경에서 FAIL 확인)

- [ ] **Step 3: 구현** (asyncpg `$N`, `::classification_level` 캐스트, 전체 CRM 필터)

```python
# khala/claims/repository.py
from khala.models.claim import Claim

class ClaimRepository:
    def __init__(self, pool):
        self.pool = pool

    async def upsert(self, c: Claim) -> None:
        async with self.pool.acquire() as con:
            await con.execute(
                """
                INSERT INTO claims (
                    rid, rtype, tenant, owner, source_kind, source_uri, hash, status,
                    claim_id, kind, concepts, statement, value_source, value_ref_kind,
                    criticality, activity, claim_status, confidence,
                    value_symbol_hash, last_verified_commit)
                VALUES ($1,'claim',$2,$3,'code',$4,$5,'active',
                        $6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
                ON CONFLICT (rid) DO UPDATE SET
                    statement=EXCLUDED.statement, concepts=EXCLUDED.concepts,
                    value_source=EXCLUDED.value_source, value_ref_kind=EXCLUDED.value_ref_kind,
                    criticality=EXCLUDED.criticality, activity=EXCLUDED.activity,
                    claim_status=EXCLUDED.claim_status, confidence=EXCLUDED.confidence,
                    value_symbol_hash=EXCLUDED.value_symbol_hash,
                    last_verified_commit=EXCLUDED.last_verified_commit,
                    hash=EXCLUDED.hash, source_uri=EXCLUDED.source_uri, updated_at=now()
                """,
                c.rid, c.tenant, c.owner, c.source_uri, c.hash,
                c.claim_id, c.kind, c.concepts, c.statement, c.value_source,
                c.value_ref_kind, c.criticality, c.activity, c.claim_status,
                c.confidence, c.value_symbol_hash, c.last_verified_commit,
            )

    async def find_by_concept(self, concept: str, tenant: str, clearance: str) -> list[Claim]:
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                """
                SELECT rid, tenant, owner, source_uri, hash, claim_id, kind, concepts,
                       statement, value_source, value_ref_kind, criticality, activity,
                       claim_status, confidence, value_symbol_hash, last_verified_commit
                FROM claims
                WHERE $1 = ANY(concepts)
                  AND tenant = $2
                  AND classification <= $3::classification_level
                  AND is_quarantined = false
                  AND status = 'active'
                """,
                concept, tenant, clearance,
            )
        return [_row_to_claim(r) for r in rows]

def _row_to_claim(r) -> Claim:
    return Claim(
        rid=r["rid"], tenant=r["tenant"], owner=r["owner"], source_uri=r["source_uri"],
        hash=r["hash"], claim_id=r["claim_id"], kind=r["kind"],
        concepts=list(r["concepts"]), statement=r["statement"],
        value_source=r["value_source"], value_ref_kind=r["value_ref_kind"],
        criticality=r["criticality"], activity=r["activity"],
        claim_status=r["claim_status"], confidence=r["confidence"],
        value_symbol_hash=r["value_symbol_hash"], last_verified_commit=r["last_verified_commit"],
    )
```

> 주: `concept` 매칭은 `concepts`에 저장된 **정규화 entity name**과 일치해야 한다. 조회 입력도 `canonicalize_entity_name()` 경유 여부를 P0에서 확인하고, 척추 entity와 어긋나지 않게 통일. (MVP 시드는 한국어 원문 사용 — 정규화가 한국어를 변형하지 않는지 확인.)

- [ ] **Step 4: 통과 확인** (DB 환경) → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat(claim): ClaimRepository (asyncpg, CRM 필터, hash 왕복)"`

### Task 7: ValueQueryService — 현재값+신선도+드리프트

**Files:** Create `khala/claims/value_query.py`; Test `tests/test_value_query.py`

- [ ] **Step 1: 실패 테스트** (단위 — FakeRepo로 DB 불필요)

```python
# tests/test_value_query.py
from pathlib import Path
import pytest
from khala.claims.value_query import ValueQueryService
from khala.index.code_source import CodeValueResolver
from khala.models.claim import Claim

FIX = Path(__file__).parent / "fixtures"

class FakeRepo:
    def __init__(self, claims): self._c = claims
    async def find_by_concept(self, concept, tenant, clearance):
        return [c for c in self._c if concept in c.concepts]

def _claim(**kw):
    base = dict(claim_id="associate-max-playlists", kind="invariant", concepts=["준회원"],
                statement="준회원 최대 N개", value_source="PlaylistPolicy.ASSOCIATE_MAX_PLAYLISTS",
                value_ref_kind="code_constant", owner="@be")
    base.update(kw); return Claim(**base)

@pytest.mark.asyncio
async def test_live_value_high_confidence_fresh():
    svc = ValueQueryService(FakeRepo([_claim()]), CodeValueResolver(FIX))
    res = await svc.query_value("준회원", "default", "INTERNAL")
    assert res[0].value == "5" and res[0].confidence == "high" and res[0].fresh is True

@pytest.mark.asyncio
async def test_drift_noted_when_stored_hash_differs():
    svc = ValueQueryService(FakeRepo([_claim(value_symbol_hash="OLD")]), CodeValueResolver(FIX))
    res = await svc.query_value("준회원", "default", "INTERNAL")
    assert res[0].value == "5"            # 값 자체는 항상 현재값(결정론)
    assert res[0].drifted is True         # 저장 hash != 현재 hash
    assert "변경" in res[0].note

@pytest.mark.asyncio
async def test_missing_source_is_honest():
    svc = ValueQueryService(FakeRepo([_claim(value_source="Foo.BAR")]), CodeValueResolver(FIX))
    res = await svc.query_value("준회원", "default", "INTERNAL")
    assert res[0].value is None and res[0].confidence == "low"
```

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: 구현**

```python
# khala/claims/value_query.py
from dataclasses import dataclass

@dataclass
class ValueAnswer:
    claim_id: str
    statement: str
    value: str | None
    source: str | None
    confidence: str
    fresh: bool
    drifted: bool = False
    note: str = ""

class ValueQueryService:
    """concept → 매칭 claim의 현재값을 코드에서 재읽기.
    값 조회는 결정론(코드 상수) → confidence=high, 조회 시 재읽기 → fresh.
    저장 hash와 현재 hash가 다르면 drifted 표기(값 자체는 현재값으로 정확).
    소스 해석 실패 → 정직 표기(거짓말 금지)."""

    def __init__(self, repo, resolver):
        self.repo = repo
        self.resolver = resolver

    async def query_value(self, concept, tenant, clearance) -> list["ValueAnswer"]:
        out = []
        for c in await self.repo.find_by_concept(concept, tenant, clearance):
            if not c.value_source:
                out.append(ValueAnswer(c.claim_id, c.statement, None, None,
                                       c.confidence, False, note="value-bearing 아님"))
                continue
            r = self.resolver.resolve(c.value_source)
            if not r.found:
                out.append(ValueAnswer(c.claim_id, c.statement, None, c.value_source,
                                       "low", False, note="소스 심볼을 코드에서 찾지 못함"))
                continue
            drifted = bool(c.value_symbol_hash) and c.value_symbol_hash != r.symbol_hash
            note = "마지막 검증 이후 코드 변경됨(현재값은 정확)" if drifted else ""
            out.append(ValueAnswer(c.claim_id, c.statement, r.value, c.value_source,
                                   "high", True, drifted=drifted, note=note))
        return out
```

- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat(claim): ValueQueryService (현재값+신선도+드리프트 표기)"`

---

## Chunk 4: 표현 + 표면

### Task 8: 캘리브레이션 답변

**Files:** Create `khala/claims/answer.py`; Test `tests/test_claim_answer.py`

- [ ] **Step 1: 실패 테스트**

```python
# tests/test_claim_answer.py
from khala.claims.answer import format_value_answer
from khala.claims.value_query import ValueAnswer

def test_high_conf_states_value_and_cites_source():
    s = format_value_answer("준회원", [ValueAnswer("a", "준회원 최대 N개", "5",
        "PlaylistPolicy.ASSOCIATE_MAX_PLAYLISTS", "high", True)])
    assert "5" in s and "PlaylistPolicy.ASSOCIATE_MAX_PLAYLISTS" in s and "확실" in s

def test_drift_is_surfaced():
    s = format_value_answer("준회원", [ValueAnswer("a", "...", "10", "P.X", "high", True,
        drifted=True, note="마지막 검증 이후 코드 변경됨(현재값은 정확)")])
    assert "10" in s and "변경" in s

def test_unknown_is_not_fabricated():
    s = format_value_answer("x", [ValueAnswer("x", "...", None, "Foo.BAR", "low", False,
        note="소스 심볼을 코드에서 찾지 못함")])
    assert "찾지 못" in s and "확실" not in s
```

- [ ] **Step 2: 실패 확인** → FAIL
- [ ] **Step 3: 구현**

```python
# khala/claims/answer.py
from khala.claims.value_query import ValueAnswer

def format_value_answer(concept: str, answers: list[ValueAnswer]) -> str:
    if not answers:
        return f"'{concept}'에 등록된 값 claim이 없습니다. (모름 — 추측하지 않음)"
    lines = []
    for a in answers:
        if a.value is not None and a.confidence == "high" and a.fresh:
            base = f"- {a.statement}: **현재 {a.value}** (확실: 코드 상수 `{a.source}`, 조회 시점 기준)"
            if a.drifted:
                base += f" ⚠️ {a.note}"
            lines.append(base)
        elif a.value is None:
            lines.append(f"- {a.statement}: 값 확인 실패 — {a.note}. (확신 없음)")
        else:
            lines.append(f"- {a.statement}: {a.value} (신뢰 {a.confidence}, "
                         f"{'fresh' if a.fresh else 'stale'})")
    return "\n".join(lines)
```

- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat(claim): 캘리브레이션 답변(모르면 확신 안 함)"`

### Task 9: 시드 로더 + CLI

**Files:** Create `khala/claims/seed.py`, `claims.yaml`; Modify `khala/cli.py`, `config.yaml`

- [ ] **Step 1: 시드 + config**

```yaml
# claims.yaml
- claim_id: associate-max-playlists
  kind: invariant
  concepts: [준회원, 플레이리스트]
  statement: "준회원은 플레이리스트를 최대 N개 가질 수 있다"
  value_source: "PlaylistPolicy.ASSOCIATE_MAX_PLAYLISTS"
  value_ref_kind: code_constant
  criticality: core
  owner: "@backend-lead"
- claim_id: track-time-limit
  kind: invariant
  concepts: [파티룸, 재생곡]
  statement: "파티룸 재생곡은 최대 N초까지 재생된다"
  value_source: "PlaylistPolicy.TRACK_TIME_LIMIT_SECONDS"
  value_ref_kind: code_constant
  criticality: core
  owner: "@backend-lead"
```

```yaml
# config.yaml 에 추가
code_source:
  repo_path: "/path/to/pfplay-platform"   # 실제 pfplay 코드 checkout
```

- [ ] **Step 2: 시드 로더** (seed 시 resolver로 현재 hash를 스냅샷 → 이후 drift 판정 기준. owner 비-unknown 강제.)

```python
# khala/claims/seed.py
import yaml
from khala.models.claim import Claim
from khala.index.code_source import CodeValueResolver
from khala.claims.repository import ClaimRepository

async def seed_claims(yaml_path: str, repo: ClaimRepository, resolver: CodeValueResolver) -> int:
    items = yaml.safe_load(open(yaml_path, encoding="utf-8")) or []
    n = 0
    for it in items:
        if not it.get("owner") or it["owner"] == "unknown":
            raise ValueError(f"claim {it.get('claim_id')}: owner 필수(비-unknown)")  # 소유권=생존변수
        c = Claim(**it)
        if c.value_source:
            r = resolver.resolve(c.value_source)
            if r.found:
                c.value_symbol_hash = r.symbol_hash
                c.source_uri = r.rel_path
                c.hash = r.symbol_hash
        await repo.upsert(c)
        n += 1
    return n
```

- [ ] **Step 3: CLI 커맨드** (기존 Typer `app` + `_run(coro)`/`db.get_pool()`/`_load_config()` 패턴은 P0에서 확인 후 사용)

```python
# khala/cli.py 에 추가
@app.command("claim-seed")
def claim_seed(path: str = "claims.yaml"):
    """claims.yaml을 적재(현재 코드 hash 스냅샷 포함)."""
    print(f"{_run(_seed(path))}건 적재")

@app.command("claim-value")
def claim_value(concept: str):
    """개념의 도메인 값 claim 현재값 조회."""
    from khala.claims.answer import format_value_answer
    print(format_value_answer(concept, _run(_query(concept))))

# wiring 헬퍼 (기존 풀/config 패턴 사용)
async def _wire():
    cfg = _load_config()                       # 기존 함수
    pool = await db.get_pool()                 # 기존 함수
    from khala.claims.repository import ClaimRepository
    from khala.index.code_source import CodeValueResolver
    from khala.claims.value_query import ValueQueryService
    repo = ClaimRepository(pool)
    resolver = CodeValueResolver(cfg["code_source"]["repo_path"])
    return repo, resolver, ValueQueryService(repo, resolver)

async def _seed(path):
    from khala.claims.seed import seed_claims
    repo, resolver, _ = await _wire(); return await seed_claims(path, repo, resolver)

async def _query(concept):
    _, _, svc = await _wire(); return await svc.query_value(concept, "default", "INTERNAL")
```

- [ ] **Step 4: 수동 검증**

Run: `docker compose up -d && khala claim-seed ./claims.yaml && khala claim-value 준회원`
Expected: `- 준회원은 플레이리스트를 최대 N개 가질 수 있다: **현재 5** (확실: 코드 상수 PlaylistPolicy.ASSOCIATE_MAX_PLAYLISTS, 조회 시점 기준)`
(repo_path에 PlaylistPolicy.java가 있어야 함 — 없으면 테스트 픽스처 경로로 임시 검증.)

- [ ] **Step 5: 커밋** — `git commit -m "feat(claim): 시드 로더 + CLI claim-seed/claim-value"`

### Task 10: MCP 도구 `claim_value`

**Files:** Modify `khala/api.py`; Test `tests/test_claim_integration.py`

- [ ] **Step 1: 실패 e2e 테스트** (integration) — MCP 도구 `claim_value(concept="준회원")` 호출 → 답변에 "5" 포함.
- [ ] **Step 2: 실패 확인** → FAIL
- [ ] **Step 3: 구현** — 기존 MCP 6개 도구 등록 패턴 따라 `claim_value` 추가. 내부는 `_wire()` 동등 wiring → `format_value_answer` 반환. "System decides, LLM narrates": 값은 코드가 결정, LLM은 문자열을 사람말로 풀기만.
- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat(claim): MCP 도구 claim_value"`

---

## Chunk 5: 가치 검증 게이트

### Task 11: ★ 가치 검증 프로토콜 실행 (코드 아님 — 운영 마일스톤·게이트)

**참조:** `docs/superpowers/specs/2026-06-06-value-validation-protocol.md`

- [ ] **Step 1: 시드 확장** — pfplay 핵심 개념 8~10(entities.yaml) + value claim 5~10(claims.yaml), 실제 상수.
- [ ] **Step 2: 실제 질문 ≥10건 수집** (회의록/Slack, 날조 금지).
- [ ] **Step 3: 참가자 ≥3명 섭외** (도구 제작자 제외).
- [ ] **Step 4: 측정** — 프로토콜 §5 a~f. **2주 지속 사용**(신규성 편향 통제). miss율 별도 집계.
- [ ] **Step 5: 결정 게이트**
  - **정확도 실패(채택된 답이 코드와 불일치) → 즉시 중단** (가치 이전에 신뢰 붕괴 — 프로토콜 §2·§7).
  - 채택률 ≥80% + stale 적발 ≥1 + 정확도 100% → **GO**: boolean 불변식·전처리 단계 별도 계획 착수.
  - 채택률 미달 → reject 이유 분류(특히 H2형) → UX 문제면 1회 개선 후 재시도, H2형이면 H1 기각/중단.
- [ ] **Step 6: 결과 리포트** — `docs/superpowers/specs/2026-XX-validation-results.md` 작성 + 커밋.

---

## 범위 밖 (GO 후 별도 계획 — YAGNI + 리스크 선소거)

boolean 불변식 검증(enforcement ⓐⓑⓒ + ArchUnit no-bypass) · 기획문서→claim 전처리(LLM 추출+조작화 게이트+큐레이션) · requirement 반영도 · goal 타입+조작화 edge · 런타임/동적 값 어댑터 · Java 외 언어 추출기. **Task 11이 분기점.**
