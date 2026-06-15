"""CLI for the human gate — merge verified drafts into manifest/scenarios.yaml.

    python -m traingen.discovery.merge_cli --all              # dry-run: show what would merge
    python -m traingen.discovery.merge_cli --scenario X --apply
    python -m traingen.discovery.merge_cli --all --apply --include-unverified

Dry-run by default; --apply writes the SSOT (preserving the defaults header/comments).
Reads out/discovery/drafts.verified.yaml, falling back to drafts.yaml.
"""
from __future__ import annotations

import argparse

import yaml

from .. import config as prod_config
from . import merge


def main() -> None:
    ap = argparse.ArgumentParser(description="TrainGen human gate — merge drafts into the SSOT")
    ap.add_argument("--drafts", help="defaults to drafts.verified.yaml, then drafts.yaml")
    ap.add_argument("--scenario", action="append", help="scenario_id to merge (repeatable)")
    ap.add_argument("--all", action="store_true", help="merge every eligible draft")
    ap.add_argument("--apply", action="store_true", help="write the SSOT (default is a dry-run)")
    ap.add_argument("--include-unverified", action="store_true",
                    help="merge even if flagged needs_review / has drop_candidate steps")
    args = ap.parse_args()

    if not args.all and not args.scenario:
        ap.error("pass --scenario <id> (repeatable) or --all")

    disc = prod_config.OUT / "discovery"
    path = args.drafts or (disc / "drafts.verified.yaml" if (disc / "drafts.verified.yaml").exists()
                           else disc / "drafts.yaml")
    doc = yaml.safe_load(open(path, encoding="utf-8"))

    summary = merge.merge(doc, scenario_ids=None if args.all else args.scenario,
                          apply=args.apply, include_unverified=args.include_unverified)

    mode = "APPLIED" if summary["applied"] else "dry-run (use --apply to write)"
    print(f"[{mode}] from {path}")
    if summary["added"]:
        print(f"  added:   {', '.join(summary['added'])}")
    if summary["updated"]:
        print(f"  updated: {', '.join(summary['updated'])}")
    for sid, reason in summary["skipped"].items():
        print(f"  skipped: {sid} ({reason})")
    if not summary["applied"]:
        print(f"  -> would write {len(summary['added']) + len(summary['updated'])} scenario(s) "
              f"to {prod_config.MANIFEST}")


if __name__ == "__main__":
    main()
