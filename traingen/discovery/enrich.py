"""Layer: visual discovery enrichment (MULTIMODAL.md C2 / roadmap M3).

A screenshot crawl that augments the inventory with semantics the code parser cannot give:
what feature a route is, what a user can do, the primary action, and the **rendered** UI
nouns (bridging API-noun <-> UI-noun, reading the shown BG/EN instead of i18n keys).
Framework-agnostic by construction — it reads a screenshot + the accessibility snapshot, not
the Next.js tree — which is what lets TrainGen comprehend apps we didn't write a parser for.

Output: `out/discovery/visual_features.json`, a SIDECAR with provenance `crawl-only`. It
NEVER feeds the Layer-1 `inventory_hash` (DESIGN R7 / MULTIMODAL Principle 1), so Layer 1
stays byte-deterministic. Vision calls are cached on the screenshot hash so re-runs are free.

Offline-testable: pass a stub `vision_backend` + a fake `make_driver`. The live crawl needs
a running app + ANTHROPIC_API_KEY (and the admin key for admin routes).
"""
from __future__ import annotations

import hashlib
import json

from .. import config as prod_config

DISCOVERY_DIR = prod_config.OUT / "discovery"
ENRICH_CACHE = DISCOVERY_DIR / "enrich_cache"

# One page -> objective feature description. Kept small (vision is token-heavy).
VISUAL_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "feature_title": {"type": "string"},     # short human name, e.g. "Interactive partner map"
        "summary": {"type": "string"},            # 1-2 sentences: what it is + who uses it
        "user_actions": {"type": "array", "items": {"type": "string"}},
        "primary_action": {"type": "string"},     # the single main call-to-action
        "ui_nouns": {"type": "array", "items": {"type": "string"}},  # domain nouns AS RENDERED
        "rendered_language": {"type": "string"},  # the language the page text is in ("en"/"bg"/…)
    },
    "required": ["feature_title", "summary", "user_actions", "primary_action",
                 "ui_nouns", "rendered_language"],
}

_SYSTEM = (
    "You are documenting a web application for training videos. You are shown a screenshot of "
    "ONE page plus the list of interactive controls actually present on it. Describe the page "
    "objectively and concisely. feature_title: a short human name for the feature. summary: one "
    "or two sentences on what the feature is and who uses it. user_actions: what a user can do "
    "here. primary_action: the single main call-to-action. ui_nouns: the key domain nouns AS "
    "RENDERED on screen (e.g. 'Itinerary', 'Partner') — read them from the image, do not "
    "translate. rendered_language: the language the page text is in. Return JSON only; never "
    "invent controls that are not visible."
)


def _user_prompt(route_entry: dict, controls: list) -> str:
    names = [c.get("name", "") for c in controls if c.get("name")][:30]
    return (f"Route: {route_entry.get('route')}\n"
            f"Role: {route_entry.get('role_gate', 'public')}\n"
            f"Resource hint: {route_entry.get('resource_hint', '')}\n"
            f"Visible interactive controls: {', '.join(names) if names else '(none detected)'}\n"
            "Describe this page per the schema.")


def _cache_get(sha: str):
    f = ENRICH_CACHE / f"{sha}.json"
    if f.is_file():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _cache_put(sha: str, value: dict) -> None:
    ENRICH_CACHE.mkdir(parents=True, exist_ok=True)
    (ENRICH_CACHE / f"{sha}.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def enrich_route(driver, route_entry: dict, vision_backend, *, render_ms: int = 2500,
                 mem: dict | None = None) -> dict:
    """Crawl one route: screenshot -> vision -> enrichment. Cached on the screenshot hash
    (in-memory `mem` for this run + on disk across runs). Returns a record, or one flagged
    `skipped` when the page yields no screenshot (e.g. WebGL/load failure)."""
    route = route_entry.get("route")
    driver.goto(route, settle_ms=render_ms)
    shot = driver.screenshot()
    base = {"route": route, "role_gate": route_entry.get("role_gate", "public"),
            "provenance": "crawl-only"}
    if not shot:
        return {**base, "skipped": "no_screenshot"}

    sha = hashlib.sha256(shot).hexdigest()
    cached = (mem or {}).get(sha) or _cache_get(sha)
    if cached is not None:
        enrichment, hit = cached, True
    else:
        controls = driver.snapshot()
        enrichment = vision_backend.complete_vision(
            _SYSTEM, _user_prompt(route_entry, controls), shot, VISUAL_SCHEMA)
        _cache_put(sha, enrichment)
        hit = False
    if mem is not None:
        mem[sha] = enrichment
    return {**base, "screenshot_sha": sha[:16], "cache_hit": hit, **enrichment}


def enrich(inventory: dict, cfg, make_driver, vision_backend=None, *,
           roles=None, max_routes: int | None = None, render_ms: int | None = None,
           log=print) -> dict:
    """Enrich the inventory's routes with visual feature descriptions, role by role.

    `make_driver(role)` yields a driver (login handled inside, per role); one driver per role.
    Drives from `inventory['routes']` for now, but the worklist is just a list of route dicts —
    a generic link-crawler can feed the same function for non-Next.js apps later.
    """
    roles = roles if roles is not None else list(getattr(cfg, "enrich_roles", ["public", "admin"]))
    cap = max_routes if max_routes is not None else int(getattr(cfg, "enrich_max_routes", 0) or 0)
    render_ms = render_ms if render_ms is not None else int(getattr(cfg, "enrich_render_ms", 2500))
    if vision_backend is None:
        from ..llm import AnthropicBackend
        vision_backend = AnthropicBackend(getattr(cfg, "vision_model", "claude-opus-4-8"),
                                          getattr(cfg, "synth_effort", "medium"))

    all_routes = inventory.get("routes", [])

    def _is_dynamic(r):
        return bool(r.get("dynamic_params")) or "[" in (r.get("route") or "")

    wanted = [r for r in all_routes
              if r.get("role_gate", "public") in roles and not _is_dynamic(r)]
    # surfaced, not silently dropped (MULTIMODAL §11): routes gated to a role we are not crawling
    # (e.g. member, pending its login seam), and dynamic routes that need a concrete param/slug.
    needs_login = [{"route": r.get("route"), "role_gate": r.get("role_gate"),
                    "skipped": f"needs-{r.get('role_gate')}-login"}
                   for r in all_routes if r.get("role_gate", "public") not in roles
                   and not _is_dynamic(r)]
    dynamic = [{"route": r.get("route"), "role_gate": r.get("role_gate"),
                "skipped": "dynamic-route (needs a concrete param/slug)"}
               for r in all_routes if _is_dynamic(r)]

    dropped = 0
    if cap and len(wanted) > cap:
        dropped = len(wanted) - cap
        wanted = wanted[:cap]
        log(f"[enrich] route cap {cap}: enriching {cap}, skipping {dropped} (raise enrich_max_routes)")

    by_role: dict[str, list] = {}
    for r in wanted:
        by_role.setdefault(r.get("role_gate", "public"), []).append(r)

    features, skipped, mem = [], [*needs_login, *dynamic], {}
    for role in roles:
        group = by_role.get(role, [])
        if not group:
            continue
        log(f"[enrich] role={role}: {len(group)} route(s)")
        driver = make_driver(role)
        try:
            for r in group:
                try:
                    rec = enrich_route(driver, r, vision_backend, render_ms=render_ms, mem=mem)
                except Exception as e:                       # one bad route never kills the crawl
                    rec = {"route": r.get("route"), "role_gate": role,
                           "provenance": "crawl-only", "skipped": f"error: {e}"}
                (skipped if rec.get("skipped") else features).append(rec)
                tag = rec.get("skipped") or ("cache" if rec.get("cache_hit") else "vision")
                log(f"  {str(r.get('route')):40} {tag}")
        finally:
            driver.close()

    doc = {
        "meta": {"roles": roles, "route_cap": cap, "dropped_by_cap": dropped,
                 "enriched": len(features), "skipped": len(skipped),
                 "extractor_version": (inventory.get("meta") or {}).get("extractor_version")},
        "features": features,
        "skipped": skipped,
    }
    DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
    (DISCOVERY_DIR / "visual_features.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc
