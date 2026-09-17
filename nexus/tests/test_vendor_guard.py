"""벤더 원문을 막되 **우리 조사 노트는 통과시키는가.**

⛔ **오탐이 이 검사의 진짜 위험이다.** 벤더 이름으로 거르면 지켜야 할 것을 막는다 — 우리
조사 노트는 벤더 이름과 심볼과 해시로 가득하고, 그게 그 노트의 존재 이유다(원문 대신 심볼과
해시만 남긴다는 규율). 그래서 보는 것은 이름이 아니라 **자기 자신에 대한 권리 주장** 하나다.

**실측 2026-09-18.** 실물 573편에 돌려 발동 0건 — picasso `docs/` 35편, picasso 최상위 11편,
khala 전체 `.md` 527편. 그중 `docs/vendors/orbit.md` 는 Boston Dynamics 의 OpenAPI 를 심볼
323개까지 분석하면서 권리 주장은 한 줄도 없다. 아래 `_NOTE` 가 그 문서의 모양이다.

⚠ **완전하지 않다는 것도 검사한다** — 권리 표시를 지우고 붙여 넣은 원문은 통과한다. 그
한계를 모듈이 적어 두고, 여기서는 그 문장이 남아 있는지 본다. 한계를 적어 두지 않으면 다음
사람이 이 검사를 실제보다 넓게 믿는다.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from nexus.ingest.vendor_guard import (
    VendorOriginalRefused,
    refuse_if_vendor_original,
    rights_assertions,
)

#: 우리 조사 노트의 모양 — 벤더 이름·심볼·해시는 있고 권리 주장은 없다.
_NOTE = """# Boston Dynamics Orbit — 벤더 API 사양 분석 및 측정 노트

- 측정 대상: Orbit Web API 공식 게시본 (`openapi: "3.0.1"`, `info.version: "5.0.0"`)
- 아티팩트 해시: `sha256=7563e16e836f3c7829e5258f45ef0e0a2a484b8a93bce8f2bed0ed3a2e086e80`

저장소 내 벤더 원문 바이너리 배제 원칙에 따라 심볼 명칭과 해시값만을 기록 관리합니다.
공식 심볼 323개를 추출해 `vendor-manifest.txt` 에 체크인했습니다.
"""

_ORIGINALS = [
    ("표지의 저작권", "Spot SDK Reference\n\nCopyright 2026 Vendor, Inc. All rights reserved."),
    ("기밀 표시", "Web API\n\nPROPRIETARY AND CONFIDENTIAL\n\nEndpoints follow."),
    ("저작권 기호", "G1 Manual\n\n© 2026 Vendor Robotics"),
    ("SDK 라이선스 헤더", "Redistribution and use in source and binary forms, with or without"),
]


# ── 막아야 할 것 ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,text", _ORIGINALS, ids=[n for n, _ in _ORIGINALS])
def test_a_rights_assertion_is_refused(name, text):
    with pytest.raises(VendorOriginalRefused) as ei:
        refuse_if_vendor_original("vendor/manual.md", text)
    assert ei.value.found, "무엇 때문에 막혔는지 말하지 않으면 고칠 수 없다"
    assert "심볼명과 해시" in str(ei.value), "대신 무엇을 넣어야 하는지가 메시지에 있어야 한다"


def test_the_refusal_names_the_file():
    with pytest.raises(VendorOriginalRefused) as ei:
        refuse_if_vendor_original("docs/vendors/manual.md", _ORIGINALS[0][1])
    assert "docs/vendors/manual.md" in str(ei.value)


# ── 통과시켜야 할 것 (오탐이 더 위험하다) ──────────────────────────────────

def test_our_own_survey_note_passes():
    """⛔ 이것이 막히면 규율이 지키려던 것을 규율이 막는다."""
    refuse_if_vendor_original("docs/vendors/orbit.md", _NOTE)


def test_a_vendor_name_alone_is_not_enough():
    assert rights_assertions("Boston Dynamics Orbit 어댑터의 남쪽 포트를 정리한다") == []


def test_a_quoted_rights_line_is_a_quotation_not_a_claim():
    """*"저쪽 표지에 이렇게 적혀 있다"* 는 서술이지 이 문서의 주장이 아니다."""
    text = "표지에는 이렇게 적혀 있다:\n\n> Copyright 2026 Vendor. All rights reserved.\n\n원문은 두지 않는다."
    assert rights_assertions(text) == []


def test_a_rights_line_inside_a_code_span_passes():
    """판별 문자열 자체를 인용해야 할 때가 있다 — `check_terms.py` 와 같은 규칙이다."""
    assert rights_assertions("헤더는 `Copyright 2026 Vendor Inc.` 이고 이것으로 판별한다") == []


def test_a_fenced_block_is_not_a_claim_either():
    text = "예시:\n\n```\nCopyright 2026 Vendor. All rights reserved.\n```\n\n위는 예시다."
    assert rights_assertions(text) == []


# ── 관문이 실제로 그 자리에 있는가 ─────────────────────────────────────────

def _pipeline_src() -> str:
    from nexus.ingest import pipeline
    return pathlib.Path(pipeline.__file__).read_text(encoding="utf-8")


def test_the_guard_runs_before_the_document_is_classified():
    """⛔ 순서가 이 관문의 전부다. 분류·청킹 뒤에 두면 거절한 문서가 이미 청크가 돼 있다 —
    격리와 거절의 차이가 사라진다."""
    src = _pipeline_src()
    guard = src.index("refuse_if_vendor_original(collected")
    classify = src.index("classification = classify(")
    assert guard < classify, "거절이 분류 뒤에 있다"


def test_a_refusal_is_counted_apart_from_a_failure():
    """⛔ 한 수로 뭉치면 *"적재가 12건 실패했다"* 를 읽는 사람이 우리 쪽 결함을 찾는다.
    여기서 고칠 것은 넣지 말았어야 할 파일이다."""
    from nexus.ingest.pipeline import IngestResult

    r = IngestResult()
    assert r.refused_vendor == 0 and r.failed == 0
    assert "refused_vendor" in IngestResult.__dataclass_fields__
    assert re.search(r"except VendorOriginalRefused", _pipeline_src())


def test_the_module_writes_down_what_it_cannot_catch():
    """한계를 안 적으면 다음 사람이 이 검사를 실제보다 넓게 믿는다."""
    from nexus.ingest import vendor_guard

    assert "완전하지 않다" in (vendor_guard.__doc__ or "")
