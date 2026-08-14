"""감사 행에서 질의를 역산할 수 없다 (SPEC-nexus-audit-query-hash, approved 2026-08-14).

**무엇이 관측됐나.** `search_query_text` 는 질문을 평문으로 담고, `a2a_audit.query_sha256` 은
소금 없는 `sha256(query)` 였다. 그래서 평문 → 해시 재계산 → `principal` 로 이어지는 **결정적
경로**가 있었다. 마지막 홉은 통계가 아니라 정확 일치다.

**소금은 이것을 못 고친다** (SPEC §1.4). `sha256(tenant‖\\0‖q)` 는 테넌트를 아는 사람이면
누구나 다시 계산하고, 테넌트는 같은 표의 컬럼이다. 기준은 "결정적 함수를 저장하느냐" 가
아니라 **"재식별에 충분한 엔트로피를 남기느냐"** 다 — `query_len` 은 남는다(§3.2 결정 A).

**이 파일이 지키는 것**: 감사 기록 경로가 질의에서 유도된 값을 다시 흘리기 시작하면 빨간불.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.a2a import audit as A  # noqa: E402

_QUERY = "결제 서비스가 발행하는 토픽이 뭐야"


def _derivations(query: str, tenant: str) -> dict[str, str]:
    """이 질의에서 유도 가능한 값들. **하나라도 감사 행에 있으면 안 된다.**

    두 후보(무염·테넌트소금)만 보면 불변식보다 약한 검사가 된다 — 절단본도 함께 본다.
    이것도 전칭 증명은 아니다(SPEC I1 이 그렇게 적었다): 다른 다이제스트·정규화 후 해시는
    이 목록에 없다. 검사는 **알려진 유도값의 부재**까지만 말한다.
    """
    plain = hashlib.sha256(query.encode("utf-8")).hexdigest()
    salted = hashlib.sha256(tenant.encode("utf-8") + b"\x00" + query.encode("utf-8")).hexdigest()
    return {"sha256": plain, "tenant_salted": salted, "truncated": plain[:16]}


# ── I1 — 새 감사 행에 질의 유도값이 없다 ──────────────────────────────────────

def test_the_structlog_record_carries_no_value_derived_from_the_query(monkeypatch):
    seen: dict = {}

    def spy(event, **kw):
        seen.update({"event": event, **kw})
    monkeypatch.setattr(A.log, "info", spy)

    A.emit_audit(skill="search", query=_QUERY, principal="agent-1", tenant="default")

    blob = repr(sorted(seen.items()))
    for name, value in _derivations(_QUERY, "default").items():
        assert value not in blob, f"감사 기록에 {name} 이 남았다 — 평문에서 재계산 가능하다"
    assert _QUERY not in blob, "원문이 그대로 남았다"


def test_the_length_still_goes_in_because_that_is_the_decision():
    """§3.2 결정 A 는 **지문**을 뺀 것이지 감사 기록을 줄인 것이 아니다.

    `query_len` 도 질의의 결정적 함수다 — SPEC §1.4 가 "결정적 함수 금지" 라는 이지선다를
    스스로 반증하며 그렇게 적었다. 기준은 **엔트로피**이고, 길이 하나로는 질의를 못 되찾는다.
    """
    import inspect

    src = inspect.getsource(A.emit_audit)
    assert "query_len" in src, "길이까지 빼면 감사 기록이 줄어든다 (I3)"


def test_the_hashing_helper_is_gone(monkeypatch):
    """§3.3.2 — 함수를 남겨 두면 다음 사람이 다시 쓴다. 삭제 자체를 검사로 박는다."""
    assert not hasattr(A, "query_sha256"), (
        "질의 해시 헬퍼가 남아 있다 — 이 모듈에서 그 값을 만들 수단이 있으면 안 된다")


# ── I5 — 기록 함수의 회귀 그물 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_persisted_row_carries_no_derived_value(monkeypatch):
    """DB 로 나가는 인자에도 유도값이 없다. structlog 만 검사하면 절반이다."""
    sent: list = []

    async def spy_execute(sql, *args):
        sent.append((sql, args))
    monkeypatch.setattr(A.db, "has_pool", lambda: True)
    monkeypatch.setattr(A.db, "execute", spy_execute)
    monkeypatch.setattr(A.log, "info", lambda *a, **k: None)

    await A.record_audit(skill="search", query=_QUERY, principal="agent-1", tenant="default")

    assert sent, "감사 행이 DB 로 안 갔다"
    blob = repr(sent)
    for name, value in _derivations(_QUERY, "default").items():
        assert value not in blob, f"INSERT 인자에 {name} 이 실렸다"
    assert _QUERY not in blob


@pytest.mark.asyncio
async def test_the_audit_still_records_everything_else(monkeypatch):
    """§4 I3 — 지문을 빼도 감사 기록이 줄지 않는다."""
    sent: list = []

    async def spy_execute(sql, *args):
        sent.append(args)
    monkeypatch.setattr(A.db, "has_pool", lambda: True)
    monkeypatch.setattr(A.db, "execute", spy_execute)
    monkeypatch.setattr(A.log, "info", lambda *a, **k: None)

    await A.record_audit(skill="search", query=_QUERY, principal="agent-1", tenant="default",
                         clearance="INTERNAL", route="hybrid", evidence_count=3,
                         task_state="completed", denied=False, latency_ms=42)

    args = sent[0]
    for expected in ("search", "agent-1", "default", "INTERNAL", "hybrid", 3, "completed", 42):
        assert expected in args, f"{expected!r} 가 감사 행에서 사라졌다"
    assert len(_QUERY) in args, "query_len 이 사라졌다"


# ── §5.1 재식별 시험 — **양성 대조군이 검사를 증명한다** ───────────────────────

@pytest.mark.asyncio
async def test_the_net_goes_red_when_the_defect_is_put_back(monkeypatch):
    """**대조군.** 기록 경로에 결함을 일부러 되돌리면 위 검사가 빨간불이어야 한다.

    초안의 대조군은 "옛 방식 해시를 가진 행을 만든다" 였는데, 그러면 증명되는 것이
    *"탐지기가 내가 방금 심은 값을 찾는다"* 뿐이다(SPEC §5.1 의 경고). 그래서 여기서는
    **기록 함수 자체**가 유도값을 다시 흘리게 만들고, 그 상태에서 그물이 발화하는지 본다.
    """
    sent: list = []

    async def spy_execute(sql, *args):
        sent.append(args)

    real_emit = A.emit_audit

    def leaky_emit(*, skill, query, **kw):
        # 결함 재도입: 지문을 다시 계산해 기록에 흘린다.
        return real_emit(skill=skill + "|" + hashlib.sha256(query.encode()).hexdigest(),
                         query=query, **kw)

    monkeypatch.setattr(A.db, "has_pool", lambda: True)
    monkeypatch.setattr(A.db, "execute", spy_execute)
    captured: dict = {}
    monkeypatch.setattr(A.log, "info", lambda ev, **kw: captured.update(kw))
    monkeypatch.setattr(A, "emit_audit", leaky_emit)

    await A.record_audit(skill="search", query=_QUERY, principal="agent-1", tenant="default")

    blob = repr(sorted(captured.items()))
    leaked = _derivations(_QUERY, "default")["sha256"]
    assert leaked in blob, (
        "결함을 되돌렸는데 그물이 안 걸렸다 — 이 검사는 아무것도 지키지 않는다")
