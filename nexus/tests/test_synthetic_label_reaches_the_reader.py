"""합성 표식이 **읽는 사람 앞까지** 오는가 — hop 을 이름이 아니라 수로 센다.

⛔ **표식은 마지막 hop 에서만 가치가 생긴다.** 문서 행에 `synthetic` 을 달아 두고 근거에 안
실으면, 지어낸 절차가 실제 운영 문서와 똑같은 얼굴로 인용된다. 검색이 잘될수록 나쁜 종류의
결함이다 — 정확하게 찾아와서 정확하게 틀린다. `provenance_tier` 가 hop 여섯을 다 통과해야
하는 것과 같은 논증이고(ADR-0010 §4 *"추출 안 하느니만 못하다"*), 그 표식은 실제로 한 hop 이
벗겨져 있었던 적이 있다.

**그래서 여기서는 자리를 이름으로 나열하지 않는다.** `SearchHit` 을 만드는 자리가 셋이고 그
행을 뜨는 SELECT 가 셋인데, 새 자리가 생겼을 때 목록에 손으로 더해야 하는 검사는 더해지지
않는다. 수를 세고, 세어진 것 전부가 표식을 싣는지 본다.
"""

from __future__ import annotations

import pathlib
import re

from nexus.labels import EXTERNAL_LABEL, SYNTHETIC_LABEL
from nexus.search.hybrid import SearchHit

_SRC = pathlib.Path(__file__).resolve().parents[1] / "nexus"
_ENRICH = ["search/hybrid.py", "search/section_fill.py"]
_BUILD = ["search/hybrid.py", "search/reconcile.py"]


def _text(rel: str) -> str:
    return (_SRC / rel).read_text(encoding="utf-8")


# ── 표식 자체 ──────────────────────────────────────────────────────────────

def test_the_labels_live_in_one_place():
    """⛔ 라벨이 둘이 되면서 선언도 둘이 될 뻔했다. `ingest` 와 `a2a` 는 서로를 못 끌어오므로
    의존 없는 최상위 모듈이 유일한 자리다."""
    assert SYNTHETIC_LABEL == "synthetic"
    assert EXTERNAL_LABEL == "external_spec"
    from nexus.ingest.external_metadata import EXTERNAL_LABEL as reexported
    assert reexported is EXTERNAL_LABEL, "재수출이 사본이 됐다"


def test_a_label_is_not_a_clearance():
    """등급으로 가리는 것은 합성이라고 말하는 것이 아니다. 두 어휘가 안 섞이는지 본다."""
    from nexus.auth import clearance
    levels = {v for v in vars(clearance).values() if isinstance(v, str)}
    assert SYNTHETIC_LABEL not in levels


# ── hop 을 수로 센다 ───────────────────────────────────────────────────────

def test_every_enrichment_query_selects_the_labels():
    """행을 안 떠 오면 뒤의 모든 hop 이 빈 값을 나른다 — 그리고 그건 "표식 없음" 으로 읽힌다."""
    found = 0
    for rel in _ENRICH:
        src = _text(rel)
        # 문서 별칭에서 뜨는 보강 SELECT 는 `d.n_images` 를 함께 뜬다 — 그것을 자리 표시로 쓴다.
        n_img = len(re.findall(r"coalesce\(d\.n_images", src))
        n_lab = len(re.findall(r"coalesce\(d\.labels", src))
        assert n_lab == n_img, f"{rel}: 보강 SELECT {n_img}개 중 {n_lab}개만 표식을 뜬다"
        found += n_lab
    assert found >= 3, f"보강 SELECT 를 {found}개만 찾았다 — 찾는 규칙이 낡았는가"


def test_every_hit_construction_carries_the_labels():
    """⛔ 새 구성 자리가 생기면 여기서 붉어져야 한다. 이름 목록이면 안 더해지고 조용히 샌다."""
    for rel in _BUILD:
        src = _text(rel)
        # 선언(`class SearchHit:`)과 import 에는 괄호가 없으니 호출만 세어진다.
        built = len(re.findall(r"SearchHit\(", src))
        carried = len(re.findall(r"labels=list\(", src))
        assert carried == built, f"{rel}: SearchHit 구성 {built}곳 중 {carried}곳만 표식을 싣는다"


def test_the_evidence_snippet_carries_it_too():
    """검색 결과와 **답변 근거**는 다른 객체다. 여기서 끊기면 답변만 표식을 잃는다."""
    from nexus.search.evidence_packet import EvidenceSnippet

    assert "labels" in EvidenceSnippet.__dataclass_fields__
    assert 'labels=list(getattr(hit, "labels"' in _text("search/evidence_packet.py")


# ── 읽는 사람이 보는 자리 ──────────────────────────────────────────────────

def test_the_search_payload_says_synthetic():
    from nexus.api import _search_hit_to_dict

    hit = SearchHit(rid="c1", doc_rid="d1", labels=[SYNTHETIC_LABEL])
    out = _search_hit_to_dict(hit)
    assert out["synthetic"] is True
    assert SYNTHETIC_LABEL in out["labels"]


def test_a_real_document_is_not_marked():
    """대조군. 실제 자료에 표식이 붙으면 표식은 곧 무시된다."""
    out = __import__("nexus.api", fromlist=["_search_hit_to_dict"])._search_hit_to_dict(
        SearchHit(rid="c1", doc_rid="d1", labels=[EXTERNAL_LABEL]))
    assert out["synthetic"] is False
    assert out["labels"] == [EXTERNAL_LABEL], "다른 표식을 잃어버리면 안 된다"


def test_a_hit_with_no_labels_is_not_marked():
    out = __import__("nexus.api", fromlist=["_search_hit_to_dict"])._search_hit_to_dict(
        SearchHit(rid="c1", doc_rid="d1"))
    assert out["synthetic"] is False and out["labels"] == []


def test_the_agent_surface_marks_it():
    from nexus.mcp import server

    assert server._synthetic_mark({"synthetic": True}).strip()
    assert server._synthetic_mark({"synthetic": False}) == ""
    assert server._synthetic_mark({}) == "", "표식 없는 행에 글자를 붙이면 안 된다"
