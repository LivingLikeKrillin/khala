"""effective_scope — the single 'narrow-only' clamp.

The ONLY producer of the ``(tenant, clearance)`` that may reach ``hybrid_search`` /
``base_filter``. Raw request-supplied ``tenant`` / ``classification_max`` must never flow
downstream; they pass through here first.
"""

from __future__ import annotations

from .clearance import floor_public, min_level
from .principal import Principal


def effective_scope(
    principal: Principal,
    requested_tenant: str | None = None,
    requested_clearance: str | None = None,
) -> tuple[str, str]:
    """Resolve the effective ``(tenant, clearance)`` for a request.

    - ``tenant`` is always the principal's; a requested tenant is **ignored** (tenant
      isolation — and no tenant-existence leak).
    - ``clearance`` = ``min(principal.clearance, floor_public(requested_clearance))``. A
      missing request keeps the principal's ceiling; an invalid/typo'd value floors to
      ``PUBLIC``. It can only narrow, never widen.
    """
    tenant = principal.tenant
    if requested_clearance is None:
        clearance = principal.clearance
    else:
        clearance = min_level(principal.clearance, floor_public(requested_clearance))
    return tenant, clearance
