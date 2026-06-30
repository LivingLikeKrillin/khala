from nexus.models.claim import Claim
from nexus.rid import claim_rid


def test_claim_defaults_and_crm_separation():
    c = Claim(
        claim_id="basic-max-projects",
        kind="invariant",
        concepts=["Basic", "프로젝트"],
        statement="Basic 등급은 프로젝트를 최대 N개 가질 수 있다",
        value_source="PlanPolicy.BASIC_MAX_PROJECTS",
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
    a = claim_rid("default", "basic-max-projects")
    assert a == claim_rid("default", "basic-max-projects")
    assert a.startswith("claim_") and ":" not in a
