"""ADR-0008 을 링크한 SPEC 은 backstop 기록을 갖는다 (ADR-0009 미결 항목 승계).

**ADR-0009 는 이 의무를 "감지 가능한 사건" 에 걸어 뒀다**:

> A mechanism that detects backstop events, or a declaration made after the fact —
> **The next SPEC that links ADR-0008** — a detectable event (`linked_adrs`), deliberately not
> "the next backstop event", since that is the thing nothing can detect

감지 가능한 사건으로 옮긴 것은 옳았다. 그런데 **그 감지를 아무것도 하지 않았다** — 2026-08-05
이후 ADR-0008 을 링크한 SPEC 이 여섯인데 `backstop:` 기록을 가진 것은 **0** 이었다(2026-08-14
전수 확인). 기록 형식은 `SPEC-nexus-retrieval-backstop-detector`(approved 2026-08-05)가
이미 정해 뒀고, 정해진 뒤 한 번도 쓰이지 않았다.

**이 파일은 판정을 만들지 않는다.** 판정은 디렉터의 것이고, 그 SPEC 자신이 기록해 둔 사고가
바로 그것이다 — *"an agent wrote `declared_by: LivingLikeKrillin` for a ruling the director had
never made; review caught it"*. 여기서 하는 일은 **빠진 자리를 세는 것**뿐이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPECS = ROOT / "specs"
DEBT = SPECS / "backstop-debt.yaml"

#: 기록 형식이 정해진 날 (`SPEC-nexus-retrieval-backstop-detector`). 그 전 SPEC 에는 소급하지
#: 않는다 — 없던 규약을 어겼다고 부를 수 없다.
CONVENTION_DATE = "2026-08-05"

sys.path.insert(0, str(ROOT / "nexus"))

#: 이 검사는 리포 루트의 `specs/` 를 읽는다. nexus 컨테이너에는 `nexus/` 만 마운트돼 있어
#: 거기서는 돌 수 없다 — CI(전체 체크아웃, `working-directory: nexus`)와 호스트에서 돈다.
#: `test_ci_applies_migrations.py` 가 `.github/` 를 읽는 것과 같은 사정이다.
pytestmark = pytest.mark.skipif(
    not SPECS.is_dir(), reason="리포 루트의 specs/ 가 없다 (컨테이너 마운트 밖)")


def _specs() -> list[tuple[str, dict, str]]:
    out = []
    for p in sorted(SPECS.glob("SPEC-*.md")):
        text = p.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        head, _, body = text[3:].partition("\n---")
        try:
            meta = yaml.safe_load(head) or {}
        except yaml.YAMLError:
            continue
        out.append((p.stem, meta, body))
    return out


def _linked_after_convention() -> list[tuple[str, dict, str]]:
    """ADR-0008 을 링크하고 규약 이후에 쓰인 SPEC — 의무가 걸리는 집합."""
    return [(n, m, b) for n, m, b in _specs()
            if "ADR-0008" in (m.get("linked_adrs") or [])
            and str(m.get("date", ""))[:10] >= CONVENTION_DATE]


def test_the_detectable_event_is_actually_detected():
    """의무가 걸린 SPEC 이 실제로 존재한다 — 0 이면 이 검사가 아무것도 안 지킨다."""
    assert _linked_after_convention(), (
        "ADR-0008 을 링크한 규약 이후 SPEC 이 하나도 없다 — 검사가 공회전 중이다")


def test_every_such_spec_carries_a_backstop_record_or_is_declared_debt():
    """기록이 있거나, **빚 목록에 이름이 있거나** 둘 중 하나여야 한다.

    빚 목록을 둔 이유: 여섯 건이 이미 기록 없이 승인됐고, 그 판정은 디렉터만 내릴 수 있다.
    검사를 그냥 빨간불로 두면 **상시 거짓 경보가 진짜 경보를 죽인다** — 인덱스 커버리지에서
    이미 그렇게 됐다(진짜 한 줄이 739줄에 묻혔다). 빚은 세어서 보이게 두고, **새로 늘지
    못하게** 막는 것이 이 검사의 일이다.
    """
    debt = set((yaml.safe_load(DEBT.read_text(encoding="utf-8")) or {}).get("undeclared", []))
    missing = [n for n, _, body in _linked_after_convention() if "\nbackstop:" not in body]
    unexpected = sorted(set(missing) - debt)

    assert not unexpected, (
        f"backstop 기록이 없고 빚 목록에도 없는 SPEC: {unexpected}\n"
        "ADR-0008 을 링크하는 SPEC 은 `backstop:` 기록을 갖거나, 왜 못 갖는지 빚 목록에 "
        "이름을 올려야 한다. **판정을 지어내서 채우지 말 것** — 디렉터의 서명이다.")


def test_the_debt_list_only_names_specs_that_really_lack_a_record():
    """빚 목록이 낡으면 그 자체가 거짓 경보다. 기록을 갖춘 SPEC 이 목록에 남아 있으면 실패."""
    debt = set((yaml.safe_load(DEBT.read_text(encoding="utf-8")) or {}).get("undeclared", []))
    have = {n for n, _, body in _linked_after_convention() if "\nbackstop:" in body}
    stale = sorted(debt & have)

    assert not stale, f"기록을 갖췄는데 빚 목록에 남아 있다 — 목록에서 지워라: {stale}"


def test_the_debt_list_is_closed_to_new_entries():
    """**빚은 줄기만 한다.** 새 SPEC 이 목록에 이름을 올려 검사를 피할 수 있으면 검사가 아니다."""
    doc = yaml.safe_load(DEBT.read_text(encoding="utf-8")) or {}
    assert doc.get("closed_at"), "빚 목록에 마감일이 없다"
    for name in doc.get("undeclared", []):
        meta = next((m for n, m, _ in _specs() if n == name), None)
        assert meta is not None, f"빚 목록에 없는 SPEC 이 적혀 있다: {name}"
        assert str(meta.get("date", ""))[:10] <= doc["closed_at"], (
            f"{name} 은 마감일 이후 SPEC 이다 — 빚 목록으로 검사를 피할 수 없다")


@pytest.mark.parametrize("field", ["reread", "ruling", "declared_by", "declared_at", "reason"])
def test_a_backstop_record_has_every_field_the_convention_named(field):
    """형식이 반쪽이면 기록이 아니다. `SPEC-nexus-retrieval-backstop-detector` 가 정한 필드들."""
    for name, _, body in _linked_after_convention():
        if "\nbackstop:" not in body:
            continue
        block = body.split("\nbackstop:", 1)[1].split("\n```", 1)[0]
        assert f"{field}:" in block, f"{name} 의 backstop 기록에 `{field}` 가 없다"
