"""M3 visual enrichment — offline. Stub vision backend + fake driver: prove the crawl shape,
screenshot-hash caching (no re-pay), role grouping, the route cap, and that routes whose role
has no login seam are surfaced as skipped (not silently dropped). No browser, no API.

    python -m tests.test_enrich
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from traingen import config as prod_config

prod_config.OUT = Path(tempfile.mkdtemp())          # never touch real artifacts
from traingen.discovery import enrich               # noqa: E402  (after OUT redirect)

enrich.DISCOVERY_DIR = prod_config.OUT / "discovery"
enrich.ENRICH_CACHE = enrich.DISCOVERY_DIR / "enrich_cache"


class StubVision:
    """Counts calls so caching is observable; returns a schema-shaped object."""
    def __init__(self):
        self.calls = 0

    def complete_vision(self, system, user, image_png, schema, media_type="image/png"):
        self.calls += 1
        return {"feature_title": "Feature", "summary": "What it is.",
                "user_actions": ["do x"], "primary_action": "do x",
                "ui_nouns": ["Partner"], "rendered_language": "en"}


class FakeDriver:
    """Returns a fixed screenshot per route (so equal bytes => cache hit)."""
    def __init__(self, role, shots):
        self.role, self.shots, self.route, self.closed = role, shots, None, False

    def goto(self, route, settle_ms=0): self.route = route
    def screenshot(self): return self.shots.get(self.route, b"")
    def snapshot(self): return [{"role": "button", "name": "Go"}]
    def close(self): self.closed = True


def _inventory(routes):
    return {"meta": {"extractor_version": "0.1.0"}, "routes": routes}


class _Cfg:
    enrich_roles = ["public", "admin"]
    enrich_max_routes = 0
    enrich_render_ms = 0
    vision_model = "claude-opus-4-8"
    synth_effort = "low"


def test_enrich_shape_and_caching():
    # /a and /b share a screenshot (same bytes) -> vision called once; /c differs -> twice total.
    shots = {"/a": b"AAA", "/b": b"AAA", "/c": b"CCC"}
    inv = _inventory([
        {"route": "/a", "role_gate": "public"},
        {"route": "/b", "role_gate": "public"},
        {"route": "/c", "role_gate": "public"},
    ])
    vision = StubVision()
    driver = FakeDriver("public", shots)
    doc = enrich.enrich(inv, _Cfg(), make_driver=lambda role: driver,
                        vision_backend=vision, log=lambda *_: None)

    assert len(doc["features"]) == 3, "all three routes enriched"
    assert vision.calls == 2, f"screenshot-hash cache: /a and /b dedupe to 1 call (+/c) -> 2, got {vision.calls}"
    f0 = doc["features"][0]
    for k in ("feature_title", "summary", "user_actions", "primary_action", "ui_nouns",
              "rendered_language", "screenshot_sha", "provenance"):
        assert k in f0, f"missing {k}"
    assert f0["provenance"] == "crawl-only"
    assert driver.closed, "driver closed after the role group"
    # written sidecar exists and never carries an inventory_hash
    out = enrich.DISCOVERY_DIR / "visual_features.json"
    assert out.is_file() and "inventory_hash" not in out.read_text()
    print(f"OK  enrich: 3 routes, vision cached on screenshot hash ({vision.calls} calls), sidecar written")


def test_no_screenshot_is_skipped():
    inv = _inventory([{"route": "/blank", "role_gate": "public"}])
    vision = StubVision()
    doc = enrich.enrich(inv, _Cfg(), make_driver=lambda role: FakeDriver("public", {"/blank": b""}),
                        vision_backend=vision, log=lambda *_: None)
    assert doc["features"] == [] and len(doc["skipped"]) == 1
    assert doc["skipped"][0]["skipped"] == "no_screenshot" and vision.calls == 0
    print("OK  enrich: a route with no screenshot is skipped, not vision-called")


def test_role_filter_and_cap():
    inv = _inventory([
        {"route": "/pub1", "role_gate": "public"},
        {"route": "/pub2", "role_gate": "public"},
        {"route": "/adm", "role_gate": "admin"},
        {"route": "/mem", "role_gate": "member"},     # role we are NOT crawling
    ])
    shots = {"/pub1": b"1", "/pub2": b"2", "/adm": b"3"}
    seen_roles = []

    def make_driver(role):
        seen_roles.append(role)
        return FakeDriver(role, shots)

    # cap to 2 of the 3 wanted (public+admin) routes
    doc = enrich.enrich(inv, _Cfg(), make_driver=make_driver, vision_backend=StubVision(),
                        roles=["public", "admin"], max_routes=2, log=lambda *_: None)
    assert doc["meta"]["dropped_by_cap"] == 1, "one wanted route dropped by the cap"
    assert len(doc["features"]) == 2
    # member route surfaced as needing a login seam, not silently dropped
    mem = [s for s in doc["skipped"] if s["route"] == "/mem"]
    assert mem and mem[0]["skipped"] == "needs-member-login", "member route flagged, not dropped"
    print(f"OK  enrich: role filter + cap honoured; member surfaced ({mem[0]['skipped']}); drivers per role {seen_roles}")


def main() -> int:
    test_enrich_shape_and_caching()
    test_no_screenshot_is_skipped()
    test_role_filter_and_cap()
    print("\nall enrich tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
