"""Guard: every privileged route declares get_principal; /status and / do not.

Introspects the live FastAPI app (no DB needed) so a newly-added endpoint that touches the
tenant corpus cannot silently regress the access-control boundary.
"""

from __future__ import annotations

from nexus.api import app, get_principal

# Every route that reads the tenant corpus (base_filter / hybrid_search) or writes to it.
PRIVILEGED = {
    "/search", "/search/answer", "/search/answer/stream", "/graph/{entity_rid_param}",
    "/diff", "/documents", "/entities/suggest", "/claims/value", "/claims/grade-authority",
    "/ingest", "/upload", "/otel/aggregate",
}
# Discovery / static — intentionally unauthenticated.
UNGATED = {"/status", "/"}


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


def test_every_privileged_route_requires_principal():
    by_path = _routes_by_path()
    missing = []
    for path in PRIVILEGED:
        routes = by_path.get(path)
        assert routes, f"privileged route not found in app: {path}"
        for r in routes:
            if not _declares(r, get_principal):
                missing.append(path)
    assert not missing, f"privileged routes missing get_principal: {sorted(set(missing))}"


def test_status_and_ui_are_not_gated():
    by_path = _routes_by_path()
    for path in UNGATED:
        for r in by_path.get(path, []):
            assert not _declares(r, get_principal), f"{path} should stay unauthenticated"
