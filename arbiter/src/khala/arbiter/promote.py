"""promote_external — 외부 CSF 문서를 Arbiter 거버넌스 DRAFT 로 끌어올린다 (서브프로젝트 A).

인바운드 기본값은 "메모"다 — 외부 spec 은 Nexus 에 ungoverned 로 산다. 승격은 명시적, 인간이
트리거하는 단계로, CSF 문서를 **인라인**으로 받아(Arbiter 는 Nexus read client 가 없다)
DRAFT SPEC/ADR 로 record 하고, provenance 를 frontmatter 에 보존한다(거버넌스 사본이 출처를
기억하고, promoted_from_source_hash 로 이후 소스 drift 를 감지할 수 있게). 이후 기존
critique→approve 흐름이 그대로 적용된다.
"""

from __future__ import annotations

import hashlib

from . import doctypes, guidelines
from .artifacts import Artifact
from .ledger import Ledger

_REQUIRED = ("id", "kind", "title", "body")
_REQUIRED_PROV = ("source_tool", "source_id", "source_hash")
# deposit(Nexus) 측 식별자 충돌 방어와 동일 — 경로 구분자/널은 id 를 무너뜨린다.
_UNSAFE_ID_CHARS = ("/", "\\", "\x00")


class PromoteError(ValueError):
    """CSF 가 승격 불가(필드 누락 / 매핑 불가 type)일 때."""


def promote_external(ledger: Ledger, csf: dict, type: str) -> dict:
    """CSF(인라인) → Arbiter DRAFT. provenance 를 frontmatter 에 보존.

    Args:
        ledger: 대상 Ledger.
        csf: canonical spec format 문서(frontmatter dict + body).
        type: 축-A 거버넌스 타입(ADR/DESIGN/RFC) 또는 레거시 CSF 토큰(SPEC). doctypes
            레지스트리로 정규화·매핑하며, T1(거버넌스)이 아닌 타입은 승격 거부.

    Returns:
        {artifact_id, status, provenance_carried}
    """
    # type 은 축-A 타입(또는 레거시 CSF 토큰) — 상류 정규화와 동일 규칙으로 정본화한 뒤
    # 레지스트리로 승격가능성(=T1)과 Arbiter 어휘를 결정한다(하드코딩 제거).
    axis_a = doctypes.normalize_kind(type)
    sl_type = doctypes.arbiter_type_of(axis_a)
    if sl_type is None:
        raise PromoteError(
            f"type 은 거버넌스(T1) 타입이어야 한다(ADR/DESIGN/RFC/레거시 SPEC), got {type!r}"
        )
    if not all(csf.get(k) for k in _REQUIRED):
        raise PromoteError("CSF missing required fields")
    prov = csf.get("provenance") or {}
    if not all(prov.get(k) for k in _REQUIRED_PROV):
        raise PromoteError("CSF missing required provenance")
    # id 형식을 §3 규칙으로 재검증한다(spec §5.1 — deposit 의 Nexus 측 검증과 대칭). 경로 구분자까지
    # 막아, deposit 으로는 절대 들어올 수 없는 malformed-id CSF 가 promote 로 새지 않게 한다.
    expected_id = f"ext-{prov['source_tool']}-{prov['source_id']}"
    if csf.get("id") != expected_id:
        raise PromoteError(f"CSF id must be {expected_id!r}")
    if any(c in expected_id for c in _UNSAFE_ID_CHARS):
        raise PromoteError("CSF source_tool/source_id must not contain path separators")
    # source_hash 를 body 에 대해 재검증한다(deposit 의 Nexus 측 검증과 대칭). promote 는 CSF 를
    # 인라인으로 받으므로, 이 확인이 없으면 body 와 어긋난 hash 가 promoted_from_source_hash 로
    # 박혀 §6 drift 감지 훅을 조용히 오염시킨다 — breadcrumb 의 신뢰를 promote 자신이 보장한다.
    body = str(csf["body"])
    if prov["source_hash"] != hashlib.sha256(body.encode("utf-8")).hexdigest():
        raise PromoteError("provenance.source_hash does not match body")

    aid = ledger.record(sl_type, str(csf["title"]))
    art = Artifact.load(ledger._resolve(aid))
    art.body = body
    art.meta["source_tool"] = prov["source_tool"]
    art.meta["source_url"] = prov.get("source_url", "")
    art.meta["source_hash"] = prov["source_hash"]
    # drift breadcrumb (§6): 승격된 정본이 어느 source_hash 에서 왔는지 기억.
    art.meta["promoted_from_source_hash"] = prov["source_hash"]
    art.save()
    # Status StrEnum 은 소문자("draft"/"proposed") — 공개 계약은 대문자로 정규화(spec §5).
    return {
        "artifact_id": aid,
        "status": art.meta["status"].upper(),
        "provenance_carried": True,
        "guidance": guidelines.guidance_for(axis_a) or "",
    }
