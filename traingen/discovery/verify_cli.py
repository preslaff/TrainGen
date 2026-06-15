"""CLI for Layer 3 — verify drafts against the running app (the caged crawl).

    python -m traingen.discovery.verify_cli [--drafts PATH]

Needs Playwright + a running seeded demo tenant (set TRAINGEN_BASE_URL and a login: block
in the manifest). Reads out/discovery/drafts.yaml, writes out/discovery/drafts.verified.yaml.
Never touches the SSOT.
"""
from __future__ import annotations

import argparse

from .. import config as prod_config
from . import config as dconfig
from . import verify


def main() -> None:
    ap = argparse.ArgumentParser(description="TrainGen Layer 3 — verify drafts (caged crawl)")
    ap.add_argument("--drafts", default=str(prod_config.OUT / "discovery" / "drafts.yaml"))
    args = ap.parse_args()

    doc = verify.run_from_file(args.drafts, cfg=dconfig.load_discovery_config())

    needs = [s["scenario_id"] for s in doc.get("drafts", [])
             if s.get("verification", {}).get("needs_review")]
    print(f"verified {len(doc.get('drafts', []))} drafts across roles "
          f"{doc['discovery_run'].get('verify_roles')}")
    if needs:
        print(f"{len(needs)} need review (unresolved/ambiguous/truncated): {', '.join(needs)}")
    print(f"-> {prod_config.OUT / 'discovery' / 'drafts.verified.yaml'}")


if __name__ == "__main__":
    main()
