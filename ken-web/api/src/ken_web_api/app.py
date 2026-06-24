"""FastAPI app — the 5 endpoints of the ken-web repayment slice over `ken.service`.

Each handler resolves storage paths from `deps` and constructs the LLM via
`deps.make_llm()` at REQUEST TIME (the test seam). Error mapping:
  - unknown artifact / question id (`KeyError`) -> 404
  - storage write failure (`OSError`) -> 500 (fail-loud; never silently drop)
Grade LLM failure is fail-closed inside `ken.service` (passed=False); remediation
LLM failure yields `remediation=None` there. Neither surfaces as an HTTP error.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ken import service
from ken.schedule import _parse_ts

from . import deps
from .schemas import (
    ArtifactDetailOut,
    ArtifactOut,
    AttemptOut,
    AttemptReq,
    CoverageOut,
    DueOut,
    LoginReq,
    MeOut,
    QuestionDetailOut,
    QuestionOut,
    RegisterReq,
    WeaknessOut,
)
from .security import DUMMY_HASH, new_session_token, verify_password

logger = logging.getLogger("ken_web_api")

app = FastAPI(title="ken-web API", version="0.1.0")

# Permissive CORS for the Vite dev server (same-origin in prod -> no CORS needed).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _auth_startup_guard() -> None:
    if deps.auth_enabled() and not os.getenv("KEN_DATABASE_URL"):
        raise RuntimeError("KEN_AUTH=1 requires KEN_DATABASE_URL (Postgres)")
    logger.info("auth: %s", "ENABLED" if deps.auth_enabled() else "OFF")


@dataclass(frozen=True)
class Principal:
    email: str
    tenant_slug: str


def require_user(request: Request) -> Principal:
    """Return the caller's Principal{email, tenant_slug}. 401 when auth is on and no valid session."""
    if not deps.auth_enabled():
        return Principal(deps.DEFAULT_PERSON, deps.DEFAULT_TENANT)
    token = request.cookies.get(deps.SESSION_COOKIE)
    user = deps.make_auth_store().user_for_session(token, now=service.now_iso()) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return Principal(user.email, user.tenant_slug)


@app.post("/api/auth/login", response_model=MeOut)
def login(req: LoginReq, response: Response) -> MeOut:
    if not deps.auth_enabled():
        raise HTTPException(status_code=400, detail="auth disabled")
    store = deps.make_auth_store()
    found = store.get_user_by_email(req.email)
    # Constant-time across branches: always run one verify (DUMMY_HASH if unknown).
    ok = verify_password(found[1] if found else DUMMY_HASH, req.password)
    if not found or not ok:
        raise HTTPException(status_code=401, detail="invalid email or password")
    token = new_session_token()
    expires = (_parse_ts(service.now_iso()) + timedelta(days=deps.SESSION_TTL_DAYS)).isoformat()
    store.create_session(found[0].id, token, expires)
    response.set_cookie(
        deps.SESSION_COOKIE, token, httponly=True, samesite="lax", path="/",
        secure=os.getenv("KEN_COOKIE_SECURE") == "1",
        max_age=deps.SESSION_TTL_DAYS * 86400,
    )
    return MeOut(email=found[0].email)


@app.post("/api/auth/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    # Apply cookie-deletion to the INJECTED response (returning a new Response
    # would drop the Set-Cookie). Returning None → FastAPI sends 204 with this
    # response's headers. delete_cookie uses the same path the cookie was set with.
    token = request.cookies.get(deps.SESSION_COOKIE)
    if token:
        deps.make_auth_store().delete_session(token)
    response.delete_cookie(deps.SESSION_COOKIE, path="/")
    return None


@app.get("/api/auth/me", response_model=MeOut)
def me(principal: Principal = Depends(require_user)) -> MeOut:
    return MeOut(email=principal.email)


@app.get("/api/artifacts", response_model=list[ArtifactOut])
def list_artifacts(principal: Principal = Depends(require_user)) -> list[ArtifactOut]:
    store = deps.make_store(principal.tenant_slug)
    rows = service.list_artifacts(store=store, now=service.now_iso())
    return [
        ArtifactOut(
            artifact_id=r.artifact_id, path=r.path, status=r.status, weak_count=r.weak_count
        )
        for r in rows
    ]


@app.post("/api/artifacts", response_model=ArtifactOut, status_code=201)
def register_artifact(req: RegisterReq, principal: Principal = Depends(require_user)) -> ArtifactOut:
    # ONE store for both service calls (register then list) within this request.
    store = deps.make_store(principal.tenant_slug)
    service.register_artifact(req.path, store=store)
    # Re-derive the status row so the response carries vouched/orphan + weak_count.
    rows = service.list_artifacts(store=store, now=service.now_iso())
    row = next(r for r in rows if r.path == req.path)
    return ArtifactOut(
        artifact_id=row.artifact_id, path=row.path, status=row.status, weak_count=row.weak_count
    )


@app.get("/api/artifacts/{artifact_id}/due", response_model=DueOut)
def get_due(artifact_id: str, principal: Principal = Depends(require_user)) -> DueOut:
    """Generate+save questions if missing/stale (non-idempotent), then list due ones."""
    store = deps.make_store(principal.tenant_slug)
    try:
        service.ensure_questions(
            artifact_id,
            store=store,
            llm=deps.make_llm(),
            n=deps.N_QUESTIONS,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown artifact_id: {artifact_id}") from exc

    lines = service.due_items(store=store, now=service.now_iso())
    line = next((ln for ln in lines if ln.artifact_id == artifact_id), None)
    if line is None:
        raise HTTPException(status_code=404, detail=f"unknown artifact_id: {artifact_id}")
    questions = [QuestionOut(question_id=qid, text=text) for qid, text in line.questions]
    return DueOut(questions=questions)


@app.get("/api/artifacts/{artifact_id}/detail", response_model=ArtifactDetailOut)
def get_detail(artifact_id: str, principal: Principal = Depends(require_user)) -> ArtifactDetailOut:
    """Read-only per-question schedule rows. No generation, no LLM."""
    store = deps.make_store(principal.tenant_slug)
    try:
        rows = service.artifact_detail(artifact_id, store=store, now=service.now_iso())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown artifact_id: {artifact_id}") from exc
    return ArtifactDetailOut(
        questions=[
            QuestionDetailOut(
                question_id=r.question_id, text=r.text, rung=r.rung, attempted=r.attempted,
                last_passed=r.last_passed, last_ts=r.last_ts, fail_count=r.fail_count,
                next_due=r.next_due, due=r.due,
            )
            for r in rows
        ]
    )


@app.post("/api/attempts", response_model=AttemptOut)
def post_attempt(req: AttemptReq, principal: Principal = Depends(require_user)) -> AttemptOut:
    store = deps.make_store(principal.tenant_slug)
    try:
        result = service.grade_answer(
            req.artifact_id, req.question_id, req.answer,
            person=principal.email,              # server-derived, not client-supplied
            store=store, llm=deps.make_llm(), now=service.now_iso(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown id: {exc.args[0]}") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="storage write failed") from exc
    return AttemptOut(passed=result.passed, score=result.score, remediation=result.remediation)


@app.get("/api/coverage", response_model=CoverageOut)
def get_coverage(principal: Principal = Depends(require_user)) -> CoverageOut:
    store = deps.make_store(principal.tenant_slug)
    rep = service.coverage_report(store=store, now=service.now_iso())
    return CoverageOut(
        total=rep.total,
        covered=rep.covered,
        ratio=rep.ratio,
        orphans=rep.orphans,
        weakness=[
            WeaknessOut(
                question_id=w.question_id, artifact_id=w.artifact_id, fail_count=w.fail_count
            )
            for w in rep.weakness
        ],
    )


# --- prod single-origin static serve -------------------------------------------
# In production the built SPA (`ken-web/web/dist`) is served at `/` so the API and
# UI share one origin (no CORS). The `/api/*` routes above are registered first and
# therefore take precedence; the catch-all mount only handles the rest. `html=True`
# falls back to index.html for client-side routes. The mount is GUARDED: when
# `dist/` is absent (dev with the Vite proxy, or automated tests) this is a no-op,
# so the app never crashes on a missing build.
_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="spa")
