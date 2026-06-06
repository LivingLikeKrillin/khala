from __future__ import annotations

from collections.abc import Callable

from .artifacts import Artifact, ArtifactType, Status
from .errors import ReviewError
from .sidecar import Sidecar

_VALID = {"accepted", "rejected", "deferred"}


def approve(ledger, artifact_id, dispositions, approver, now: Callable[[], str]) -> None:
    art = Artifact.load(ledger._resolve(artifact_id))
    sc_path = ledger.reviews / f"{art.id}.md"
    if not sc_path.exists():
        raise ReviewError(f"no critique sidecar for {art.id}; run critique first")
    sc = Sidecar.read(sc_path)

    by_id = {d["issue_id"]: d for d in dispositions}
    open_issues = [i for i in sc.issues if i.status == "open"]
    missing = [i.issue_id for i in open_issues if i.issue_id not in by_id]
    if missing:
        raise ReviewError(f"undispositioned issues: {missing}")

    has_accept = False
    for i in open_issues:
        d = by_id[i.issue_id]
        disp = d.get("disposition")
        if disp not in _VALID:
            raise ReviewError(f"invalid disposition for {i.issue_id}: {disp}")
        if disp in ("rejected", "deferred") and not (d.get("reason") or "").strip():
            raise ReviewError(f"{disp} requires a reason for {i.issue_id}")
        has_accept = has_accept or disp == "accepted"

    if has_accept and art.recompute_hash() == sc.critiqued_hash:
        raise ReviewError("accepted 했으나 문서 미수정 (본문 해시 불변)")

    for i in sc.issues:
        # only mutate issues that were actually open and dispositioned this round;
        # never overwrite an already-closed issue's historical record
        if i.status == "open" and i.issue_id in by_id:
            i.status = by_id[i.issue_id]["disposition"]
            i.disposition_reason = by_id[i.issue_id].get("reason")
    sc.approved_by = approver
    sc.approved_at = now()

    final = Status.ACCEPTED if art.type is ArtifactType.ADR else Status.APPROVED
    art.meta["status"] = str(final)
    art.meta["approved_by"] = approver
    art.meta["reviewed_at"] = now()
    art.meta["content_hash"] = art.recompute_hash()

    sc.write(sc_path)
    art.save()
