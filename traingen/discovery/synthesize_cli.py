"""CLI for Layer 2 — synthesize drafts.yaml from feature_inventory.json.

    python -m traingen.discovery.synthesize_cli [--inventory PATH]

Requires the Anthropic SDK (`pip install anthropic`) and ANTHROPIC_API_KEY, unless a
cached result exists for every group. Reads out/discovery/feature_inventory.json by
default (run `make extract` first).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .. import config as prod_config
from . import config as dconfig
from . import synthesize


def main() -> None:
    ap = argparse.ArgumentParser(description="TrainGen Layer 2 — synthesize draft scenarios")
    ap.add_argument("--inventory",
                    default=str(prod_config.OUT / "discovery" / "feature_inventory.json"))
    args = ap.parse_args()

    inv = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    cfg = dconfig.load_discovery_config()
    doc = synthesize.run(inv, cfg=cfg)

    run = doc["discovery_run"]
    print(f"drafts: {len(doc['drafts'])} scenarios across {run['groups']} groups "
          f"(model {run['model']})")
    if run["failures"]:
        print(f"WARNING: {len(run['failures'])} group(s) failed validation after retries:")
        for res, errs in run["failures"].items():
            print(f"  [{res}] {len(errs)} issue(s); first: {errs[0]}")
    print(f"-> {prod_config.OUT / 'discovery' / 'drafts.yaml'}")


if __name__ == "__main__":
    main()
