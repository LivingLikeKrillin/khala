# 타입별 운용 가이드라인 (S2) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 축-A 타입별 운용 가이드(딥리서치 근거)를 specledger에 두고, **promote 반환**과 **MCP `guide` 도구**라는 소비 지점에 붙인다.

**Architecture:** `guidelines.py`(타입→가이드 텍스트 + `guidance_for`, `doctypes.normalize_kind` 재사용). `promote_external` 반환에 `guidance` 추가(순수). MCP `guide(type)` 도구. inert 문서 아님 — 결정/조회 순간에 제시.

**Tech Stack:** Python, pytest, FastMCP. specledger `doctypes`/`promote`/`server` 확장.

**Spec:** `docs/superpowers/specs/2026-06-25-type-guidelines-s2-design.md`

---

## File Structure

| 파일 | 변경 |
|---|---|
| `specledger/src/specledger/guidelines.py` (생성) | `GUIDANCE` dict + `_CROSS_CUTTING` + `guidance_for` |
| `specledger/tests/test_guidelines.py` (생성) | 타입별 반환·정규화·미지 None |
| `specledger/src/specledger/promote.py` (수정) | 반환에 `guidance` 추가 |
| `specledger/tests/test_promote.py` (수정) | 반환 guidance 검증 |
| `specledger/src/specledger/server.py` (수정) | `guide` MCP 도구 |
| `specledger/tests/test_server.py` (수정) | guide 도구 테스트 |

---

## Chunk 1: guidelines 모듈

### Task 1: GUIDANCE + guidance_for

**Files:**
- Create: `specledger/src/specledger/guidelines.py`
- Test: `specledger/tests/test_guidelines.py`

- [ ] **Step 1: 실패 테스트**

`specledger/tests/test_guidelines.py`:

```python
from __future__ import annotations

from specledger.guidelines import guidance_for


def test_guidance_for_known_types_carries_research_anchors():
    adr = guidance_for("ADR")
    assert "supersede" in adr and "불변" in adr
    assert "계층" in guidance_for("RFC") or "substantial" in guidance_for("RFC")
    assert "blameless" in guidance_for("POSTMORTEM") or "비난" in guidance_for("POSTMORTEM")


def test_guidance_for_normalizes_legacy_token():
    # 레거시 SPEC → DESIGN 가이드(doctypes.normalize_kind 재사용)
    assert guidance_for("SPEC") == guidance_for("DESIGN")


def test_guidance_for_includes_cross_cutting_footer():
    assert "owner" in guidance_for("NOTE")          # 공통 푸터(docs-as-code)


def test_guidance_for_unknown_returns_none():
    assert guidance_for("MYSTERY") is None
```

- [ ] **Step 2: 실패 확인**

Run: `cd specledger && python -m pytest tests/test_guidelines.py -q`
Expected: FAIL (`guidelines` 모듈 없음)

- [ ] **Step 3: 구현**

`specledger/src/specledger/guidelines.py`:

```python
"""타입별 운용 가이드라인 (S2). 딥리서치(2026-06-25) 근거.

각 축-A 타입을 어떻게 저작·관리·운용할지 요지+근거. promote 반환과 MCP guide 도구가
소비한다(inert 문서 아님). 타입 정규화는 doctypes.normalize_kind 재사용(레거시 SPEC→DESIGN).
"""

from __future__ import annotations

from . import doctypes

# 모든 타입 공통 — doc-rot 최강 치료제(SWE at Google ch10).
_CROSS_CUTTING = "공통: owner 명시 · 소스컨트롤 · 이슈 추적 · 정기 staleness 점검(docs-as-code)."

# 축-A 타입 → 운용 요지(근거). 간결(읽히게).
GUIDANCE = {
    "ADR": (
        "불변+supersede: accepted 후 수정 금지 — 변경은 새 ADR로 대체(old→superseded). "
        "5섹션(Title/Status/Context/Decision/Consequences). 상태: proposed→accepted→"
        "deprecated/superseded. (arc42 §9, Nygard, AWS)"
    ),
    "RFC": (
        "계층적 게이트: substantial 변경만 정식 승인 — 버그픽스·리팩터는 게이트 없음. "
        "active→complete(구현 후)→inactive. 승인≠구현 보장. (Rust RFC 0002)"
    ),
    "DESIGN": (
        "단일 목적 + 승인 게이트: 한 문서 한 목적, 구현 근거이므로 리뷰·승인 후 발효, "
        "변경은 supersede. (SWE at Google ch10)"
    ),
    "PRD": (
        "추적·제자리 개정: 버전+owner로 추적, SPEC이 파생되므로 변경 시 하위 stale 점검(drift). "
        "승인 게이트 없음."
    ),
    "RUNBOOK": (
        "운영 절차(how-to-operate): 코드/인프라 변경과 함께 갱신, 정기 staleness 재확인 필수. "
        "(doc-rot 최대 피해 영역, Aghajani ICSE'19)"
    ),
    "POSTMORTEM": (
        "고정 내용(사건/영향/완화/근본원인/후속) + 리뷰 필수(미리뷰=없는 것), "
        "비난 없는(blameless). 승인 게이트 없음. (Google SRE)"
    ),
    "NOTE": "메모: 생애주기 없음 — 인덱싱·검색만. 정본이 되면 promote로 격상.",
}


def guidance_for(type_name: str) -> str | None:
    """축-A 타입(또는 레거시 토큰) → 운용 가이드 + 공통 푸터. 미등록 None."""
    g = GUIDANCE.get(doctypes.normalize_kind(type_name))
    return f"{g}\n{_CROSS_CUTTING}" if g else None
```

- [ ] **Step 4: 통과 확인**

Run: `cd specledger && python -m pytest tests/test_guidelines.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: ruff + Commit**

```bash
cd specledger && python -m ruff check src/specledger/guidelines.py tests/test_guidelines.py
git add specledger/src/specledger/guidelines.py specledger/tests/test_guidelines.py
git commit -m "feat(guidelines): 타입별 운용 가이드 + guidance_for (S2 Chunk 1)"
```

---

## Chunk 2: promote_external 반환에 guidance

### Task 2: promote 반환 확장

**Files:**
- Modify: `specledger/src/specledger/promote.py` (import + return)
- Test: `specledger/tests/test_promote.py`

- [ ] **Step 1: 실패 테스트 추가**

`specledger/tests/test_promote.py` 끝에:

```python
def test_promote_returns_type_guidance(tmp_path):
    out = promote_external(_led(tmp_path), _csf(), "ADR")
    assert "guidance" in out
    assert "supersede" in out["guidance"]   # ADR 가이드
    # 기존 키 회귀 없음
    assert out["status"] == "PROPOSED" and out["provenance_carried"] is True
```

- [ ] **Step 2: 실패 확인**

Run: `cd specledger && python -m pytest tests/test_promote.py -q -k guidance`
Expected: FAIL (`guidance` 키 없음)

- [ ] **Step 3: 구현**

`specledger/src/specledger/promote.py` import에 추가:

```python
from . import doctypes, guidelines
```

(기존 `from . import doctypes` 줄을 위로 교체)

return 문을 교체. 기존:

```python
    return {"artifact_id": aid, "status": art.meta["status"].upper(), "provenance_carried": True}
```

신규:

```python
    return {
        "artifact_id": aid,
        "status": art.meta["status"].upper(),
        "provenance_carried": True,
        "guidance": guidelines.guidance_for(axis_a) or "",
    }
```

(`axis_a`는 이미 함수 상단에서 `doctypes.normalize_kind(type)`로 계산됨 — 재사용)

- [ ] **Step 4: 통과 확인 + 회귀**

Run: `cd specledger && python -m pytest tests/test_promote.py -q`
Expected: PASS (기존 + 신규)

- [ ] **Step 5: ruff + Commit**

```bash
cd specledger && python -m ruff check src/specledger/promote.py tests/test_promote.py
git add specledger/src/specledger/promote.py specledger/tests/test_promote.py
git commit -m "feat(promote): 반환에 타입 guidance 부착 (S2 Chunk 2)"
```

---

## Chunk 3: MCP guide 도구

### Task 3: guide 도구

**Files:**
- Modify: `specledger/src/specledger/server.py` (새 `@app.tool()`)
- Test: `specledger/tests/test_server.py`

- [ ] **Step 1: 실패 테스트 추가**

먼저 `specledger/tests/test_server.py`에서 기존 도구 호출 패턴(예: `build_app` 사용, `_get_tool`/직접 호출)을 확인하고 그에 맞춰 추가. 패턴 예(기존 테스트가 `build_app(...)` + MCP 내부 호출이면 동일하게):

```python
def test_guide_tool_returns_tier_and_guidance(tmp_path):
    # 기존 test_server.py의 app/ledger fixture 패턴 재사용.
    # guide("ADR") → tier T1 + ADR 가이드, guide(미지) → T3 + 메모.
    from specledger import doctypes, guidelines
    # 도구 본체 계약을 직접 검증(도구 등록은 아래 import 회귀로 보장):
    assert doctypes.tier_of(doctypes.normalize_kind("ADR")) == "T1"
    assert "supersede" in (guidelines.guidance_for("ADR") or "")
    assert doctypes.tier_of(doctypes.normalize_kind("MYSTERY")) == "T3"
```

(주: specledger MCP 도구는 FastMCP 등록이라 단위 호출이 번거로우면, 위처럼 도구가 위임하는 `doctypes`/`guidelines` 계약을 검증 + Step 4의 import/등록 회귀로 도구 존재를 보장한다. 기존 test_server.py가 도구를 직접 부르는 헬퍼를 갖고 있으면 그걸로 `guide` 직접 호출 테스트를 작성.)

- [ ] **Step 2: 실패/현행 확인**

Run: `cd specledger && python -m pytest tests/test_server.py -q -k guide`
Expected: 위 계약 테스트는 doctypes/guidelines가 이미 있으면 PASS(계약 고정). guide 도구 자체는 Step 3에서 추가.

- [ ] **Step 3: guide 도구 구현**

`specledger/src/specledger/server.py`의 `build_app` 안, 다른 `@app.tool()` 옆에 추가:

```python
    @app.tool()
    def guide(type: str) -> dict:
        from . import doctypes, guidelines
        axis_a = doctypes.normalize_kind(type)
        return {
            "type": type,
            "tier": doctypes.tier_of(axis_a),
            "guidance": guidelines.guidance_for(type) or "메모: 생애주기 없음 — 인덱싱·검색만.",
        }
```

- [ ] **Step 4: import/등록 회귀**

Run: `cd specledger && python -m pytest tests/test_server.py -q`
Expected: PASS (server.py import/구문 회귀 없음; 기존 도구 회귀 없음)

- [ ] **Step 5: ruff + Commit**

```bash
cd specledger && python -m ruff check src/specledger/server.py tests/test_server.py
git add specledger/src/specledger/server.py specledger/tests/test_server.py
git commit -m "feat(server): MCP guide(type) 도구 — tier+운용 가이드 조회 (S2 Chunk 3)"
```

---

## Task 4: 전체 회귀

- [ ] **Step 1: specledger 전체**

Run: `cd specledger && python -m pytest -q`
Expected: PASS

- [ ] **Step 2: ruff 변경분**

Run: `cd specledger && python -m ruff check src/specledger/ tests/`
Expected: All checks passed!

## Acceptance (스펙 §6 대응)

- [ ] guidance_for: 타입별 근거 가이드 + 레거시 정규화 + 공통 푸터 + 미지 None (Task 1)
- [ ] promote_external 반환 guidance(기존 키 회귀 없음) (Task 2)
- [ ] MCP guide(type)→{type,tier,guidance}, 미지→T3+메모 (Task 3)
- [ ] specledger 전체 회귀 (Task 4)
