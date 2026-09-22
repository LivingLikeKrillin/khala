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
    note = P.note_for(_WROTE)
    assert "네가 가져온 곳은 여기다" in note


def test_citing_this_is_not_a_ban_on_citing_the_others():
    """⛔ **그 절이 한 번 너무 멀리 갔다 (실측 2026-09-23).**

    앞 판은 *"해석한 다른 문서를 **대신** 인용하지 마라"* 였고, 넷째 운영자 질의에서 **사람
    근거 인용이 0** 이 됐다 — 앞 세 판이 2~3건씩 인용하던 사람 문서가 통째로 빠졌다.
    「대신」이 하는 일을 모델이 흘리면 *"해석한 문서를 인용하지 마라"* 가 된다.

    ⚠ 그 판의 조각 배합은 **앞 판과 같았고**(기계 19 · 사람 12), 이 등급의 문서는 절 이름이
    번호로 시작하지 않아 `crossrefs` 가 가져올 절이 **0 건**이다 — 재고 나서 D 를 배제했다.
    """
    note = P.note_for(_WROTE)
    assert "그것도 같이 인용해라" in note, "사람 근거를 같이 인용하라는 말이 없다"
    assert "인용하지 말라는 말이 아니다" in note, "금지로 읽힐 자리를 안 막았다"
    assert "대신 인용하지 마라" not in note, "너무 멀리 간 절이 살아 있다"


def test_the_note_forbids_laundering_a_citation_out_of_the_document():
    """⛔⛔ **같은 판에서 나온 둘째 — 인용 세탁 (2026-09-23).**

    그 설명 문서의 카드 줄 안에 `[출처: 인터페이스 계약 명세서 …]` 가 **글자로 적혀 있었고**,
    답이 그것을 **제 인용으로 옮겨 적었다.** 그 사람 문서는 이번 꾸러미에 없었다. 지난 LLM
    답의 인용이 새 답의 인용으로 승격된다 — **한 세대에 한 번씩 근거 없이 신뢰가 오른다.**

    ⚠ **오늘 걸린 것은 우연이다.** 그 문서가 없어서 `verified:false` 가 났다. 있었으면
    **검증을 통과하고 세탁은 안 보였다.** 검증기로는 못 막고 계약이 막아야 한다.
    """
    note = P.note_for(_WROTE)
    assert "이 문서의 내용이지 네 근거가 아니다" in note
    assert "옮겨 적지 마라" in note


def test_an_unmatched_citation_keeps_its_raw_string(monkeypatch):
    """⭐ **검증기는 제 일을 했다** — 여기서 고칠 것이 없다는 것을 박아 둔다.

    세탁된 인용이 `verified: false` 로 났다. 꾸러미에 그 문서가 없으므로 **맞는 판정**이다.
    그리고 제목·절을 **임의로 가르지 않고 원문 그대로 남긴다** — 대조할 이름이 없는데
    쉼표에서 자르면 **없는 절 이름을 만들어 낸다.**
    """
    from nexus.llm.citations import validate_citations
    from nexus.search.evidence_packet import EvidencePacket, EvidenceSnippet

    s = EvidenceSnippet(chunk_rid="c1", doc_rid="d1", doc_title="꾸러미에 있는 문서",
                        section_path="1절", source_uri="t:x.md", text="본문",
                        score=0.9, classification="INTERNAL")
    r = validate_citations("주장[출처: 꾸러미에 없는 문서 — 부제, 3. 어느 절].",
                           EvidencePacket(snippets=[s]))

    assert r.unverified_count == 1
    c = r.citations[0]
    assert c.verified is False
    assert c.title == "꾸러미에 없는 문서 — 부제, 3. 어느 절", "원문을 안 지켰다"
    assert c.section == "", "대조할 문서가 없는데 절 이름을 지어냈다"


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


def test_the_rule_is_stated_once_and_the_mark_rides_on_each_chunk():
    """⛔⛔ **조각마다 붙이던 판은 꾸러미의 52% 가 같은 문장 열두 벌이었다** (실측 2026-09-23).

    등급 문장이 한 줄일 때는 값이 쌌다. 기계가 **쓴** 등급의 문장은 여섯 문장 354자이고,
    조각마다 붙자 근거보다 주석이 길어졌다.

    ⛔ **그리고 이 비용은 기계 조각이 많을수록 커진다** — 즉 **사람 근거가 가장 주목받아야
    할 때 가장 묻힌다.** 넷째 운영자 질의에서 사람 근거 인용이 0 이 된 판이 그 모양이었다.

    ⇒ 규칙은 위에서 **한 번**, 조각마다 남는 것은 **짧은 표시**다.
    """
    from nexus.search.evidence_packet import EvidencePacket, EvidenceSnippet, format_for_llm

    def _snip(i, tier):
        s = EvidenceSnippet(chunk_rid=f"c{i}", doc_rid="d1", doc_title="문서",
                            section_path=f"{i}절", source_uri="t:x.md",
                            text="근거 본문", score=0.9, classification="INTERNAL")
        s.provenance_tier = tier
        return s

    text = format_for_llm(EvidencePacket(
        snippets=[_snip(i, _WROTE) for i in range(6)] + [_snip(9, P.AUTHORED)]))

    assert text.count(P.note_for(_WROTE)) == 1, "규칙이 조각마다 반복된다 — 근거가 묻힌다"
    assert text.count(P.mark(_WROTE)) == 7, "짧은 표시가 조각마다 안 붙는다 (머리말 1 + 조각 6)"
    assert P.note_for(_WROTE) in text, "규칙이 아예 없다"


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
