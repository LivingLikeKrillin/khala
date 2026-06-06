"""Claim — 개념(entity)에 매달리는 도메인 사실 (값/불변식/요구).

CRM(KhalaResource)을 상속한다. CRM `status`(resource_status: active|...)는
리소스 수명주기이며, claim의 *검증상태*는 별도 `claim_status` 필드로 둔다.
value-bearing claim은 코드 상수를 가리키므로 source_kind='code'.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from khala.models.resource import KhalaResource
from khala.rid import claim_rid


@dataclass
class Claim(KhalaResource):
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
    value_ref_kind: str | None = None  # code_constant | config_key | db_default
    criticality: str = "peripheral"  # core | peripheral
    activity: str = "active"  # active | dormant | archived
    # 검증상태 (CRM status와 분리)
    # invariant: held|violated|unverified / requirement: reflected|partial|not-reflected|unverified
    claim_status: str = "unverified"
    confidence: str = "low"  # high | medium | low
    value_symbol_hash: str | None = None
    last_verified_commit: str | None = None

    def __post_init__(self):
        if not self.rid:
            self.rid = claim_rid(self.tenant, self.claim_id)
