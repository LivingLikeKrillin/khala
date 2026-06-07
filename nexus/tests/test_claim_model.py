from nexus.models.claim import Claim
from nexus.rid import claim_rid


def test_claim_defaults_and_crm_separation():
    c = Claim(
        claim_id="associate-max-playlists",
        kind="invariant",
        concepts=["준회원", "플레이리스트"],
        statement="준회원은 플레이리스트를 최대 N개 가질 수 있다",
        value_source="PlaylistPolicy.ASSOCIATE_MAX_PLAYLISTS",
        value_ref_kind="code_constant",
        criticality="core",
        owner="@backend-lead",
    )
    assert c.rtype == "claim"
    assert c.rid.startswith("claim_")  # make_rid prefix, 콜론 없음
    assert c.status == "active"  # CRM resource_status — 검증상태로 오염 금지
    assert c.claim_status == "unverified"  # claim 검증상태는 별도 필드
    assert c.confidence == "low"
    assert c.source_kind == "code"  # value-bearing claim은 code 소스
    assert c.owner == "@backend-lead"


def test_claim_rid_stable_and_prefixed():
    a = claim_rid("default", "associate-max-playlists")
    assert a == claim_rid("default", "associate-max-playlists")
    assert a.startswith("claim_") and ":" not in a
