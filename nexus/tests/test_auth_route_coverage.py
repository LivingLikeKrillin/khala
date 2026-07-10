"""Guard: every privileged route resolves a principal; /status and / do not.

Introspects the live FastAPI app (no DB needed) so a newly-added endpoint that touches the
tenant corpus cannot silently regress the access-control boundary.

Routers that live outside `nexus.api` (documents, sources) cannot import `get_principal`
without a circular import, so they declare a placeholder dependency and the app wires it
through `dependency_overrides`. That indirection is accepted **only when the override is
actually installed and points at `get_principal`** — an unwired placeholder raises 500,
but a placeholder pointing somewhere else would be an open door, so the guard checks it.
"""

from __future__ import annotations

from nexus.api import app, get_principal

# Every route that reads the tenant corpus (base_filter / hybrid_search) or writes to it.
PRIVILEGED = {
    "/search", "/search/answer", "/search/answer/stream", "/graph/{entity_rid_param}",
    "/diff", "/documents", "/documents/{rid}", "/entities/suggest",
    "/claims/value", "/claims/grade-authority",
    "/ingest", "/upload", "/otel/aggregate", "/supersede",
    "/documents/{rid}/hide", "/documents/{rid}/restore", "/documents/{rid}/unsupersede",
    "/sources/notion/roots", "/sources/notion/roots/{root_id}",
    "/sources/notion/sync", "/sources/notion/sync/{run_id}", "/sources/notion/sync/latest",
}
# Discovery / static / dev-onramp — intentionally unauthenticated.
# /auth/dev-token returns the local dev token *before* a principal exists (env-gated; null in prod).
UNGATED = {"/status", "/", "/auth/dev-token"}


def _declares(route, dep) -> bool:
    """Recursively flatten the route's dependant tree (signature or dependencies=[...])."""
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return False
    stack = [dependant]
    while stack:
        d = stack.pop()
        if getattr(d, "call", None) is dep:
            return True
        stack.extend(d.dependencies)
    return False


def _routes_by_path() -> dict[str, list]:
    out: dict[str, list] = {}
    for r in app.routes:
        path = getattr(r, "path", None)
        if path is not None:
            out.setdefault(path, []).append(r)
    return out


def _resolves_principal(route) -> bool:
    """Directly declares get_principal, or a placeholder that the app overrides with it."""
    if _declares(route, get_principal):
        return True
    for placeholder, target in app.dependency_overrides.items():
        if target is get_principal and _declares(route, placeholder):
            return True
    return False


def test_every_privileged_route_requires_principal():
    by_path = _routes_by_path()
    missing = []
    for path in PRIVILEGED:
        routes = by_path.get(path)
        assert routes, f"privileged route not found in app: {path}"
        for r in routes:
            if not _resolves_principal(r):
                missing.append(path)
    assert not missing, f"privileged routes do not resolve a principal: {sorted(set(missing))}"


def test_an_unwired_placeholder_would_be_caught():
    """가드가 실제로 무는지 확인한다 — override 를 떼면 그 라우트는 실패해야 한다."""
    from nexus.documents.api import dep as documents_dep

    saved = app.dependency_overrides.pop(documents_dep)
    try:
        hide = _routes_by_path()["/documents/{rid}/hide"][0]
        assert not _resolves_principal(hide)
    finally:
        app.dependency_overrides[documents_dep] = saved


def test_status_and_ui_are_not_gated():
    by_path = _routes_by_path()
    for path in UNGATED:
        for r in by_path.get(path, []):
            assert not _declares(r, get_principal), f"{path} should stay unauthenticated"
