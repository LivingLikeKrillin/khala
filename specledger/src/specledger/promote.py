"""promote_external — 외부 CSF 문서를 specledger 거버넌스 DRAFT 로 끌어올린다 (서브프로젝트 A).

인바운드 기본값은 "메모"다 — 외부 spec 은 Nexus 에 ungoverned 로 산다. 승격은 명시적, 인간이
트리거하는 단계로, CSF 문서를 **인라인**으로 받아(specledger 는 Nexus read client 가 없다)
DRAFT SPEC/ADR 로 record 하고, provenance 를 frontmatter 에 보존한다(거버넌스 사본이 출처를
기억하고, promoted_from_source_hash 로 이후 소스 drift 를 감지할 수 있게). 이후 기존
critique→approve 흐름이 그대로 적용된다.
"""

from __future__ import annotations

from .artifacts import Artifact
from .ledger import Ledger

# CSF kind 의 열린 enum → specledger 어휘로 강제 매핑.
_KIND_TO_TYPE = {"SPEC": "spec", "ADR": "adr"}
_REQUIRED = ("id", "kind", "title", "body")
_REQUIRED_PROV = ("source_tool", "source_id", "source_hash")


class PromoteError(ValueError):
    """CSF 가 승격 불가(필드 누락 / 매핑 불가 type)일 때."""


def promote_external(ledger: Ledger, csf: dict, type: str) -> dict:
    """CSF(인라인) → specledger DRAFT. provenance 를 frontmatter 에 보존.

    Args:
        ledger: 대상 Ledger.
        csf: canonical spec format 문서(frontmatter dict + body).
        type: "SPEC" | "ADR" — CSF 의 열린 kind 를 specledger 어휘로 매핑.

    Returns:
        {artifact_id, status, provenance_carried}
    """
    if type not in _KIND_TO_TYPE:
        raise PromoteError(f"type must be SPEC or ADR, got {type!r}")
    if not all(csf.get(k) for k in _REQUIRED):
        raise PromoteError("CSF missing required fields")
    prov = csf.get("provenance") or {}
    if not all(prov.get(k) for k in _REQUIRED_PROV):
        raise PromoteError("CSF missing required provenance")

    aid = ledger.record(_KIND_TO_TYPE[type], str(csf["title"]))
    art = Artifact.load(ledger._resolve(aid))
    art.body = str(csf["body"])
    art.meta["source_tool"] = prov["source_tool"]
    art.meta["source_url"] = prov.get("source_url", "")
    art.meta["source_hash"] = prov["source_hash"]
    # drift breadcrumb (§6): 승격된 정본이 어느 source_hash 에서 왔는지 기억.
    art.meta["promoted_from_source_hash"] = prov["source_hash"]
    art.save()
    # Status StrEnum 은 소문자("draft"/"proposed") — 공개 계약은 대문자로 정규화(spec §5).
    return {"artifact_id": aid, "status": art.meta["status"].upper(), "provenance_carried": True}
