"""CLI for M3 — visual discovery enrichment (MULTIMODAL C2).

    python -m traingen.discovery.enrich_cli [--roles public,admin] [--max-routes N]

Screenshot-crawls the inventory's routes and asks Claude (vision) what each feature is.
Needs Playwright + a running app + ANTHROPIC_API_KEY (and TRAINGEN_ADMIN_PASSWORD for admin
routes). Reads out/discovery/feature_inventory.json, writes out/discovery/visual_features.json
(a SIDECAR — never the Layer-1 inventory_hash, never the SSOT).
"""
from __future__ import annotations

import argparse
import json

from .. import config as prod_config
from . import config as dconfig
from . import enrich
from .verify import _playwright_driver_factory


def main() -> None:
    ap = argparse.ArgumentParser(description="TrainGen M3 — visual discovery enrichment")
    ap.add_argument("--inventory", default=str(prod_config.OUT / "discovery" / "feature_inventory.json"))
    ap.add_argument("--roles", help="comma list, e.g. public,admin (default: config)")
    ap.add_argument("--max-routes", type=int, help="cap routes enriched (default: config)")
    args = ap.parse_args()

    cfg = dconfig.load_discovery_config()
    inventory = json.loads(open(args.inventory, encoding="utf-8").read())
    make_driver = _playwright_driver_factory(cfg)
    roles = args.roles.split(",") if args.roles else None

    doc = enrich.enrich(inventory, cfg, make_driver, roles=roles, max_routes=args.max_routes)
    m = doc["meta"]
    print(f"enriched {m['enriched']} route(s) across roles {m['roles']}; "
          f"{m['skipped']} skipped (incl. roles without a login seam)")
    print(f"-> {prod_config.OUT / 'discovery' / 'visual_features.json'}")


if __name__ == "__main__":
    main()
