"""소유자의 **판정**이 claim 에 붙어 답변까지 가는가.

⛔ **왜 이 파일이 있나 (2026-09-23).** 문서 값과 코드 값이 갈린 것을 khala 가 찾아 전달했고,
소유자가 2026-08-31 에 일곱 건을 판정했다. 그 판정은 운영자 메모에만 있었다 — 기계가 읽는
자리에 없어서, 같은 질문이 오면 답변은 여전히 문서 값만 내거나(정원 200) 둘을 나란히 놓고
판정을 사람에게 되물었다(`OPEN.md` A27). **판정을 다시 하는 것이 아픈 것이지, 판정이 필요한
것이 아픈 것이 아니다.** 그래서 판정을 값에 붙여 한 번만 하게 만든다.

설계 셋:
- 판정은 **소유자와 날짜**를 갖는다. 둘 중 하나가 없으면 판정이 아니라 메모다 — 시드가 거부한다.
- 판정은 코드 값을 **읽지 못해도** 붙는다. 정원(`if (count > 49)`)처럼 해석기가 못 읽는 모양이
  있고, 그 값에도 판정은 있다.
- 판정과 코드 현재 값의 어긋남은 **코드가 계산**한다. 모델은 그것을 서술만 한다.
"""

from __future__ import annotations

import pytest
import yaml

from nexus.claims.seed import seed_claims
from nexus.index.code_source import CodeValueResolver
from nexus.models.claim import Claim
from nexus.search.evidence_packet import CodeValue, EvidencePacket, format_for_llm


class _Repo:
    def __init__(self):
        self.saved = []

    async def upsert(self, c):
        self.saved.append(c)


def _yaml(tmp_path, items):
    p = tmp_path / "claims.yaml"
    p.write_text(yaml.safe_dump(items, allow_unicode=True), encoding="utf-8")
    return str(p)


def _src(tmp_path):
    src = tmp_path / "src"
    f = src / "a" / "Req.java"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("public class Req { @Size(max = 20) private String nickname; }",
                 encoding="utf-8")
    return src


def _item(claim_id="user-nickname-max", value_source="Req.nickname@Size.max", **ruling):
    it = {"claim_id": claim_id, "kind": "invariant", "concepts": ["닉네임"],
          "statement": "닉네임 길이 상한 (서버 요청 검증)", "value_source": value_source,
          "value_ref_kind": "code_annotation", "criticality": "core", "owner": "@backend"}
    it.update(ruling)
    return it


RULING = {"ruled_value": "12", "ruled_source": "정책 문서 · 프론트 공용 스키마",
          "ruled_by": "@owner", "ruled_on": "2026-08-31",
          "ruling_note": "코드 20 은 12 로 고칠 것"}


# ── 모델 ─────────────────────────────────────────────────────────────────────

def test_a_claim_carries_the_owners_ruling():
    c = Claim(**_item(**RULING))
    assert c.ruled_value == "12"
    assert c.ruled_source == "정책 문서 · 프론트 공용 스키마"
    assert c.ruled_by == "@owner"
    assert c.ruled_on == "2026-08-31"
    assert c.ruling_note == "코드 20 은 12 로 고칠 것"


def test_a_claim_without_a_ruling_has_none_not_empty_strings():
    """None 과 "" 가 다르다 — "" 은 「판정이 빈 값」으로 읽힌다."""
    c = Claim(**_item())
    assert c.ruled_value is None and c.ruled_by is None and c.ruled_on is None


# ── 시드 ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_seed_refuses_a_ruling_without_who_and_when(tmp_path):
    """⛔ 소유자·날짜 없는 판정은 판정이 아니라 메모다. 조용히 들어가면 「누가 언제」를
    영영 못 묻는다."""
    path = _yaml(tmp_path, [_item(ruled_value="12")])
    with pytest.raises(ValueError, match="ruled_by"):
        await seed_claims(path, _Repo(), CodeValueResolver(_src(tmp_path)))


@pytest.mark.asyncio
async def test_seed_reports_ruling_only_claims_separately(tmp_path):
    """코드 값을 읽지 못하는 자리에도 판정은 있다 — 그것은 「안 붙음」이 아니다."""
    path = _yaml(tmp_path, [
        _item(**RULING),
        _item("partyroom-capacity", None, ruled_value="50", ruled_source="코드",
              ruled_by="@owner", ruled_on="2026-08-31"),
    ])
    repo = _Repo()

    rep = await seed_claims(path, repo, CodeValueResolver(_src(tmp_path)))

    assert rep.total == 2 and rep.bound == 1
    assert rep.unbound == []
    assert rep.ruling_only == ["partyroom-capacity"]
    assert rep.rulings == 2
    saved = {c.claim_id: c for c in repo.saved}
    assert saved["partyroom-capacity"].ruled_value == "50"


# ── 판정 ↔ 코드 현재 값 ──────────────────────────────────────────────────────

def test_a_code_value_carries_the_ruling_and_flags_a_conflict():
    from nexus.search.reconcile import code_value_from

    c = Claim(**_item(**RULING))

    cv = code_value_from(c, value="20", source="a/Req.java", drifted=False)

    assert cv.value == "20" and cv.ruled_value == "12"
    assert cv.ruled_by == "@owner" and cv.ruled_on == "2026-08-31"
    assert cv.ruling_conflict is True


def test_no_conflict_when_the_code_already_matches_the_ruling():
    from nexus.search.reconcile import code_value_from

    cv = code_value_from(Claim(**_item(**RULING)), value="12", source="a/Req.java",
                         drifted=False)
    assert cv.ruling_conflict is False


def test_a_ruling_without_a_value_never_conflicts():
    """「코드 값 기각, 대체 값 미정」 — 판정은 있지만 비교할 값이 없다."""
    from nexus.search.reconcile import code_value_from

    c = Claim(**_item(ruled_value=None, ruled_by="@owner", ruled_on="2026-08-31",
                      ruling_note="코드값 기각, 대체 값 미정"))
    cv = code_value_from(c, value="100", source="a/Req.java", drifted=False)
    assert cv.ruling_conflict is False
    assert cv.ruling_note == "코드값 기각, 대체 값 미정"


def test_a_ruling_reaches_the_packet_even_when_the_code_value_is_unreadable():
    from nexus.search.reconcile import code_value_from

    c = Claim(**_item("partyroom-capacity", None, ruled_value="50", ruled_source="코드",
                      ruled_by="@owner", ruled_on="2026-08-31"))
    cv = code_value_from(c, value=None, source="", drifted=False)
    assert cv.value == "" and cv.ruled_value == "50" and cv.ruling_conflict is False


def test_a_claim_with_neither_code_value_nor_ruling_yields_nothing():
    from nexus.search.reconcile import code_value_from

    assert code_value_from(Claim(**_item()), value=None, source="", drifted=False) is None


# ── 프롬프트 ─────────────────────────────────────────────────────────────────

def _packet(**kw):
    base = dict(statement="닉네임 길이 상한 (서버 요청 검증)", value="20", source="a/Req.java")
    base.update(kw)
    return EvidencePacket(code_values=[CodeValue(**base)])


def test_the_prompt_shows_the_ruling_and_says_it_is_decided():
    out = format_for_llm(_packet(ruled_value="12", ruled_source="정책 문서",
                                 ruled_by="@owner", ruled_on="2026-08-31",
                                 ruling_conflict=True))
    assert "판정" in out and "12" in out and "@owner" in out and "2026-08-31" in out
    assert "정책 문서" in out
    # 모델에게: 판정된 값은 다시 판정하지 말고 답으로 내라.
    assert "판정이 있는 값은" in out and "다시 판정하지" in out


def test_the_prompt_flags_a_code_value_that_contradicts_the_ruling():
    yes = format_for_llm(_packet(ruled_value="12", ruled_by="@owner", ruled_on="2026-08-31",
                                 ruling_conflict=True))
    no = format_for_llm(_packet(value="12", ruled_value="12", ruled_by="@owner",
                                ruled_on="2026-08-31", ruling_conflict=False))
    assert "판정과 어긋" in yes
    assert "판정과 어긋" not in no


def test_a_ruling_only_value_is_rendered_as_unread_code():
    out = format_for_llm(_packet(value="", source="", ruled_value="50", ruled_source="코드",
                                 ruled_by="@owner", ruled_on="2026-08-31"))
    assert "코드에서 읽지 못함" in out and "50" in out


def test_values_without_rulings_do_not_mention_rulings():
    """⛔ 대조군. 판정이 없는 claim 의 프롬프트에 판정 어휘가 새면 모델이 없는 판정을 찾는다."""
    out = format_for_llm(_packet())
    assert "판정" not in out


# ── 응답 ─────────────────────────────────────────────────────────────────────

def test_the_answer_payload_lists_code_values_with_their_rulings():
    """에이전트 소비자에게 판정은 산문이 아니라 값이어야 한다."""
    from nexus.search.evidence_packet import code_values_payload

    rows = code_values_payload(_packet(ruled_value="12", ruled_by="@owner",
                                       ruled_on="2026-08-31", ruling_conflict=True))
    assert rows == [{
        "statement": "닉네임 길이 상한 (서버 요청 검증)", "value": "20", "source": "a/Req.java",
        "drifted": False, "ruled_value": "12", "ruled_source": None, "ruled_by": "@owner",
        "ruled_on": "2026-08-31", "ruling_note": None, "ruling_conflict": True,
    }]


def test_an_empty_packet_yields_an_empty_payload():
    from nexus.search.evidence_packet import code_values_payload

    assert code_values_payload(EvidencePacket()) == []
