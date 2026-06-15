"""Layer 2 synthesis tests — offline, no API key. A stub LLM backend returns canned
drafts so grouping, semantic validation, caching, and assembly are exercised without
calling Claude.

    python -m tests.test_synthesize
"""
from __future__ import annotations

import copy
import shutil
import sys
from pathlib import Path

import tempfile
from pathlib import Path

from traingen import config as prod_config
from traingen.discovery import config as dconfig
from traingen.discovery import synthesize
from traingen.discovery.config import DiscoveryConfig
from traingen.discovery.extract import build_inventory

# Redirect OUT so synthesize.run's drafts.yaml / cache writes don't clobber real artifacts.
prod_config.OUT = Path(tempfile.mkdtemp())

FIX = Path(__file__).parent / "fixtures"
SPEC, APP = FIX / "openapi_partners.json", FIX / "next_app" / "app"

# A clean, inventory-bound draft for the `partners` group (mirrors SYNTHESIZER §7).
PARTNERS_DRAFTS = {"drafts": [{
    "scenario_id": "add-partner-profile",
    "title": {"bg": "Добавяне на партньорски профил", "en": "Adding a partner profile"},
    "role": "admin",
    "goal": "Teach an admin to create a partner profile and publish it.",
    "entry_route": "/admin/partners",
    "needs_seed_record": False, "destructive": False, "usage_rank": 0,
    "provenance": "code:route",
    "source_refs": {"routes": ["/admin/partners", "/admin/partners/new"],
                    "endpoints": ["create_partner", "publish_partner"]},
    "steps": [
        {"id": "open-new-form", "intent": "Open the new-partner form from the list",
         "locator": {"testid": "partners-add-btn"}, "action": "click", "value": "",
         "emphasis": "highlight", "settle_ms": 800, "provenance": "code:route", "bound_via": "testid"},
        {"id": "enter-name", "intent": "Enter the partner's business name",
         "locator": {"testid": "partner-business-name"}, "action": "fill", "value": "Хотел Морска Звезда",
         "emphasis": "zoom", "settle_ms": 400, "provenance": "code:route+endpoint", "bound_via": "testid"},
        {"id": "select-category", "intent": "Choose the partner category",
         "locator": {"label": "Category"}, "action": "select", "value": "accommodation",
         "emphasis": "highlight", "settle_ms": 600, "provenance": "code:route+endpoint", "bound_via": "label"},
        {"id": "select-region", "intent": "Set the region used for search",
         "locator": {"testid": "partner-region"}, "action": "select", "value": "Varna",
         "emphasis": "none", "settle_ms": 600, "provenance": "code:route+endpoint", "bound_via": "testid"},
        {"id": "save-draft", "intent": "Save the profile as a draft",
         "locator": {"testid": "partner-save-draft"}, "action": "click", "value": "",
         "emphasis": "highlight", "settle_ms": 1200, "provenance": "code:route", "bound_via": "testid"},
        {"id": "publish", "intent": "Publish so the profile appears in search",
         "locator": {"testid": "partner-publish"}, "action": "click", "value": "",
         "emphasis": "zoom", "settle_ms": 1500, "provenance": "code:route+endpoint", "bound_via": "testid"},
    ],
    "open_questions": ["Category select has no data-testid; bound by label. Confirm in crawl."],
}]}


class StubBackend:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def complete_json(self, system, user, schema):
        self.calls += 1
        return copy.deepcopy(self.payload)


def _inventory():
    return build_inventory(DiscoveryConfig(spec_url=str(SPEC), frontend_app_dir=str(APP)))


def test_grouping():
    groups = synthesize.group_by_resource(_inventory())
    assert "partners" in groups
    assert groups["partners"]["endpoints"], "partners group has endpoints"
    # route-only groups (no API backing) exist but will be skipped by run()
    assert any(not g["endpoints"] for g in groups.values())
    print(f"OK  grouping: {len(groups)} groups; partners has "
          f"{len(groups['partners']['endpoints'])} endpoints / {len(groups['partners']['routes'])} routes")


def test_candidate_routes_enable_cross_noun_binding():
    # announcements API but the UI lives under a differently-named "communications" page
    inv = {
        "meta": {}, "i18n": {"strings": {}}, "usage": [], "testid_gaps": [],
        "endpoints": [{"operation_id": "create_announcement", "method": "POST",
                       "path": "/api/v1/admin/announcements", "resource_hint": "announcements",
                       "security": ["admin"], "request_fields": [], "task_verb_hint": "create"}],
        "routes": [{"route": "/admin/dashboard/communications", "resource_hint": "communications",
                    "role_gate": "admin", "controls": [
                        {"label": "New announcement", "control_type": "button", "role": "button",
                         "testid": "comms-new", "name_attr": None, "i18n_key": None}]}],
    }
    groups = synthesize.group_by_resource(inv)
    ann = groups["announcements"]
    assert ann["endpoints"] and not ann["routes"], "noun mismatch: no same-noun route"
    assert any(r["route"] == "/admin/dashboard/communications" for r in ann["candidate_routes"]), \
        "same-role route offered as a candidate"
    testids, _, _ = synthesize._control_index(ann)
    assert "comms-new" in testids, "candidate-route controls are bindable (cross-noun reconcile)"
    print("OK  candidate routes: announcements endpoints can bind to the communications page's controls")


def test_validation_accepts_and_rejects():
    group = synthesize.group_by_resource(_inventory())["partners"]
    assert synthesize.validate_drafts(PARTNERS_DRAFTS, group) == [], "clean draft must validate"

    bad = copy.deepcopy(PARTNERS_DRAFTS)
    bad["drafts"][0]["steps"][0]["locator"] = {"testid": "does-not-exist"}        # invented selector
    bad["drafts"][0]["steps"][2]["provenance"] = "code:route+crawl"               # forbidden "crawl"
    bad["drafts"][0]["steps"] = bad["drafts"][0]["steps"][:3]                     # only 3 steps
    errs = synthesize.validate_drafts(bad, group)
    assert any("not in inventory" in e for e in errs)
    assert any("crawl" in e for e in errs)
    assert any("steps" in e for e in errs)
    print(f"OK  validation: clean draft passes; bad draft caught {len(errs)} issues")


def test_normalize_derives_provenance_and_rejects_bare_role():
    group = synthesize.group_by_resource(_inventory())["partners"]

    # normalize: scenario provenance becomes the weakest step, regardless of what the model set
    doc = {"drafts": [{**copy.deepcopy(PARTNERS_DRAFTS["drafts"][0]), "provenance": "inferred"}]}
    synthesize.normalize(doc)
    assert doc["drafts"][0]["provenance"] == "code:route", "derived weakest-step provenance"

    # bare role (no name) is rejected — the model must mark unbound instead of guessing
    bad = copy.deepcopy(PARTNERS_DRAFTS)
    bad["drafts"][0]["steps"][0] = {**bad["drafts"][0]["steps"][0],
                                    "bound_via": "role", "locator": {"role": "link"}}
    errs = synthesize.validate_drafts(bad, group)
    assert any("role+name not in inventory" in e for e in errs)
    print("OK  normalize: provenance derived from steps; bare role={role} rejected")


def test_run_and_cache():
    shutil.rmtree(prod_config.OUT / "discovery" / "drafts_cache", ignore_errors=True)
    inv = _inventory()
    backend = StubBackend(PARTNERS_DRAFTS)

    doc = synthesize.run(inv, cfg=dconfig.DiscoveryConfig(), backend=backend)
    assert backend.calls == 1, "exactly one group (partners) synthesized"
    assert doc["drafts"][0]["scenario_id"] == "add-partner-profile"
    assert doc["discovery_run"]["failures"] == {}

    synthesize.run(inv, cfg=dconfig.DiscoveryConfig(), backend=backend)
    assert backend.calls == 1, "second run served from cache (no new LLM call)"

    out = prod_config.OUT / "discovery" / "drafts.yaml"
    assert out.exists()
    print(f"OK  run+cache: 1 group synthesized, cache hit on rerun -> {out}")


def main() -> int:
    test_grouping()
    test_candidate_routes_enable_cross_noun_binding()
    test_validation_accepts_and_rejects()
    test_normalize_derives_provenance_and_rejects_bare_role()
    test_run_and_cache()
    print("\nall synthesize tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
