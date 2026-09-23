"""Claim — 개념(entity)에 매달리는 도메인 사실 (값/불변식/요구).

CRM(NexusResource)을 상속한다. CRM `status`(resource_status: active|...)는
리소스 수명주기이며, claim의 *검증상태*는 별도 `claim_status` 필드로 둔다.
value-bearing claim은 코드 상수를 가리키므로 source_kind='code'.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nexus.models.resource import NexusResource
from nexus.rid import claim_rid

#: 판정을 이루는 칸. 하나라도 있으면 판정이고, 그러면 `ruled_by`·`ruled_on` 이 필수다.
RULING_FIELDS = ("ruled_value", "ruled_source", "ruled_by", "ruled_on", "ruling_note")


@dataclass
class Claim(NexusResource):
    # base에선 필수였던 rid/rtype에 기본값 부여 → 키워드만으로 생성. __post_init__에서 rid 채움.
    rid: str = ""
    rtype: str = "claim"
    source_kind: str = "code"  # value-bearing claim은 코드 소스 (CRM 기본 'git' 오버라이드)

    # ── claim 고유 ──
    claim_id: str = ""
    kind: str = "invariant"  # goal | invariant | requirement
    concepts: list[str] = field(default_factory=list)  # 척추 entity name 참조
    statement: str = ""
    value_source: str | None = None
    value_ref_kind: str | None = None  # code_constant | code_annotation | config_key | db_default
    criticality: str = "peripheral"  # core | peripheral
    activity: str = "active"  # active | dormant | archived
    # 검증상태 (CRM status와 분리)
    # invariant: held|violated|unverified / requirement: reflected|partial|not-reflected|unverified
    claim_status: str = "unverified"
    confidence: str = "low"  # high | medium | low
    value_symbol_hash: str | None = None
    last_verified_commit: str | None = None

    # ── 소유자의 판정 (2026-09-23) ──
    # 문서 값과 코드 값이 갈렸을 때 **소유자가 정한 값**. `ruled_value` 는 없을 수 있다 —
    # "코드 값 기각, 대체 값 미정" 도 판정이다(`ruling_note` 에 적는다). 판정은 반드시
    # `ruled_by`·`ruled_on` 을 갖는다(시드가 강제). 시스템은 여전히 어느 쪽이 맞는지 판정하지
    # 않는다 — 사람이 한 판정을 **기억**해서 두 번 묻지 않게 할 뿐이다.
    ruled_value: str | None = None
    ruled_source: str | None = None
    ruled_by: str | None = None
    ruled_on: str | None = None
    ruling_note: str | None = None

    @property
    def has_ruling(self) -> bool:
        return any(getattr(self, f) is not None for f in RULING_FIELDS)

    def __post_init__(self):
        if not self.rid:
            self.rid = claim_rid(self.tenant, self.claim_id)
