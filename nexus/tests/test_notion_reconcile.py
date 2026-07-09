"""Notion 재조정(reconciliation)의 순수 로직 — DB/네트워크 없음.

SPEC-nexus-notion-reconciliation §3.1(root provenance) · §3.2(containment) · §3.5(safety).
"""

from __future__ import annotations

from nexus.ingest.sources.base import ConvertedDoc
from nexus.ingest.sources.notion import NotionSource
from nexus.ingest.sources.notion_importer import build_csf
from nexus.ingest.sources.notion_reconcile import (
    ScopeRow,
    notion_doc_rid,
    plan_reconcile,
)
from nexus.rid import doc_rid


class FakeForkedTreeClient:
    """두 root 가 한 페이지를 공유하는 트리.

        rootA → shared, onlyA
        rootB → shared
    """

    def __init__(self):
        self.blocks = type("B", (), {"children": self})()
        self.pages = type("P", (), {"retrieve": self._retrieve})()
        self.databases = type("D", (), {"query": self._query})()
        self._tree = {
            "rootA": [
                {"type": "child_page", "id": "shared"},
                {"type": "child_page", "id": "onlyA"},
            ],
            "rootB": [{"type": "child_page", "id": "shared"}],
            "shared": [],
            "onlyA": [],
        }

    def list(self, block_id, start_cursor=None):
        return {"results": self._tree.get(block_id, []), "has_more": False, "next_cursor": None}

    def _retrieve(self, page_id):
        return {"id": page_id, "url": f"https://notion.so/{page_id}",
                "last_edited_time": "2026-07-09T00:00:00Z"}

    def _query(self, database_id, start_cursor=None):
        return {"results": [], "has_more": False, "next_cursor": None}


# ── §3.1 root provenance ──────────────────────────────────────────────────────

def test_live_index_maps_each_page_to_every_root_that_reaches_it():
    src = NotionSource(client=FakeForkedTreeClient(), roots=["rootA", "rootB"], tenant="default")
    assert src.live_index() == {
        "rootA": {"rootA"},
        "onlyA": {"rootA"},
        "shared": {"rootA", "rootB"},  # 두 root 모두에서 도달
        "rootB": {"rootB"},
    }


def test_live_index_keys_match_live_ids():
    """live_index 는 live_ids 의 상위호환 — 열거 집합이 동일해야 한다."""
    src = NotionSource(client=FakeForkedTreeClient(), roots=["rootA", "rootB"], tenant="default")
    assert set(src.live_index()) == src.live_ids()


def test_build_csf_carries_source_roots_into_provenance():
    conv = ConvertedDoc(page_id="p1", markdown="# 제목\n본문", frontmatter={"title": "제목"},
                        image_count=0)
    csf = build_csf(conv, "p1", roots={"rootB", "rootA"})
    # 결정적 순서(정렬) — 같은 입력이 같은 prov_inputs 를 낳아야 멱등하다.
    assert csf["provenance"]["source_roots"] == ["rootA", "rootB"]


def test_build_csf_without_roots_omits_source_roots():
    """roots 미지정(기존 호출자) 이면 provenance 에 키가 생기지 않는다 — sink 가 prov_inputs 를 안 건드린다."""
    conv = ConvertedDoc(page_id="p1", markdown="본문", frontmatter={"title": "t"}, image_count=0)
    csf = build_csf(conv, "p1")
    assert "source_roots" not in csf["provenance"]


# ── rid 매핑 (sink 의 canonical uri 와 일치해야 함) ────────────────────────────

def test_notion_doc_rid_matches_sink_canonical_uri():
    assert notion_doc_rid("acme", "pg-1") == doc_rid("acme:ext-notion-pg-1.md")


# ── §3.3 prune / revive 집합 ──────────────────────────────────────────────────

def test_plan_prunes_active_docs_absent_from_live_set():
    scope = [ScopeRow(rid="d1", status="active"), ScopeRow(rid="d2", status="active")]
    plan = plan_reconcile(scope, live_rids={"d1"})
    assert plan.prune == ["d2"]
    assert plan.revive == []
    assert plan.refused is False


def test_plan_revives_soft_deleted_docs_present_in_live_set():
    scope = [ScopeRow(rid="d1", status="soft_deleted"), ScopeRow(rid="d2", status="soft_deleted")]
    plan = plan_reconcile(scope, live_rids={"d1"})
    assert plan.revive == ["d1"]
    assert plan.prune == []


def test_plan_never_touches_superseded_docs():
    """의도적으로 supersede 된 문서는 prune 대상도 revive 대상도 아니다."""
    scope = [ScopeRow(rid="gone", status="superseded"), ScopeRow(rid="live", status="superseded")]
    plan = plan_reconcile(scope, live_rids={"live"})
    assert plan.prune == []
    assert plan.revive == []


# ── §3.5 safety threshold ─────────────────────────────────────────────────────

def test_plan_refuses_when_prune_ratio_exceeds_threshold():
    """--roots 오타로 전부 사라진 것처럼 보이는 실행을 막는다."""
    scope = [ScopeRow(rid=f"d{i}", status="active") for i in range(4)]
    plan = plan_reconcile(scope, live_rids={"d0"}, threshold=0.5)  # 3/4 = 75%
    assert plan.refused is True
    assert plan.prune == ["d1", "d2", "d3"]  # 보고는 하되
    assert "75" in plan.reason or "0.75" in plan.reason


def test_plan_allows_prune_at_threshold_boundary():
    scope = [ScopeRow(rid="d0", status="active"), ScopeRow(rid="d1", status="active")]
    plan = plan_reconcile(scope, live_rids={"d0"}, threshold=0.5)  # 1/2 = 50%, not > 50%
    assert plan.refused is False
    assert plan.prune == ["d1"]


def test_plan_force_overrides_refusal():
    scope = [ScopeRow(rid=f"d{i}", status="active") for i in range(4)]
    plan = plan_reconcile(scope, live_rids=set(), threshold=0.5, force=True)
    assert plan.refused is False
    assert plan.prune == ["d0", "d1", "d2", "d3"]


def test_plan_empty_scope_is_not_a_refusal():
    """첫 실행(아직 prov_inputs 백필 전)은 scope 가 비어 있다 — 0/0 을 100% 로 읽으면 안 된다."""
    plan = plan_reconcile([], live_rids={"whatever"})
    assert plan.refused is False
    assert plan.prune == []
    assert plan.revive == []


# ── import_notion 배선 (§3.3 순서: 적재 → 재조정) ─────────────────────────────

class _IndexedSource:
    """live_index 를 제공하는 페이크 소스."""

    def __init__(self, index, edits=None):
        self._index, self._edits = index, edits or {}

    def live_index(self):
        return self._index

    def live_ids(self):
        return set(self._index)

    def page_ref(self, pid):
        le = self._edits.get(pid, "2026-07-09T00:00:00Z")
        return type("R", (), {"id": pid, "url": f"u/{pid}", "last_edited": le})()

    def fetch_markdown(self, ref):
        return ConvertedDoc(page_id=ref.id, markdown=f"# {ref.id}\n본문",
                            frontmatter={"title": ref.id}, image_count=0)


class _Outcome:
    def __init__(self, rid, idempotent=False):
        self.resource_rid, self.idempotent_hit = rid, idempotent


async def test_import_notion_tags_each_page_with_the_roots_that_reach_it():
    from nexus.ingest.sources.notion_importer import import_notion

    seen: dict[str, list[str]] = {}

    async def fake_ingest(csf, tenant):
        seen[csf["provenance"]["source_id"]] = csf["provenance"].get("source_roots", [])
        return _Outcome(rid=f"rid-{csf['provenance']['source_id']}")

    src = _IndexedSource({"shared": {"rootB", "rootA"}, "onlyA": {"rootA"}})
    await import_notion(src, "acme", fake_ingest)

    assert seen["shared"] == ["rootA", "rootB"]  # 정렬 — 멱등
    assert seen["onlyA"] == ["rootA"]


async def test_import_notion_reconciles_after_ingest_with_full_live_set():
    from nexus.ingest.sources.notion_importer import import_notion

    order: list[str] = []
    captured: dict = {}

    async def fake_ingest(csf, tenant):
        order.append("ingest")
        return _Outcome(rid="r")

    async def fake_reconcile(tenant, walked_roots, live_by_rid):
        order.append("reconcile")
        captured.update(tenant=tenant, roots=walked_roots, live=set(live_by_rid))
        return type("O", (), {"pruned": 2, "revived": 1, "refused": False, "reason": ""})()

    src = _IndexedSource({"p1": {"rootA"}, "p2": {"rootA"}})
    report = await import_notion(src, "acme", fake_ingest, reconcile_fn=fake_reconcile)

    assert order == ["ingest", "ingest", "reconcile"]  # 재조정은 반드시 적재 뒤
    assert captured["roots"] == {"rootA"}
    assert captured["live"] == {notion_doc_rid("acme", "p1"), notion_doc_rid("acme", "p2")}
    assert report.pruned == 2
    assert report.revived == 1


async def test_import_notion_without_reconcile_fn_changes_nothing():
    """기존 호출자(재조정 미사용)의 동작은 그대로다."""
    from nexus.ingest.sources.notion_importer import import_notion

    async def fake_ingest(csf, tenant):
        return _Outcome(rid="r")

    report = await import_notion(_IndexedSource({"p1": {"rootA"}}), "acme", fake_ingest)
    assert report.pruned == 0
    assert report.revived == 0
    assert report.refused is False


# ── I-009: page id 표기 정규화 ────────────────────────────────────────────────

class _HexTreeClient:
    """API 는 대시 포함 소문자 id 를 준다. 사용자는 Notion URL 에서 대시 없는 id 를 복사한다."""

    ROOT_DASHED = "2740c71b-b9dc-80ef-b43a-ea3676e632c8"
    CHILD_DASHED = "29f0c71b-b9dc-8094-84ca-fc0c416a90e2"

    def __init__(self):
        self.blocks = type("B", (), {"children": self})()
        self.pages = type("P", (), {"retrieve": self._retrieve})()
        self.databases = type("D", (), {"query": self._query})()

    def list(self, block_id, start_cursor=None):
        kids = ([{"type": "child_page", "id": self.CHILD_DASHED}]
                if block_id == self.ROOT_DASHED else [])
        return {"results": kids, "has_more": False, "next_cursor": None}

    def _retrieve(self, page_id):
        return {"id": page_id, "url": "u", "last_edited_time": "2026-07-09T00:00:00Z"}

    def _query(self, database_id, start_cursor=None):
        return {"results": [], "has_more": False, "next_cursor": None}


def test_undashed_root_id_is_canonicalised_to_the_api_form():
    """--roots 에 URL 형식(대시 없음)을 줘도 API 가 주는 대시 형식과 같은 페이지로 취급해야 한다.

    아니면 루트 페이지가 다른 doc rid 로 중복 적재되고, walked_roots 표기가 어긋나
    containment 술어가 조용히 빗나간다.
    """
    undashed = _HexTreeClient.ROOT_DASHED.replace("-", "").upper()
    src = NotionSource(client=_HexTreeClient(), roots=[undashed], tenant="default")
    index = src.live_index()
    assert set(index) == {_HexTreeClient.ROOT_DASHED, _HexTreeClient.CHILD_DASHED}
    # root 귀속도 정규화된 형태여야 한다
    assert index[_HexTreeClient.CHILD_DASHED] == {_HexTreeClient.ROOT_DASHED}


def test_non_uuid_root_strings_are_left_alone():
    """테스트 픽스처나 비-UUID id 를 망가뜨리지 않는다."""
    src = NotionSource(client=FakeForkedTreeClient(), roots=["rootA"], tenant="default")
    assert "rootA" in src.live_index()


async def test_reconcile_sees_full_live_set_even_with_since_watermark():
    """--since 는 무엇을 '적재'할지만 좁힌다. 무엇이 '살아있는지'는 전체 열거가 정한다."""
    from nexus.ingest.sources.notion_importer import import_notion

    captured: dict = {}

    async def fake_ingest(csf, tenant):
        return _Outcome(rid="r")

    async def fake_reconcile(tenant, walked_roots, live_by_rid):
        captured["live"] = set(live_by_rid)
        return type("O", (), {"pruned": 0, "revived": 0, "refused": False, "reason": ""})()

    # p_old 는 since 이전 → 적재 스킵. 그래도 live 집합에는 있어야 한다.
    src = _IndexedSource(
        {"p_old": {"rootA"}, "p_new": {"rootA"}},
        edits={"p_old": "2026-01-01T00:00:00Z", "p_new": "2026-07-09T00:00:00Z"},
    )
    report = await import_notion(src, "acme", fake_ingest, since="2026-06-01T00:00:00Z",
                                 reconcile_fn=fake_reconcile)

    assert report.ingested == 1  # p_new 만 적재
    assert captured["live"] == {notion_doc_rid("acme", "p_old"), notion_doc_rid("acme", "p_new")}
