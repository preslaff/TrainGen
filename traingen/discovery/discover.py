"""Discovery orchestrator — chains Layer 1 → 2 → 3 (DISCOVERY §2, §10).

    extract → feature_inventory.json → synthesize → drafts.yaml → verify → drafts.verified.yaml

Stops at the verified drafts. The human gate (merge into the SSOT) is deliberately a
separate, explicit step — discovery never auto-commits. Each stage reads/writes the
standard out/discovery/ artifacts, so stages can also be run individually.
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import config as prod_config
from . import config as dconfig
from . import extract, synthesize, verify


def run(roles=None, skip_verify: bool = False, cfg=None,
        synth_backend=None, make_driver=None) -> dict:
    cfg = cfg or dconfig.load_discovery_config()
    out_dir = prod_config.OUT / "discovery"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Layer 1 — extract (deterministic)
    inventory = extract.build_inventory(cfg)
    (out_dir / "feature_inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")

    # Layer 2 — synthesize (LLM)
    drafts = synthesize.run(inventory, cfg=cfg, backend=synth_backend)
    if roles:
        wanted = set(roles)
        drafts["drafts"] = [d for d in drafts["drafts"] if d.get("role") in wanted]

    # Layer 3 — verify (caged crawl) — optional (needs a live app)
    if not skip_verify:
        drafts = verify.verify(drafts, cfg=cfg, make_driver=make_driver)

    return {
        "endpoints": len(inventory.get("endpoints", [])),
        "routes": len(inventory.get("routes", [])),
        "drafts": len(drafts.get("drafts", [])),
        "verified": not skip_verify,
        "roles": roles,
    }
