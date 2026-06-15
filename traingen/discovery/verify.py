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

Expansion: when a step's code-derived locator doesn't resolve (or was left unbound),
the crawl SNAPSHOTS the page's real interactive controls off the rendered DOM and a
matcher binds the step to an actual control — provenance `crawl-only`. This sidesteps both
the app's missing test-ids and the static scan's blindness to imported components. The
matcher is pluggable: a deterministic heuristic by default (offline-testable), an optional
LLM matcher for harder cases.

Still deferred: inserting brand-new sub-steps for runtime-only wizard/modal stages no step
predicts (this binds the steps Layer 2 proposed; it doesn't yet invent new ones).
"""
from __future__ import annotations

import json
import re
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

# action -> ARIA roles a control must have to satisfy it (for live-control matching)
_ROLE_FOR_ACTION = {
    "click": {"button", "link", "menuitem", "tab", "checkbox", "radio"},
    "fill": {"textbox", "searchbox"},
    "select": {"combobox", "listbox"},
    "hover": {"button", "link"},
    "navigate": {"link"},
}


def _tokens(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


class HeuristicMatcher:
    """Match a step to a live control by action→role compatibility + intent/name token
    overlap. Deterministic; no LLM. Good enough to bind obvious controls, conservative
    enough (>=1 shared token) to avoid wild guesses."""

    def match(self, step: dict, controls: list):
        ok_roles = _ROLE_FOR_ACTION.get(step.get("action"), set())
        want = _tokens(step.get("intent")) | _tokens((step.get("locator") or {}).get("label"))
        best, best_score = None, 0
        for c in controls:
            if ok_roles and c.get("role") not in ok_roles:
                continue
            score = len(want & _tokens(c.get("name")))
            if score > best_score:
                best, best_score = c, score
        return best if best_score >= 1 else None


def get_matcher(cfg):
    if getattr(cfg, "verify_matcher", "heuristic") == "llm":
        from .llm import get_backend
        return LLMMatcher(get_backend(cfg))
    return HeuristicMatcher()


class LLMMatcher:
    """Optional agentic matcher: ask the model to pick the best live control (or none) for
    a step's intent. Lazily uses the Claude backend; falls back to heuristic on any error."""

    _SCHEMA = {"type": "object", "additionalProperties": False,
               "properties": {"index": {"type": "integer"}},
               "required": ["index"]}

    def __init__(self, backend):
        self.backend = backend
        self._fallback = HeuristicMatcher()

    def match(self, step: dict, controls: list):
        if not controls:
            return None
        try:
            opts = "\n".join(f"{i}: role={c.get('role')} name={c.get('name')!r}"
                             for i, c in enumerate(controls))
            out = self.backend.complete_json(
                "Pick the control that best performs the step, or index -1 if none fits. "
                "Return JSON {index}.",
                f"step intent: {step.get('intent')}\naction: {step.get('action')}\n"
                f"controls:\n{opts}",
                self._SCHEMA)
            i = out.get("index", -1)
            return controls[i] if 0 <= i < len(controls) else None
        except Exception:
            return self._fallback.match(step, controls)


def _locator_from_control(c: dict):
    if c.get("testid"):
        return {"testid": c["testid"]}, "testid"
    if c.get("name") and c.get("role"):
        return {"role": c["role"], "name": c["name"]}, "role"
    if c.get("name"):
        return {"label": c["name"]}, "label"
    return None, None


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


def verify_scenario(scenario: dict, driver, max_steps: int, matcher=None, expand: bool = True) -> dict:
    """Confirm each step's locator against the live DOM via `driver`; promote provenance,
    bind unresolved/unbound steps to discovered controls (expansion), and flag the rest.
    Mutates and returns the scenario dict."""
    matcher = matcher or HeuristicMatcher()
    driver.goto(scenario["entry_route"])
    steps = scenario.get("steps", [])
    truncated = len(steps) > max_steps
    confirmed, bound_by_crawl, unresolved, ambiguous = 0, [], [], []

    for st in steps[:max_steps]:
        status, matches = driver.resolve(st.get("locator", {}))
        pre = st.get("provenance", "inferred")
        if status == "confirmed":
            st["verified"] = {"status": status, "matches": matches}
            st["provenance"] = PROMOTE.get(pre, "crawl-verified")
            st["bound_via"] = st.get("bound_via") if st.get("bound_via") != "unbound" else "crawl"
            confirmed += 1
            if not (scenario.get("destructive") and st is steps[-1]):
                driver.advance(st)
            continue

        # EXPANSION: the code locator didn't resolve — discover a real control live
        control = matcher.match(st, driver.snapshot()) if expand else None
        loc, via = _locator_from_control(control) if control else (None, None)
        if loc:
            st["locator"], st["bound_via"] = loc, via
            st["provenance"] = "crawl-only"          # discovered live, no code backing
            st["verified"] = {"status": "bound_by_crawl", "name": control.get("name")}
            st.pop("drop_candidate", None)
            bound_by_crawl.append(st["id"])
            confirmed += 1
            if not (scenario.get("destructive") and st is steps[-1]):
                driver.advance(st)
            continue

        st["verified"] = {"status": status, "matches": matches}
        (ambiguous if status == "ambiguous" else unresolved).append(st["id"])
        if pre in _DROP_IF_UNCONFIRMED:
            st["drop_candidate"] = True
        scenario.setdefault("open_questions", []).append(
            f"step '{st['id']}': locator {status} in crawl, no live control matched — "
            + ("drop or add a test-id" if st.get("drop_candidate") else "confirm locator"))

    if truncated:
        scenario.setdefault("open_questions", []).append(
            f"scenario exceeds the {max_steps}-step verify ceiling; "
            f"{len(steps) - max_steps} step(s) not crawled")

    scenario["provenance"] = _weakest([s.get("provenance", "inferred") for s in steps[:max_steps]])
    scenario["verification"] = {
        "role": scenario.get("role"),
        "confirmed": confirmed,
        "bound_by_crawl": bound_by_crawl,
        "unresolved": unresolved,
        "ambiguous": ambiguous,
        "needs_review": bool(unresolved or ambiguous or truncated),
    }
    return scenario


def verify(drafts_doc: dict, cfg=None, make_driver=None) -> dict:
    """Run the caged crawl over every draft, grouped by role (one driver per role)."""
    cfg = cfg or dconfig.load_discovery_config()
    make_driver = make_driver or _playwright_driver_factory(cfg)
    matcher = get_matcher(cfg)
    expand = getattr(cfg, "verify_expand", True)

    by_role: dict = {}
    for s in drafts_doc.get("drafts", []):
        by_role.setdefault(s.get("role", "public"), []).append(s)

    for role, scenarios in sorted(by_role.items()):
        driver = make_driver(role)
        try:
            for s in scenarios:
                verify_scenario(s, driver, cfg.verify_max_steps, matcher=matcher, expand=expand)
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
        if not locator or not any(k in locator for k in ("testid", "placeholder", "label", "role")):
            return "unresolved", 0
        try:
            count = self._rec.resolve_locator(self.page, locator).count()
        except Exception:
            return "unresolved", 0
        return ("confirmed" if count == 1 else "ambiguous" if count > 1 else "unresolved"), count

    def snapshot(self):
        """Real interactive controls on the current page (role + accessible name + testid)."""
        try:
            return self.page.eval_on_selector_all(
                "button,a,input,select,textarea,[role=button],[role=link],[role=combobox]",
                """els => els.map(e => {
                    const tag = e.tagName.toLowerCase();
                    const role = e.getAttribute('role') || ({a:'link', button:'button',
                        select:'combobox', textarea:'textbox',
                        input:(e.type==='checkbox'?'checkbox':e.type==='radio'?'radio':'textbox')}[tag] || tag);
                    const name = (e.getAttribute('aria-label') || e.innerText ||
                        e.placeholder || e.name || '').trim().slice(0, 80);
                    return {role, name, testid: e.getAttribute('data-testid')};
                }).filter(c => c.name)""")
        except Exception:
            return []

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
