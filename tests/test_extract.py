"""Layer 1 extraction tests — deterministic, offline, fixture-based.

    python -m tests.test_extract
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from traingen.discovery import config as dconfig
from traingen.discovery.extract import build_inventory
from traingen.discovery.nextjs import extract_routes
from traingen.discovery.openapi import extract_endpoints

FIX = Path(__file__).parent / "fixtures"
SPEC = FIX / "openapi_partners.json"
APP = FIX / "next_app" / "app"


def _by_id(endpoints):
    return {e["operation_id"]: e for e in endpoints}


def test_openapi():
    eps = _by_id(extract_endpoints(json.loads(SPEC.read_text())))

    create = eps["create_partner"]
    assert create["task_verb_hint"] == "create"
    assert create["security"] == ["admin"]
    fields = {f["name"]: f for f in create["request_fields"]}
    assert fields["business_name"]["required"] is True
    assert fields["category"]["type"] == "enum" and "accommodation" in fields["category"]["enum"]
    assert {s["status"]: s["meaning"] for s in create["response_states"]}[422] == "validation_error"

    assert eps["publish_partner"]["task_verb_hint"] == "publish"   # action endpoint
    assert eps["get_partner"]["task_verb_hint"] == "view"
    assert eps["delete_partner"]["task_verb_hint"] == "remove"
    assert eps["list_partners"]["task_verb_hint"] == "list"
    print("OK  openapi: 5 endpoints, verbs + fields + security correct")


def test_nextjs():
    routes = {r["route"]: r for r in
              extract_routes(APP, dconfig.DEFAULT_ROLE_GATES, dconfig.DEFAULT_LOCALE_PARAMS)}

    # group segment is stripped from the URL but recorded in segments[]
    assert "/admin/partners/new" in routes
    new = routes["/admin/partners/new"]
    assert any(s["type"] == "group" for s in new["segments"])
    assert new["resource_hint"] == "partners"
    assert new["role_gate"] == "admin"
    assert new["layout_chain"] == ["app/layout.tsx", "app/admin/(dashboard)/layout.tsx"]
    assert new["testid_coverage"]["missing"], "category select should be a gap"

    detail = routes["/admin/partners/[id]"]
    assert detail["dynamic_params"] == ["id"]
    assert detail["requires_seed_record"] is True

    assert routes["/dashboard"]["role_gate"] == "public"

    # i18n [locale] segment is stripped from the URL and is NOT a seeded record
    admin_dash = routes["/admin/dashboard"]
    assert admin_dash["role_gate"] == "admin"
    assert admin_dash["dynamic_params"] == [] and admin_dash["requires_seed_record"] is False
    assert any(s["type"] == "locale" for s in admin_dash["segments"])
    # real dynamic segment beside a locale: /[locale]/trip/[slug] -> /trip/[slug]
    trip = routes["/trip/[slug]"]
    assert trip["dynamic_params"] == ["slug"] and trip["requires_seed_record"] is True
    print(f"OK  nextjs: {len(routes)} routes, segments/role/layout/seed-flag/locale correct")


def test_inventory_deterministic():
    cfg = dconfig.DiscoveryConfig(spec_url=str(SPEC), frontend_app_dir=str(APP))
    a = build_inventory(cfg)
    b = build_inventory(cfg)

    assert a["meta"]["inventory_hash"] == b["meta"]["inventory_hash"], "hash must be stable"
    assert a["meta"]["generated_at"] != "" and "generated_at" not in json.dumps(
        {k: v for k, v in a.items() if k != "meta"}), "hash payload excludes timestamp"

    gaps = {g["control"] for g in a["testid_gaps"]}
    assert "category" in gaps
    cat = next(g for g in a["testid_gaps"] if g["control"] == "category")
    assert cat["suggested_testid"] == "partners-category"
    print(f"OK  inventory: hash {a['meta']['inventory_hash'][:20]}…  "
          f"{len(a['endpoints'])} endpoints / {len(a['routes'])} routes / "
          f"{len(a['testid_gaps'])} gaps")


def main() -> int:
    test_openapi()
    test_nextjs()
    test_inventory_deterministic()
    print("\nall extract tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
