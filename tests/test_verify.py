"""Layer 3 verify tests — offline, no browser. A fake driver returns canned locator
resolutions so the cage logic — role grouping, step ceiling, resolution → provenance
promotion, and flagging — is exercised without Playwright or a live app.

    python -m tests.test_verify
"""
from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

from traingen import config as prod_config
from traingen.discovery import config as dconfig
from traingen.discovery import verify

# Redirect OUT so verify.verify's drafts.verified.yaml write doesn't clobber real artifacts.
prod_config.OUT = Path(tempfile.mkdtemp())


def _draft(scenario_id, role, steps, destructive=False):
    return {"scenario_id": scenario_id, "role": role, "entry_route": f"/{role}/x",
            "destructive": destructive, "provenance": "code:route", "open_questions": [],
            "steps": steps}


def _step(sid, prov, locator, bound_via="testid"):
    return {"id": sid, "intent": "x", "locator": locator, "action": "click",
            "emphasis": "none", "settle_ms": 0, "provenance": prov, "bound_via": bound_via}


class FakeDriver:
    """Resolves a locator as confirmed iff its testid is in `present`; everything else
    unresolved. Records which roles were instantiated and advance() calls."""
    instantiated_roles: list = []

    def __init__(self, role, present):
        self.role = role
        self.present = present
        self.advanced = 0
        FakeDriver.instantiated_roles.append(role)

    def goto(self, route):
        pass

    def resolve(self, locator):
        tid = (locator or {}).get("testid")
        return ("confirmed", 1) if tid in self.present else ("unresolved", 0)

    def snapshot(self):
        return []                 # no live controls -> expansion finds nothing

    def advance(self, step):
        self.advanced += 1

    def close(self):
        pass


def test_promotion_and_flagging():
    drafts = {"discovery_run": {}, "drafts": [_draft("s1", "admin", [
        _step("a", "code:route+endpoint", {"testid": "ok-1"}),
        _step("b", "code:route", {"testid": "ok-2"}),
        _step("c", "code:endpoint", {"testid": "missing"}),     # unresolved -> drop candidate
        _step("d", "inferred", {"testid": "ok-3"}),
    ])]}
    present = {"ok-1", "ok-2", "ok-3"}
    verify.verify(drafts, cfg=dconfig.DiscoveryConfig(),
                  make_driver=lambda role: FakeDriver(role, present))

    s = drafts["drafts"][0]
    steps = {st["id"]: st for st in s["steps"]}
    assert steps["a"]["provenance"] == "route+endpoint+crawl"
    assert steps["b"]["provenance"] == "route+crawl"
    assert steps["d"]["provenance"] == "crawl-verified"
    assert steps["c"]["verified"]["status"] == "unresolved"
    assert steps["c"].get("drop_candidate") is True
    # scenario provenance = weakest step; unresolved code:endpoint (rank 0) is the floor
    assert s["provenance"] == "code:endpoint"
    assert s["verification"]["confirmed"] == 3 and s["verification"]["unresolved"] == ["c"]
    assert s["verification"]["needs_review"] is True
    assert any("step 'c'" in q for q in s["open_questions"])
    print("OK  promotion: confirmed steps promoted; unresolved code:endpoint flagged + dropped")


def test_role_grouping_and_ceiling():
    FakeDriver.instantiated_roles = []
    drafts = {"discovery_run": {}, "drafts": [
        _draft("admin1", "admin", [_step(f"a{i}", "code:route", {"testid": "ok"}) for i in range(15)]),
        _draft("member1", "member", [_step("m", "code:route", {"testid": "ok"})]),
    ]}
    cfg = dconfig.DiscoveryConfig(verify_max_steps=12)
    verify.verify(drafts, cfg=cfg, make_driver=lambda role: FakeDriver(role, {"ok"}))

    assert sorted(set(FakeDriver.instantiated_roles)) == ["admin", "member"], "one driver per role"
    admin = drafts["drafts"][0]
    assert admin["verification"]["confirmed"] == 12, "crawl stops at the 12-step ceiling"
    assert any("ceiling" in q for q in admin["open_questions"])
    print(f"OK  cage: per-role drivers {sorted(set(FakeDriver.instantiated_roles))}; "
          f"15-step scenario truncated at 12")


def test_destructive_final_step_not_advanced():
    drafts = {"discovery_run": {}, "drafts": [_draft("del", "admin", [
        _step("open", "code:route", {"testid": "ok"}),
        _step("confirm-delete", "code:route+endpoint", {"testid": "ok"}),
    ], destructive=True)]}
    drivers = []

    def mk(role):
        d = FakeDriver(role, {"ok"})
        drivers.append(d)
        return d

    verify.verify(drafts, cfg=dconfig.DiscoveryConfig(), make_driver=mk)
    # both steps confirmed, but the destructive final step is not executed (advance only on step 1)
    assert drivers[0].advanced == 1
    print("OK  read-mostly: destructive final step confirmed but not executed")


def test_expansion_binds_from_live_controls():
    steps = [
        {"id": "open", "intent": "Open the new announcement form", "locator": {}, "action": "click",
         "emphasis": "none", "settle_ms": 0, "provenance": "code:endpoint", "bound_via": "unbound"},
        {"id": "title", "intent": "Enter the announcement title", "locator": {}, "action": "fill",
         "emphasis": "none", "settle_ms": 0, "provenance": "code:endpoint", "bound_via": "unbound"},
    ]
    scen = {"scenario_id": "ann", "role": "admin", "entry_route": "/admin/x",
            "destructive": False, "provenance": "inferred", "open_questions": [], "steps": steps}
    controls = [{"role": "button", "name": "New announcement", "testid": None},
                {"role": "textbox", "name": "Announcement title", "testid": None}]

    class LiveDriver:
        def goto(self, r): pass
        def resolve(self, loc): return ("unresolved", 0)   # nothing binds via the code locator
        def snapshot(self): return controls
        def advance(self, s): pass
        def close(self): pass

    verify.verify_scenario(scen, LiveDriver(), max_steps=12)   # default HeuristicMatcher
    o, t = scen["steps"]
    assert o["bound_via"] == "role" and o["locator"] == {"role": "button", "name": "New announcement"}
    assert o["provenance"] == "crawl-only" and o["verified"]["status"] == "bound_by_crawl"
    assert "drop_candidate" not in o
    assert t["bound_via"] == "role" and t["locator"]["role"] == "textbox"
    assert scen["verification"]["bound_by_crawl"] == ["open", "title"]
    assert scen["verification"]["needs_review"] is False
    print("OK  expansion: unbound steps bound to live-discovered controls (provenance crawl-only)")


def test_matcher_ignores_generic_and_chrome():
    m = verify.HeuristicMatcher()
    controls = [{"role": "button", "name": "Open Next.js Dev Tools", "testid": None},
                {"role": "button", "name": "New announcement", "testid": None}]
    assert m.match({"action": "click", "intent": "Open the new announcement form", "locator": {}},
                   controls)["name"] == "New announcement"
    # a purely generic intent must not latch onto chrome
    assert m.match({"action": "click", "intent": "Open the page", "locator": {}}, controls) is None
    print("OK  matcher: ignores generic tokens; won't bind to dev-tools chrome")


def test_live_route_reinserts_locale():
    assert verify.live_route("/admin/announcements", "en") == "/admin/en/announcements"
    assert verify.live_route("/member/dashboard/bookings", "en") == "/member/en/dashboard/bookings"
    assert verify.live_route("/discover", "en") == "/en/discover"            # public
    assert verify.live_route("/admin/x", "") == "/admin/x"                   # no locale -> unchanged
    print("OK  live_route: locale re-inserted after role scope (and at root for public)")


def main() -> int:
    test_promotion_and_flagging()
    test_role_grouping_and_ceiling()
    test_destructive_final_step_not_advanced()
    test_expansion_binds_from_live_controls()
    test_matcher_ignores_generic_and_chrome()
    test_live_route_reinserts_locale()
    print("\nall verify tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
