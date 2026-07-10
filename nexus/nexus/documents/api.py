"""문서 생애주기 HTTP 표면 (SPEC-nexus-document-lifecycle §4.4).

엔드포인트가 정본이다. 웹 뷰·MCP 툴·CLI 는 전부 이 위의 얇은 클라이언트다.

**모든 파괴적 행위에는 역이 있다.** hide↔restore, supersede↔unsupersede.
그리고 전부 `manage_documents` capability 뒤에 있다 — `/supersede` 는 지금까지
무권한이었다(인증만 하면 누구나 문서를 검색에서 지웠다).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from nexus import db
from nexus.auth import Principal, effective_scope
from nexus.documents.filters import ORIGIN_FILTERS, STATUS_FILTERS, reportable_status
from nexus.documents.lifecycle_ops import (
    AlreadySuperseded,
    UseUnsupersede,
    hide_document,
    restore_document,
)
from nexus.documents.origin import derive_origin
from nexus.lifecycle import ChainBroken, unsupersede

MANAGE_DOCUMENTS = "manage_documents"

router = APIRouter(tags=["documents"])


def dep() -> Principal:  # pragma: no cover - 항상 override 된다
    """principal 해석 주입 지점 (nexus.api 순환 회피). 안 꽂히면 500 — 무인증으로 열리지 않는다."""
    raise HTTPException(status_code=500, detail="principal dependency not wired")


class _Envelope(BaseModel):
    success: bool = True
    data: object = None
    error: str | None = None
    meta: dict = {}


class UnsupersedeRequest(BaseModel):
    reason: str = ""


class SupersedeRequest(BaseModel):
    old_ref: str
    new_ref: str
    tenant: str = "default"


def _require(principal: Principal) -> None:
    if not principal.has(MANAGE_DOCUMENTS):
        raise HTTPException(status_code=403, detail=f"capability required: {MANAGE_DOCUMENTS}")


def _scope(principal: Principal, tenant: str | None = None, clearance: str | None = None):
    return effective_scope(principal, tenant, clearance)


@router.get("/documents", response_model=_Envelope)
async def list_documents(
    tenant: str = Query(default="default"),
    classification_max: str = Query(default="INTERNAL"),
    q: str = Query(default="", description="제목 부분일치 (내용 검색이 아니다 — /search 를 쓰라)"),
    status: str = Query(default="active"),
    origin: str = Query(default=""),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(dep),
) -> _Envelope:
    tenant, classification_max = _scope(principal, tenant, classification_max)
    if status not in STATUS_FILTERS:
        raise HTTPException(status_code=400, detail=f"unknown status filter: {status}")
    if origin and origin not in ORIGIN_FILTERS:
        raise HTTPException(status_code=400, detail=f"unknown origin filter: {origin}")

    # 모든 필터는 SQL 에 있다. 파이썬에서 사후 필터링하면 limit 만큼 뽑은 뒤 버리게 되어
    # 페이지가 조용히 줄고 total 이 거짓말한다.
    where = f"""
        d.tenant = $1
          AND d.classification <= $2::classification_level
          AND d.is_quarantined = false
          AND ({STATUS_FILTERS[status]})
          AND ($3 = '' OR d.title ILIKE '%' || $3 || '%')
          AND ({ORIGIN_FILTERS[origin] if origin else 'TRUE'})
    """

    rows = await db.fetch_all(
        f"""
        SELECT d.rid, d.title, d.source_uri, d.classification, d.doc_type, d.language,
               d.status::text AS status, d.hold, d.superseded_by, d.updated_at,
               s.title AS superseded_by_title,
               (SELECT COUNT(*) FROM chunks c WHERE c.doc_rid = d.rid AND c.status='active')
                   AS chunk_count
        FROM documents d
        -- 대체한 문서의 **제목**. rid 만 보여주면 사람은 그게 무슨 문서인지 알 수 없다.
        LEFT JOIN documents s ON s.rid = d.superseded_by AND s.tenant = d.tenant
        WHERE {where}
        ORDER BY d.updated_at DESC
        OFFSET $4 LIMIT $5
        """,
        tenant, classification_max, q, offset, limit,
    )
    total = await db.fetch_val(
        f"SELECT COUNT(*) FROM documents d WHERE {where}", tenant, classification_max, q)

    docs = []
    for r in rows:
        item = dict(r)
        item["origin"], item["origin_url"] = derive_origin(item["source_uri"])
        item["status"] = reportable_status(item["status"], item["hold"])
        item["updated_at"] = item["updated_at"].isoformat()
        docs.append(item)

    return _Envelope(data={"documents": docs, "total": total, "offset": offset, "limit": limit})


@router.get("/documents/{rid}", response_model=_Envelope)
async def get_document(rid: str, principal: Principal = Depends(dep)) -> _Envelope:
    tenant, _ = _scope(principal)
    row = await db.fetch_one(
        "SELECT rid, title, source_uri, classification, doc_type, language, "
        "status::text AS status, hold, superseded_by, updated_at, "
        "(SELECT COUNT(*) FROM chunks c WHERE c.doc_rid = documents.rid AND c.status='active') "
        "AS chunk_count FROM documents WHERE rid=$1 AND tenant=$2",
        rid, tenant,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="unknown document")
    item = dict(row)
    item["origin"], item["origin_url"] = derive_origin(item["source_uri"])
    item["status"] = reportable_status(item["status"], item["hold"])
    item["updated_at"] = item["updated_at"].isoformat()
    return _Envelope(data=item)


@router.post("/documents/{rid}/hide", response_model=_Envelope)
async def hide(rid: str, principal: Principal = Depends(dep)) -> _Envelope:
    _require(principal)
    tenant, _ = _scope(principal)
    try:
        result = await hide_document(rid, tenant)
    except AlreadySuperseded as e:
        raise HTTPException(status_code=409, detail="already_superseded") from e
    return _Envelope(
        data={"rid": rid, "result": result},
        meta={"note": "검색에서 사라집니다. 문서와 청크는 지워지지 않으며 언제든 되돌릴 수 있습니다."},
    )


@router.post("/documents/{rid}/restore", response_model=_Envelope)
async def restore(rid: str, principal: Principal = Depends(dep)) -> _Envelope:
    _require(principal)
    tenant, _ = _scope(principal)
    try:
        result = await restore_document(rid, tenant)
    except UseUnsupersede as e:
        raise HTTPException(status_code=409, detail="use_unsupersede") from e
    return _Envelope(data={"rid": rid, "result": result})


@router.post("/documents/{rid}/unsupersede", response_model=_Envelope)
async def undo_supersede(
    rid: str, req: UnsupersedeRequest, principal: Principal = Depends(dep)
) -> _Envelope:
    _require(principal)
    tenant, _ = _scope(principal)
    try:
        result = await unsupersede(rid, tenant, reason=req.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="reason_required") from e
    except ChainBroken as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return _Envelope(data={"rid": rid, "result": result})


@router.post("/supersede", response_model=_Envelope)
async def supersede_docs(req: SupersedeRequest, principal: Principal = Depends(dep)) -> _Envelope:
    """옛 문서를 새 문서로 대체한다 — **파괴적**. 역명령: /documents/{rid}/unsupersede.

    ⚠️ 이 엔드포인트는 지금까지 capability 게이트가 없었다. 이제 manage_documents 를 요구한다.
    명시 설정된 principal(예: MCP 의 NEXUS_MCP_TOKEN)은 그 capability 를 받기 전까지 403 이다.
    """
    _require(principal)
    from nexus.supersede import resolve_active_doc, supersede

    tenant, _ = _scope(principal, req.tenant, None)
    try:
        old_rid = await resolve_active_doc(req.old_ref, tenant)
        new_rid = await resolve_active_doc(req.new_ref, tenant)
        result = await supersede(old_rid, new_rid, tenant)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    # 해석된 rid 를 돌려준다: 되돌리려면(unsupersede) rid 가 필요한데, 그때 옛 문서는 이미
    # active 가 아니라 경로로 다시 찾을 수 없다. 파괴한 자리에서 손잡이를 함께 준다.
    return _Envelope(
        data={"result": result, "old_rid": old_rid, "new_rid": new_rid},
        meta={"undo": f"POST /documents/{old_rid}/unsupersede (reason 필수)"},
    )
