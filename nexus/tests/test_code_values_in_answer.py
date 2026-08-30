"""답변 근거에 **코드의 현재 값**이 붙는가.

⛔ **왜 이 파일이 있나 (2026-08-30).** 코드 값 해석기도, claims 표도, 전용 CLI 도 다 있었는데
**답변 경로가 부르는 곳이 없었다.** 그래서 슬랙에서 *"파티 이름 몇 자까지"* 를 물으면 문서만
보고 답했고, 코드가 다른 값을 갖고 있어도 나타날 길이 없었다. 만들어 놓고 읽는 쪽이 없는,
이 리포가 반복해서 데인 모양이다.

그리고 사용자가 요구한 것은 **판정이 아니라 병치**다: *"구현이 문서를 어긴 것일 수도 있고
문서가 갱신되지 않은 것일 수도 있다. 그러니 둘 다 알려줘야 한다."*
"""

from __future__ import annotations

from dataclasses import dataclass

from nexus.claims.matching import claims_for_question
from nexus.search.evidence_packet import CodeValue, EvidencePacket, format_for_llm


@dataclass
class _Claim:
    concepts: list
    statement: str = "값"


# ── 질문 → claim 고르기 ───────────────────────────────────────────────────────

def test_all_concepts_must_appear_or_it_does_not_attach():
    """⛔ 하나만 겹쳐도 붙이면 `이름` 하나로 파티·플레이리스트·닉네임이 전부 딸려 온다."""
    party = _Claim(["파티", "이름"])
    playlist = _Claim(["플레이리스트", "이름"])

    got = claims_for_question("파티 이름은 몇 자까지 쓸 수 있어?", [party, playlist])

    assert got == [party]


def test_an_unrelated_question_attaches_nothing():
    """대조군 — 안 붙는 것이 기본이다."""
    assert claims_for_question("배포는 어떻게 해?", [_Claim(["파티", "이름"])]) == []


def test_an_empty_question_attaches_nothing():
    assert claims_for_question("", [_Claim(["파티"])]) == []


def test_a_claim_without_concepts_never_attaches():
    """개념이 비면 `all([])` 이 참이라 **모든** 질문에 붙는다. 그 자리를 막는다."""
    assert claims_for_question("아무 질문", [_Claim([])]) == []


# ── 프롬프트에 어떻게 나가는가 ────────────────────────────────────────────────

def test_the_code_value_is_marked_as_code_not_as_a_document():
    """그 구별이 없으면 모델은 코드 값을 근거 문서처럼 인용한다."""
    packet = EvidencePacket(code_values=[
        CodeValue(statement="파티 이름 길이 상한 (서버 요청 검증)", value="100",
                  source="party/.../CreatePartyroomRequest.java")])

    out = format_for_llm(packet)

    assert "## 코드의 현재 값 (Code)" in out
    assert "문서가 아니라" in out
    assert "100" in out


def test_the_prompt_tells_the_model_not_to_pick_a_side():
    """⛔ 사용자 요구의 핵심. 시스템은 병치하고 판정은 사람이 한다."""
    packet = EvidencePacket(code_values=[CodeValue(statement="x", value="1")])
    out = format_for_llm(packet)
    assert "단정하지 말고" in out and "둘 다" in out


def test_drift_is_disclosed_rather_than_hidden():
    packet = EvidencePacket(code_values=[
        CodeValue(statement="x", value="1", drifted=True)])
    assert "심은 뒤 코드가 바뀜" in format_for_llm(packet)


def test_no_code_values_leaves_the_prompt_byte_identical():
    """⛔ 대조군. 안 걸리는 질문의 프롬프트가 바뀌면 평가 팩과의 비교가 끊긴다."""
    assert format_for_llm(EvidencePacket()) == format_for_llm(
        EvidencePacket(code_values=[]))
    assert "코드의 현재 값" not in format_for_llm(EvidencePacket())


# ── 배선 ─────────────────────────────────────────────────────────────────────

def test_every_call_site_passes_the_question_and_the_pool():
    """⛔ **배선 검사.** 답변 경로가 다섯이다. 한 곳만 배선하면 사람과 에이전트가 다른 답을
    받고, **그 조합은 검사가 초록인 채로 프로덕션에서 조용히 틀린다** — 이 리포가 2026-08-29
    에 정확히 그렇게 데였고(`api.py` 한 곳만), 그래서 `packet_for_answer` 가 생겼다.

    호출부를 목록으로 박지 않고 트리에서 찾는다. 새 호출부가 생기면 자동으로 걸린다.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    missing = []
    for py in list(root.rglob("*.py")):
        if "tests" in py.parts:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if getattr(fn, "id", None) != "packet_for_answer" and \
               getattr(fn, "attr", None) != "packet_for_answer":
                continue
            kw = {k.arg for k in node.keywords}
            if not {"question", "pool"} <= kw:
                missing.append(f"{py.relative_to(root)}:{node.lineno}")

    assert not missing, f"코드 값이 안 붙는 답변 경로: {missing}"
