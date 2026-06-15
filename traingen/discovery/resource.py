"""Shared resource-noun derivation for the Layer 1 join key (reconcile on resource_hint,
DISCOVERY §4). Endpoints and routes MUST use the same rule or they won't join.

API paths nest the resource under scope/plumbing segments — `/api/v1/admin/analytics/leads`,
`/api/v1/member/me/bookings/{id}/cancel` — and frontend routes nest under role/nav segments —
`/admin/dashboard/leads`. Taking the first path segment yields `admin`/`member` and collapses
every feature into one group. Instead, strip a configurable scope set and version segments,
then take the first remaining segment as the resource noun.
"""
from __future__ import annotations

import re

# Not resources — API plumbing, role scopes, and nav containers.
DEFAULT_SCOPE_SEGMENTS = ["api", "admin", "member", "me", "dashboard", "portal", "auth"]
_VERSION = re.compile(r"^v\d+$")


def resource_hint(segments, scope_segments=None) -> str:
    scope = set(scope_segments or DEFAULT_SCOPE_SEGMENTS)
    plain = [s for s in segments if s]
    candidates = [s for s in plain if not _VERSION.match(s) and s not in scope]
    if candidates:
        return candidates[0]
    return plain[-1] if plain else "root"   # all-scope path (e.g. /api/v1/member/me)
