"""기계가 **쓴** 근거는 기계가 **읽은** 근거와 다른 말을 듣는다.

⛔ **왜 생겼나 (2026-09-23).** 설명 층이 제 LLM 설명을 코퍼스로 되돌린다. 「LLM 산출이 LLM
근거가 되는」 순환은 테넌트와 신원으로 막았다 — 사건 바퀴는 그 테넌트에 **닿을 수 없다.**

그런데 닿아도 되는 질의(운영자 질의)에서는 그 근거가 **사람이 쓴 문서와 같은 얼굴로** 들어온다.
등급이 없으면 답을 쓰는 모델이 둘을 같은 것으로 다루고, 인용은 그 구별을 약속하지 못한다.

⭐ **핵심 정식화는 설명 층이 줬다**: *이력의 근거로 쓰고 원인의 근거로는 쓰지 마라.*
LLM 산출은 **무엇이 언제 있었나**에는 쓸 만하고 **왜**에는 못 쓴다.

⛔ **첫 초안의 한 줄을 물렸다.** *"원인은 그 설명이 인용한 사람의 문서에서 다시 확인하라"* 는
**모델이 못 지킨다** — 그 문서가 이번 꾸러미에 있을 수도 없을 수도 있다. 못 할 일을 시키면
무시하거나 **한 척한다.** 지킬 수 있는 모양은 금지다.
"""

from __future__ import annotations

import pytest

from nexus.ingest.pipeline import machine_written_tenants
from nexus.search import provenance as P

_WROTE = P.MACHINE_WRITTEN
_READ = P.MACHINE_READ


# ── 등급마다 **다른** 말을 한다 ───────────────────────────────────────────────

def test_the_two_machine_tiers_do_not_share_a_sentence():
    """⛔ **이것이 이 파일의 핵심 단언이다.**

    상수 하나를 붙이던 판은 등급이 둘일 때 맞았다. 셋이 되면 **둘 중 하나가 거짓을 받는다** —
    기계가 쓴 근거에 *"그림에서 읽었다"* 가 붙는다. 거짓인 주석은 없는 주석보다 나쁘다.
    """
    assert P.note_for(_WROTE) != P.note_for(_READ)
    assert P.mark(_WROTE) != P.mark(_READ)
    assert P.note_for(_WROTE) and P.note_for(_READ)


def test_the_authored_tier_stays_silent():
    """⭐ **기본이 조용해야 표시가 뜻을 갖는다.** 전부에 붙이면 아무것도 구별하지 못한다."""
    for quiet in (P.AUTHORED, None, "", "모르는-등급"):
        assert P.note_for(quiet) == ""
        assert P.mark(quiet) == ""
        assert not P.needs_note(quiet)


def test_the_new_tier_asks_for_a_note_and_a_mark():
    assert P.needs_note(_WROTE)
    assert P.mark(_WROTE).strip()


# ── 문구가 지켜야 할 것 ───────────────────────────────────────────────────────

def test_the_note_does_not_use_the_citation_word():
    """⛔ **`출처` 를 쓰면 인용 안으로 빨려 들어간다** (실측 2026-08-10, 이 모듈 머리말).

    앞선 판에서 라벨이 인용 문자열에 흡수돼 검증기가 제목을 못 찾았고, **멀쩡한 답 2건이
    환각으로 분류**됐다. 새 등급이 같은 함정을 다시 밟지 않는지 여기서 본다.
    """
    assert "출처" not in P.note_for(_WROTE)
    assert "출처" not in P.mark(_WROTE)


def test_the_note_forbids_rather_than_asks_for_something_impossible():
    """⭐ **모델이 지킬 수 있는 모양인가.**

    「다시 확인하라」는 그 문서가 꾸러미에 없으면 못 한다. 금지는 언제나 지킬 수 있다.
    """
    note = P.note_for(_WROTE)
    assert "단정하지 마라" in note, "지킬 수 있는 금지가 없다"
    assert "다시 확인하라" not in note, "못 할 일을 시키는 문장이 살아 있다"


def test_the_note_carries_every_obligation_the_source_asked_for():
    """⛔ **이 검사가 한 번 틀렸다 (2026-09-23).**

    앞 판은 *"의무 넷"* 을 셌는데, 그 넷은 **내가 줄인 문구에서 뽑은 것**이었다. 원본은
    다섯이었고 첫째가 *"인용하되 LLM 산출이라 밝혀라"* 다. **줄인 글로 쓴 검사는 줄인 글을
    자기 자신과 대조할 뿐이다** — 초록이었고, 뜻은 빠져 있었다.

    ⇒ 목록을 **원본 기준으로** 다시 적는다. 다음에 문구를 줄이는 사람은 이 다섯을 넘어야 한다.
    """
    note = P.note_for(_WROTE)
    assert "사람이 쓴 문장이 아니다" in note          # ① 무엇인가
    assert "인용해라" in note                          # ② **귀속하라** — 한 번 잃었던 의무
    assert "무엇이 언제 있었나" in note                # ③ 무엇에 쓰는가
    assert "원인을" in note                            # ④ 무엇에 안 쓰는가
    assert "어긋나면 사람 쪽을 따르고" in note         # ⑤ 충돌하면


def test_the_note_says_not_to_cite_the_interpreter_instead():
    """⛔ **실물이 그렇게 났다 (첫 운영자 질의, 2026-09-23).**

    답이 사건 사실 셋을 이 등급의 조각 하나에서만 가져다 쓰고, 인용은 그 사실을 **해석한
    사람 문서**로 갔다. 계약은 지켰는데 근거를 근거라고 안 밝혔고, 그래서 표시가 나올 자리가
    없었다. 「인용해라」만으로는 그 답이 이미 인용을 하고 있었으므로 안 걸린다.
    """
    assert "해석한 다른 문서를 대신 인용하지 마라" in P.note_for(_WROTE)


def test_the_note_names_no_producer():
    """⚠ **등급은 어휘이지 어느 층의 것이 아니다.** 다른 기계가 써도 같은 말이어야 한다."""
    for name in ("narrator", "picasso", "khala"):
        assert name not in P.note_for(_WROTE)


# ── 근거 꾸러미가 **그 등급의** 주석을 싣는가 ────────────────────────────────

@pytest.mark.parametrize("tier,expect", [(_WROTE, _WROTE), (_READ, _READ), (P.AUTHORED, None)])
def test_the_packet_carries_the_note_that_belongs_to_the_tier(tier, expect):
    """⛔ **표현이 아니라 행동이다.** 프롬프트에 실제로 실리는 문자열을 본다."""
    from nexus.search.evidence_packet import EvidencePacket, EvidenceSnippet, format_for_llm

    snippet = EvidenceSnippet(
        chunk_rid="c1", doc_rid="d1", doc_title="문서", section_path="1절",
        source_uri="t:doc.md", text="근거 본문", score=0.9, classification="INTERNAL",
    )
    snippet.provenance_tier = tier
    text = format_for_llm(EvidencePacket(snippets=[snippet]))

    if expect is None:
        assert P.note_for(_WROTE) not in text and P.note_for(_READ) not in text
    else:
        assert P.note_for(expect) in text, "그 등급의 주석이 프롬프트에 안 실린다"
        other = _READ if expect is _WROTE else _WROTE
        assert P.note_for(other) not in text, "다른 등급의 주석이 실렸다 — 거짓을 말한다"


# ── 선언 — 문서가 자칭하지 않는다 ────────────────────────────────────────────

def test_the_declaration_is_configuration_not_a_file_claim():
    """⛔ 자칭을 허용하면 **안 적은 문서가 사람 글로 신뢰된다** (`external_spec` 과 같은 논증)."""
    assert machine_written_tenants({}) == frozenset()
    assert machine_written_tenants({"index": {"machine_written_tenants": ["a", " b "]}}) \
        == frozenset({"a", "b"})


def test_this_deployment_declares_the_explanation_tenant():
    """⭐ 배포 대조군 — 선언이 없으면 위의 모든 검사가 **빈 집합에 대고** 초록이다."""
    import pathlib

    import yaml

    cfg_path = pathlib.Path(__file__).resolve().parents[1] / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    assert "narrator" in machine_written_tenants(cfg), \
        "설명 코퍼스가 기계가 쓴 것으로 선언돼 있지 않다 — 사람 글과 같은 얼굴로 들어온다"


def test_the_ingest_lets_the_tenant_win_over_the_chunker():
    """⛔ **기본 인자로 받지 않는다** — 안 넘긴 호출부가 조용히 「사람 글」로 앉힌다.

    오늘 같은 모양에 한 번 데였다(`weak_evidence` 가 스트리밍 경로에서 기본값으로 떨어진 것,
    #537). 그래서 마지막 관문이 **테넌트를 보고** 정한다.
    """
    import inspect

    from nexus.ingest import pipeline

    src = inspect.getsource(pipeline._save_chunks)
    assert "machine_written_tenants()" in src, "조각을 쓰는 자리가 선언을 안 본다"
    assert "MACHINE_WRITTEN if tenant in" in src
