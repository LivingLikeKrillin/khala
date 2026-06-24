"""FastAPI app — the 5 endpoints of the ken-web repayment slice over `ken.service`.

Each handler resolves storage paths from `deps` and constructs the LLM via
`deps.make_llm()` at REQUEST TIME (the test seam). Error mapping:
  - unknown artifact / question id (`KeyError`) -> 404
  - storage write failure (`OSError`) -> 500 (fail-loud; never silently drop)
Grade LLM failure is fail-closed inside `ken.service` (passed=False); remediation
LLM failure yields `remediation=None` there. Neither surfaces as an HTTP error.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ken import service

from . import deps
from .schemas import (
    ArtifactDetailOut,
    ArtifactOut,
    AttemptOut,
    AttemptReq,
    CoverageOut,
    DueOut,
    QuestionDetailOut,
    QuestionOut,
    RegisterReq,
    WeaknessOut,
)

app = FastAPI(title="ken-web API", version="0.1.0")

# Permissive CORS for the Vite dev server (same-origin in prod -> no CORS needed).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/artifacts", response_model=list[ArtifactOut])
def list_artifacts() -> list[ArtifactOut]:
    store = deps.make_store()
    rows = service.list_artifacts(store=store, now=service.now_iso())
    return [
        ArtifactOut(
            artifact_id=r.artifact_id, path=r.path, status=r.status, weak_count=r.weak_count
        )
        for r in rows
    ]


@app.post("/api/artifacts", response_model=ArtifactOut, status_code=201)
def register_artifact(req: RegisterReq) -> ArtifactOut:
    # ONE store for both service calls (register then list) within this request.
    store = deps.make_store()
    service.register_artifact(req.path, store=store)
    # Re-derive the status row so the response carries vouched/orphan + weak_count.
    rows = service.list_artifacts(store=store, now=service.now_iso())
    row = next(r for r in rows if r.path == req.path)
    return ArtifactOut(
        artifact_id=row.artifact_id, path=row.path, status=row.status, weak_count=row.weak_count
    )


@app.get("/api/artifacts/{artifact_id}/due", response_model=DueOut)
def get_due(artifact_id: str) -> DueOut:
    """Generate+save questions if missing/stale (non-idempotent), then list due ones."""
    store = deps.make_store()
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
def get_detail(artifact_id: str) -> ArtifactDetailOut:
    """Read-only per-question schedule rows. No generation, no LLM."""
    store = deps.make_store()
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
def post_attempt(req: AttemptReq) -> AttemptOut:
    store = deps.make_store()
    try:
        result = service.grade_answer(
            req.artifact_id,
            req.question_id,
            req.answer,
            person=req.person,
            store=store,
            llm=deps.make_llm(),
            now=service.now_iso(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown id: {exc.args[0]}") from exc
    except OSError as exc:
        # Fail-loud: storage write failed -> never silently drop the attempt.
        raise HTTPException(status_code=500, detail="storage write failed") from exc
    return AttemptOut(
        passed=result.passed, score=result.score, remediation=result.remediation
    )


@app.get("/api/coverage", response_model=CoverageOut)
def get_coverage() -> CoverageOut:
    store = deps.make_store()
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
