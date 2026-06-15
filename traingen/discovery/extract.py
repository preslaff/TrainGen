"""Layer 1 orchestrator — builds feature_inventory.json (FEATURE_INVENTORY.md).

Deterministic: same commits ⇒ same `inventory_hash` (computed over the facts payload,
excluding the `generated_at` timestamp). That hash is the CI release-diff key.

    python -m traingen.discovery.extract --spec <url|path> --app <next-app-dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .. import config as prod_config
from . import config as dconfig
from .nextjs import extract_routes
from .openapi import extract_endpoints


def _fetch_spec(spec_url: str) -> dict:
    if spec_url.startswith(("http://", "https://")):
        with urllib.request.urlopen(spec_url, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    return json.loads(Path(spec_url).read_text(encoding="utf-8"))


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in (text or "").lower()).strip("-")


def _aggregate_testid_gaps(routes: list) -> list:
    gaps = []
    for r in routes:
        for c in r["controls"]:
            if c["testid"] is None:
                label = c["label"] or c["name_attr"] or c["control_type"]
                slug = _slug(c["name_attr"] or label or "control")
                gaps.append({
                    "route": r["route"],
                    "control": c["name_attr"] or label,
                    "label": label,
                    "suggested_testid": f"{r['resource_hint']}-{slug}" if slug else None,
                })
    return gaps


def _inventory_hash(facts: dict) -> str:
    canon = json.dumps(facts, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


def build_inventory(dcfg: dconfig.DiscoveryConfig) -> dict:
    spec = _fetch_spec(dcfg.spec_url) if dcfg.spec_url else {}
    endpoints = extract_endpoints(spec) if spec else []
    routes = extract_routes(dcfg.frontend_app_dir, dcfg.role_gates) if dcfg.frontend_app_dir else []
    i18n = {"locales": prod_config.load_config().langs, "strings": {}}
    usage: list = []                       # GA4 weighting is a later cut
    testid_gaps = _aggregate_testid_gaps(routes)

    facts = {"endpoints": endpoints, "routes": routes,
             "i18n": i18n, "usage": usage, "testid_gaps": testid_gaps}
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "frontend": {"repo": dcfg.frontend_repo, "app_dir": dcfg.frontend_app_dir,
                     "commit": dcfg.frontend_commit, "framework": "next-app-router"},
        "api": {"spec_url": dcfg.spec_url, "commit": dcfg.api_commit,
                "openapi_version": spec.get("openapi")},
        "ga4": {"property": dcfg.ga4_property, "window_days": dcfg.ga4_window_days},
        "extractor_version": dcfg.extractor_version,
        "inventory_hash": _inventory_hash(facts),
    }
    return {"meta": meta, **facts}


def main() -> None:
    ap = argparse.ArgumentParser(description="TrainGen Layer 1 — feature inventory extraction")
    ap.add_argument("--spec", help="OpenAPI spec URL or local path (overrides config)")
    ap.add_argument("--app", help="Path to the Next.js app/ directory (overrides config)")
    ap.add_argument("--out", default=str(prod_config.OUT / "discovery" / "feature_inventory.json"))
    args = ap.parse_args()

    dcfg = dconfig.load_discovery_config()
    if args.spec:
        dcfg.spec_url = args.spec
    if args.app:
        dcfg.frontend_app_dir = args.app

    inv = build_inventory(dcfg)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"inventory: {len(inv['endpoints'])} endpoints, "
          f"{len(inv['routes'])} routes, {len(inv['testid_gaps'])} testid gaps")
    print(f"hash: {inv['meta']['inventory_hash']}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
