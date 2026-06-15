"""Layer 3 — Verify (DISCOVERY §6). The one caged agent: live perception that code
can't provide. For each draft scenario it opens the running app and, per step, checks
that the code-derived locator actually resolves in the DOM; it then promotes provenance
and flags whatever didn't resolve.

The cage:
- role-scoped: one browser context per role (admin, member); never mixed.
- read-mostly: navigates the flow on the SEEDED DEMO TENANT (never prod); destructive
  final steps are not executed, only flagged for manual confirmation.
- bounded: a hard per-scenario step ceiling; no open-ended exploration.
- write-restricted: emits out/discovery/drafts.verified.yaml only; never the SSOT.

The cage logic (grouping, bounds, resolution → provenance promotion, enrichment) is driver-
agnostic and unit-tested with a fake driver. The Playwright-backed driver (below) is the
real perception layer; like record.py it is lazily imported and unrun without a live app.

Not yet: agentic EXPANSION of runtime-only sub-steps (modal stages, wizard pages that no
locator predicts). This first cut confirms/flags what Layer 2 proposed; expansion is the
genuinely agentic follow-up.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from .. import config as prod_config
from . import config as dconfig

# pre-crawl provenance (SYNTHESIZER §4) -> promoted value on a confirmed locator (DISCOVERY §7)
PROMOTE = {
    "code:route+endpoint": "route+endpoint+crawl",
    "code:route": "route+crawl",
    "code:endpoint": "endpoint+crawl",
    "inferred": "crawl-verified",
}
# risk floor ordering — scenario provenance = the weakest step (lowest rank)
_RANK = {
    "route+endpoint+crawl": 5, "route+crawl": 4, "crawl-verified": 3,
    "endpoint+crawl": 2, "crawl-only": 2, "inventory-only": 1,
    "code:route+endpoint": 0, "code:route": 0, "code:endpoint": 0, "inferred": 0,
}
_DROP_IF_UNCONFIRMED = {"code:endpoint", "inferred"}


def _weakest(provenances: list) -> str:
    return min(provenances, key=lambda p: _RANK.get(p, 0)) if provenances else "inventory-only"


def live_route(route: str, locale: str, scopes=("admin", "member")) -> str:
    """Re-insert the i18n locale that extract stripped, matching the app's layout:
    /admin/announcements -> /admin/en/announcements ; /discover -> /en/discover."""
    if not locale:
        return route
    parts = [p for p in route.strip("/").split("/") if p]
    if parts and parts[0] in scopes:
        return "/" + "/".join([parts[0], locale, *parts[1:]])
    return "/" + "/".join([locale, *parts])


def verify_scenario(scenario: dict, driver, max_steps: int) -> dict:
    """Confirm each step's locator against the live DOM via `driver`; promote provenance
    and flag failures. Mutates and returns the scenario dict."""
    driver.goto(scenario["entry_route"])
    steps = scenario.get("steps", [])
    truncated = len(steps) > max_steps
    confirmed, unresolved, ambiguous = 0, [], []

    for st in steps[:max_steps]:
        status, matches = driver.resolve(st.get("locator", {}))
        st["verified"] = {"status": status, "matches": matches}
        pre = st.get("provenance", "inferred")
        if status == "confirmed":
            st["provenance"] = PROMOTE.get(pre, "crawl-verified")
            st["bound_via"] = st.get("bound_via") if st.get("bound_via") != "unbound" else "crawl"
            confirmed += 1
            # read-mostly: advance to the next surface, but never run a destructive final step
            if not (scenario.get("destructive") and st is steps[-1]):
                driver.advance(st)
        else:
            (ambiguous if status == "ambiguous" else unresolved).append(st["id"])
            if pre in _DROP_IF_UNCONFIRMED:
                st["drop_candidate"] = True
            scenario.setdefault("open_questions", []).append(
                f"step '{st['id']}': locator {status} in crawl ({matches} matches) — "
                + ("drop or add a test-id" if st.get("drop_candidate") else "confirm locator"))

    if truncated:
        scenario.setdefault("open_questions", []).append(
            f"scenario exceeds the {max_steps}-step verify ceiling; "
            f"{len(steps) - max_steps} step(s) not crawled")

    scenario["provenance"] = _weakest([s.get("provenance", "inferred") for s in steps[:max_steps]])
    scenario["verification"] = {
        "role": scenario.get("role"),
        "confirmed": confirmed,
        "unresolved": unresolved,
        "ambiguous": ambiguous,
        "needs_review": bool(unresolved or ambiguous or truncated),
    }
    return scenario


def verify(drafts_doc: dict, cfg=None, make_driver=None) -> dict:
    """Run the caged crawl over every draft, grouped by role (one driver per role)."""
    cfg = cfg or dconfig.load_discovery_config()
    make_driver = make_driver or _playwright_driver_factory(cfg)

    by_role: dict = {}
    for s in drafts_doc.get("drafts", []):
        by_role.setdefault(s.get("role", "public"), []).append(s)

    for role, scenarios in sorted(by_role.items()):
        driver = make_driver(role)
        try:
            for s in scenarios:
                verify_scenario(s, driver, cfg.verify_max_steps)
        finally:
            driver.close()

    run = drafts_doc.setdefault("discovery_run", {})
    run["verified"] = True
    run["verify_roles"] = sorted(by_role)
    out = prod_config.OUT / "discovery" / "drafts.verified.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(drafts_doc, allow_unicode=True, sort_keys=False),
                   encoding="utf-8")
    return drafts_doc


# --- Playwright-backed driver (real perception; lazily imported, unrun without a live app) ---

class PlaywrightDriver:
    """Drives one role's browser context against the seeded demo tenant. Reuses record.py's
    semantic locator resolution and login so verification and recording agree on selectors."""

    def __init__(self, role: str, prod_cfg, locale: str = "en", scopes=("admin", "member")):
        from playwright.sync_api import sync_playwright

        from .. import record as rec  # reuse resolve_locator / do_action / login
        self._rec = rec
        self._cfg = prod_cfg
        self._locale, self._scopes = locale, scopes
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=prod_cfg.headless)
        self._ctx = self._browser.new_context(base_url=prod_cfg.base_url, viewport=prod_cfg.viewport)
        self.page = self._ctx.new_page()
        rec.login(self.page, role, prod_cfg)

    def goto(self, route: str):
        self.page.goto(live_route(route, self._locale, self._scopes))
        self.page.wait_for_load_state("networkidle")

    def resolve(self, locator: dict):
        if not locator or not any(k in locator for k in ("testid", "label", "role")):
            return "unresolved", 0
        try:
            count = self._rec.resolve_locator(self.page, locator).count()
        except Exception:
            return "unresolved", 0
        return ("confirmed" if count == 1 else "ambiguous" if count > 1 else "unresolved"), count

    def advance(self, step: dict):
        try:
            el = self._rec.resolve_locator(self.page, step["locator"]).first
            self._rec.do_action(self.page, el, step)
            self.page.wait_for_load_state("networkidle")
        except Exception:
            pass  # read-mostly best effort; resolution already recorded

    def close(self):
        self._ctx.close(); self._browser.close(); self._pw.stop()


def _playwright_driver_factory(dcfg):
    prod_cfg = prod_config.load_config()
    return lambda role: PlaywrightDriver(role, prod_cfg,
                                         locale=dcfg.live_locale, scopes=tuple(dcfg.live_scopes))


def run_from_file(drafts_path=None, cfg=None) -> dict:
    cfg = cfg or dconfig.load_discovery_config()
    path = Path(drafts_path or (prod_config.OUT / "discovery" / "drafts.yaml"))
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return verify(doc, cfg=cfg)
