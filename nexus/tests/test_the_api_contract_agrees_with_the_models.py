"""`docs/API_CONTRACT.md` 가 적은 요청 칸이 **코드에 그 값으로 있는가.**

⛔ **왜 생겼나 (실측 2026-09-23).** 그 문서가 `AnswerRequest.top_k` 를 **10** 이라고 적고
있었다. 실제 값은 **20** 이고, 그 20 에는 측정 근거가 코드 주석에 붙어 있다(집합 질문이
10 에서 잘려 근거가 8,163자 → 19,184자로 늘었다). 문서만 읽고 만든 클라이언트는 **예산이
절반인 채로** 돌고, 답이 부실한 이유를 검색 품질에서 찾게 된다.

같은 문단에서 `identifier_channel` · `exclude_doc_types` · `history` · `origin_*` 넷이 통째로
빠져 있었고, `provenance_tier` 어휘에는 `machine_written` 이 없었다.

⭐ **이 파일이 막는 것은 「낡음」이 아니라 「틀림」이다.** 문서가 스스로 *"전체 목록이 아니다"*
라고 선언하므로 **빠진 것은 결함이 아니다.** 결함은 **적어 놓고 다른 값인 것**이다 — 읽는
사람이 확인할 방법이 없고, 확인할 생각도 안 한다.

⚠ 그래서 단언이 한 방향이다: **문서 → 코드.** 코드에만 있는 칸은 여기서 안 운다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from nexus.api import AnswerRequest, SearchRequest

DOC = Path(__file__).resolve().parents[1] / "docs" / "API_CONTRACT.md"

#: 문서가 이름으로 부르는 요청 모델. 늘리려면 문서에 그 클래스 블록이 있어야 한다.
DOCUMENTED = {"SearchRequest": SearchRequest, "AnswerRequest": AnswerRequest}

#: `    name: type = default   # 주석` 에서 이름과 기본값만 집는다.
FIELD = re.compile(r"^\s{4}(\w+)\s*:\s*[^=#]+?(?:=\s*(.+?))?\s*(?:#.*)?$")

#: 문서가 쓰는 표기 → 파이썬 값. **여기 없는 표기는 값 대조를 건너뛴다** — 문서는 산문이고,
#: 모든 표기를 파서에 맞추라고 요구하면 문서가 파서에 종속된다.
LITERALS = {"True": True, "False": False, "None": None,
            "'auto'": "auto", '"auto"': "auto",
            "'INTERNAL'": "INTERNAL", '"INTERNAL"': "INTERNAL",
            "'default'": "default", '"default"': "default"}


def _documented_fields(class_name: str) -> dict[str, str | None]:
    """문서의 그 클래스 블록에서 `{칸: 기본값 표기}` 를 읽는다."""
    text = DOC.read_text(encoding="utf-8")
    start = text.index(f"class {class_name}(BaseModel):")
    body = text[start:].split("```", 1)[0].splitlines()[1:]

    out: dict[str, str | None] = {}
    for line in body:
        if not line.startswith("    ") or line.strip().startswith("#"):
            continue
        m = FIELD.match(line)
        if m:
            out[m.group(1)] = (m.group(2) or "").strip() or None
    return out


@pytest.mark.parametrize("name", sorted(DOCUMENTED), ids=str)
def test_every_documented_field_exists_in_the_model(name):
    """⛔ 문서가 부르는 칸이 코드에 없으면, 그 문서를 읽고 만든 요청은 이제 **422** 다."""
    documented = _documented_fields(name)
    missing = sorted(set(documented) - set(DOCUMENTED[name].model_fields))

    assert not missing, f"{name}: 문서에만 있는 칸 {missing} — 문서가 낡았거나 칸이 사라졌다"


@pytest.mark.parametrize("name", sorted(DOCUMENTED), ids=str)
def test_every_documented_default_is_the_real_one(name):
    """⭐ **이것이 `top_k` 를 잡는 단언이다.**"""
    model = DOCUMENTED[name]
    wrong = []
    for field, written in _documented_fields(name).items():
        if written is None or field not in model.model_fields:
            continue
        expected = LITERALS.get(written, _as_number(written))
        if expected is _SKIP:
            continue
        actual = model.model_fields[field].default
        if actual != expected:
            wrong.append(f"{field}: 문서 {written} != 코드 {actual!r}")

    assert not wrong, f"{name}: " + " · ".join(wrong)


def test_the_parser_actually_found_the_fields():
    """⚠ **대조군.** 파서가 빈 사전을 내면 위 둘이 **공짜로 초록**이다.

    문서의 서식이 바뀌어 블록을 못 읽게 되면 여기가 먼저 운다.
    """
    for name, model in DOCUMENTED.items():
        found = _documented_fields(name)
        assert len(found) >= 8, f"{name}: 문서에서 칸을 {len(found)}개만 읽었다 — 파서가 빗나갔다"
        assert "top_k" in found, f"{name}: `top_k` 를 못 읽었다"
        assert found["top_k"] == str(model.model_fields["top_k"].default)


def test_the_two_paths_really_have_different_budgets():
    """⛔ **문서가 둘을 같은 값으로 적고 있었다.** 다르다는 것이 이 계약의 요점이다."""
    assert SearchRequest.model_fields["top_k"].default == 10
    assert AnswerRequest.model_fields["top_k"].default == 20


def test_the_treatment_flag_is_documented_only_where_it_exists():
    """⚠ 이 깃발이 `/search` 요청에 적히면, 읽은 사람은 **422 를 받는다.**"""
    assert "identifier_channel" in _documented_fields("AnswerRequest")
    assert "identifier_channel" not in _documented_fields("SearchRequest")


def test_the_provenance_vocabulary_in_the_doc_is_complete():
    """등급 어휘는 프롬프트·응답·MCP·웹이 **같은 것**을 써야 한다 (`search/provenance.py` 정본).

    ⛔ **첫 판은 문서 전체에서 글자를 찾았고, 그래서 안 물었다** — 타입 줄에서 등급 하나를
    지워도 **바로 아래 설명 주석에 남은 같은 글자**에 걸려 초록이었다. 읽는 사람이 보고
    구현하는 것은 그 union 이지 주석이 아니다. 그래서 **그 줄만** 본다.
    """
    from nexus.search import provenance

    line = next(ln for ln in DOC.read_text(encoding="utf-8").splitlines()
                if ln.strip().startswith("provenance_tier:"))
    tiers = {v for k, v in vars(provenance).items()
             if k.isupper() and isinstance(v, str) and v.startswith(("authored", "machine_"))}

    missing = sorted(t for t in tiers if f"'{t}'" not in line)
    assert not missing, f"`provenance_tier` union 에 없는 등급: {missing} — 줄: {line.strip()!r}"


_SKIP = object()


def _as_number(written: str):
    """숫자 표기만 값으로 본다. 나머지는 건너뛴다 — 문서는 파서를 위해 쓰이지 않는다."""
    try:
        return int(written)
    except ValueError:
        return _SKIP
