"""소스 콘솔 HTTP 표면 (SPEC-nexus-notion-source-console §4.6).

여기가 **정본**이다. 웹 뷰·MCP 툴·CLI 는 전부 이 엔드포인트 위의 얇은 클라이언트다.
기능이 API 를 건너뛰면 사람도 에이전트도 그 기능을 잃는다.

실패 표면을 일부러 둘로 가른다(§4.6):
  · 일을 시작하기 **전에** 알 수 있는 것 → 동기 4xx/503, run 행을 만들지 않는다.
  · 걷는 **도중에** 드러나는 것 → 이미 만들어진 run 의 종료 상태(refused/failed).
"""

from __future__ import annotations

import os

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from nexus.auth import Principal, effective_scope
from nexus.sources import roots_store, runs_store
from nexus.sources.errors import DuplicateRoot
from nexus.sources.notion_health import ConnectionHealth, RootState, probe_connection

MANAGE_SOURCES = "manage_sources"

router = APIRouter(prefix="/sources/notion", tags=["sources"])


def dep() -> Principal:  # pragma: no cover - 항상 override 된다
    """principal 해석 주입 지점.

    `get_principal` 은 auth config 를 물고 api.py 에서 만들어진다. 여기서 직접 임포트하면
    순환이 되므로, 앱(과 테스트)이 `dependency_overrides[dep]` 로 실제 해석기를 꽂는다.
    꽂히지 않은 채 라우터가 마운트되면 조용히 무인증으로 열리는 대신 500 으로 죽는다.
    """
    raise HTTPException(status_code=500, detail="principal dependency not wired")


class _Envelope(BaseModel):
    success: bool = True
    data: object = None
    error: str | None = None
    meta: dict = {}


class AddRootRequest(BaseModel):
    url_or_id: str
    label: str = ""


class SyncRequest(BaseModel):
    reconcile: bool = False
    dry_run: bool = False
    force: bool = False
    since: str = ""
    threshold: float = 0.5
    confirm_plan: str | None = None


def _require(principal: Principal, capability: str) -> None:
    if not principal.has(capability):
        raise HTTPException(status_code=403, detail=f"capability required: {capability}")


def _tenant(principal: Principal) -> str:
    tenant, _ = effective_scope(principal, None, None)
    return tenant


def _notion_configured() -> bool:
    return bool(os.getenv("NOTION_TOKEN"))


# ── roots ─────────────────────────────────────────────────────────────────────

@router.get("/roots", response_model=_Envelope)
async def list_roots(principal: Principal = Depends(dep)) -> _Envelope:
    tenant = _tenant(principal)
    roots = await roots_store.list_roots(tenant)
    for r in roots:
        r["added_at"] = r["added_at"].isoformat()
    return _Envelope(data={"roots": roots, "token_configured": _notion_configured()})


def _health_dict(h: ConnectionHealth) -> dict:
    """응답 모양을 여기서 못 박는다. 자유 텍스트 필드가 없다 — `str(e)` 가 끼어들 자리가 없다."""
    return {
        "token": {"state": h.token.state.value, "integration": h.token.integration,
                  "workspace": h.token.workspace, "prefix": h.token.prefix},
        "roots": [{"root_id": r.root_id, "state": r.state.value,
                   "title": r.title, "remedy": r.remedy} for r in h.roots],
        "checked_at": h.checked_at,
    }


@router.get("/health", response_model=_Envelope)
async def health(principal: Principal = Depends(dep)) -> _Envelope:
    """토큰이 진짜인가, 등록된 root 에 정말 닿는가. Notion 에게 직접 묻는다.

    ⚠️ `manage_sources` 뒤에 있다. 토큰만 비밀이 아니다 — 워크스페이스 이름과 문서 제목은
    조직 문서 트리의 모양을 드러낸다. Cloudflare Access 는 망 경계를, capability 는
    엔드포인트를 지킨다. 서로를 대신하지 않는다.

    Notion 이 통째로 죽어도 200 을 준다. 진단이 진단 대상과 함께 죽으면 정작 필요할 때 쓸모없다.
    """
    _require(principal, MANAGE_SOURCES)
    tenant = _tenant(principal)
    roots = [r["root_id"] for r in await roots_store.list_roots(tenant)]
    h = await probe_connection(os.getenv("NOTION_TOKEN", ""), roots)
    return _Envelope(data=_health_dict(h))


@router.post("/roots", response_model=_Envelope, status_code=201)
async def add_root(req: AddRootRequest, principal: Principal = Depends(dep)) -> _Envelope:
    """root 를 등록하고, 지금 그 페이지에 닿는지 **말해 준다**. 거부하지는 않는다.

    등록하고 나서 Notion 에서 공유하는 것은 정상 순서다(URL 을 붙여넣고, 가서 연결을 추가한다).
    게다가 Notion 은 '아직 공유 안 된 페이지' 와 '없는 페이지' 를 똑같이 404 로 답한다 —
    잡아내지도 못하는 오타를 막겠다고 멀쩡한 흐름을 깨뜨릴 이유가 없다 (SPEC §4.4).
    """
    _require(principal, MANAGE_SOURCES)
    try:
        root_id = await roots_store.add_root(_tenant(principal), req.url_or_id, req.label)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except DuplicateRoot as e:
        raise HTTPException(status_code=409, detail=f"root already registered: {e}") from e

    probed = (await probe_connection(os.getenv("NOTION_TOKEN", ""), [root_id])).roots[0]
    return _Envelope(
        data={"root_id": root_id, "state": probed.state.value,
              "title": probed.title, "remedy": probed.remedy},
        meta={"probed": probed.state is not RootState.UNKNOWN},
    )


@router.delete("/roots/{root_id}", response_model=_Envelope)
async def remove_root(root_id: str, principal: Principal = Depends(dep)) -> _Envelope:
    _require(principal, MANAGE_SOURCES)
    try:
        removed = await roots_store.remove_root(_tenant(principal), root_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not removed:
        raise HTTPException(status_code=404, detail="root not registered")
    # 문서는 건드리지 않는다. 걷지 않게 될 뿐이고, containment 때문에 prune 후보에서도 빠진다.
    return _Envelope(
        data={"root_id": root_id, "documents_deleted": 0},
        meta={"note": "root unregistered; its documents remain indexed and are no longer walked"},
    )


# ── sync ──────────────────────────────────────────────────────────────────────

def _validate_sync(req: SyncRequest) -> None:
    if req.confirm_plan is None:
        return
    # 확정은 저장된 run 의 조건을 그대로 재생한다. 다른 파라미터를 함께 받으면
    # 미리보기와 다른 조건으로 적용될 수 있다 (I-006).
    conflicting = [
        name for name, value in (
            ("reconcile", req.reconcile), ("dry_run", req.dry_run),
            ("force", req.force), ("since", bool(req.since)),
        ) if value
    ]
    if conflicting:
        raise HTTPException(
            status_code=400,
            detail=f"confirm_plan cannot be combined with: {', '.join(conflicting)}",
        )


@router.post("/sync", response_model=_Envelope, status_code=202)
async def start_sync(req: SyncRequest, principal: Principal = Depends(dep)) -> _Envelope:
    _require(principal, MANAGE_SOURCES)
    _validate_sync(req)
    tenant = _tenant(principal)

    if not _notion_configured():
        raise HTTPException(status_code=503, detail="notion_not_configured")

    if req.confirm_plan is not None:
        prior = await runs_store.get_run(req.confirm_plan)
        if prior is None or prior["tenant"] != tenant:
            raise HTTPException(status_code=404, detail="unknown run")
        if not prior["dry_run"] or prior["status"] != "succeeded":
            raise HTTPException(status_code=400, detail="confirm_plan must reference a completed dry run")
        roots = list(prior["walked_roots"])
        params = dict(reconcile=True, dry_run=False, force=prior["force"], since=prior["since"])
    else:
        roots = [r["root_id"] for r in await roots_store.list_roots(tenant)]
        if not roots:
            raise HTTPException(status_code=400, detail="no roots registered")
        params = dict(reconcile=req.reconcile, dry_run=req.dry_run, force=req.force, since=req.since)

    if (running := await runs_store.running_run_id(tenant)) is not None:
        raise HTTPException(status_code=409, detail=f"sync_in_progress: {running}")

    try:
        run_id = await runs_store.create_run(tenant, walked_roots=roots, **params)
    except asyncpg.UniqueViolationError as e:  # lock 을 우회한 경쟁 — DB 백스톱이 잡는다
        running = await runs_store.running_run_id(tenant)
        raise HTTPException(status_code=409, detail=f"sync_in_progress: {running}") from e

    from nexus.sources.sync_job import spawn_sync

    spawn_sync(
        run_id=run_id, tenant=tenant, roots=roots, threshold=req.threshold,
        confirm_run=req.confirm_plan, **params,
    )
    return _Envelope(data={"run_id": run_id, "status": "running"})


@router.get("/sync/latest", response_model=_Envelope)
async def sync_latest(principal: Principal = Depends(dep)) -> _Envelope:
    run = await runs_store.latest_run(_tenant(principal))
    if run is None:
        raise HTTPException(status_code=404, detail="no runs yet")
    return _Envelope(data=_public(run))


@router.get("/sync/{run_id}", response_model=_Envelope)
async def sync_status(run_id: str, principal: Principal = Depends(dep)) -> _Envelope:
    run = await runs_store.get_run(run_id)
    if run is None or run["tenant"] != _tenant(principal):
        raise HTTPException(status_code=404, detail="unknown run")
    return _Envelope(data=_public(run))


def _public(run: dict) -> dict:
    out = dict(run)
    for k in ("started_at", "finished_at"):
        if out.get(k) is not None:
            out[k] = out[k].isoformat()
    out["walked_roots"] = list(out.get("walked_roots") or [])
    return out
