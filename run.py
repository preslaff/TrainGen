#!/usr/bin/env python3
"""TrainGen CLI orchestrator (BLUEPRINT §12).

    python run.py --scenario add-partner-profile --lang bg
    python run.py --all --lang bg,en

Pipeline per (scenario, lang): script -> narrate -> choreograph -> record -> compose.
Each stage is cacheable; unchanged inputs are skipped. (subtitle/discover are v0.3+.)
"""
from __future__ import annotations

import argparse

from traingen import choreograph, compose, config, narrate, record, script


def run_one(scenario_id: str, lang: str, cfg: config.Config) -> None:
    scenario = config.get_scenario(scenario_id)
    tag = f"[{scenario_id}/{lang}]"

    print(f"{tag} script");       sdoc = script.run(scenario, lang, cfg)
    print(f"{tag} narrate");      ndoc = narrate.run(sdoc, cfg)
    print(f"{tag} choreograph");  tl = choreograph.run(scenario, ndoc, cfg)
    print(f"{tag} record");       rlog = record.run(scenario, tl, cfg)
    print(f"{tag} compose");      final = compose.run(rlog, ndoc, cfg)
    print(f"{tag} done -> {final}")


def main() -> None:
    ap = argparse.ArgumentParser(description="TrainGen pipeline")
    ap.add_argument("--scenario", help="scenario_id from the manifest")
    ap.add_argument("--all", action="store_true", help="run every scenario")
    ap.add_argument("--lang", default="bg", help="comma-separated, e.g. bg,en")
    ap.add_argument("--discover", action="store_true",
                    help="run discovery (extract→synthesize→verify) instead of the pipeline")
    ap.add_argument("--role", action="append", help="restrict discovery to role(s) (repeatable)")
    ap.add_argument("--skip-verify", action="store_true", help="discovery without the live crawl")
    args = ap.parse_args()

    if args.discover:
        from traingen.discovery import discover
        summary = discover.run(roles=args.role, skip_verify=args.skip_verify)
        print(f"discovery: {summary['endpoints']} endpoints, {summary['routes']} routes, "
              f"{summary['drafts']} drafts (verified={summary['verified']}, roles={summary['roles']})")
        print("review out/discovery/drafts.verified.yaml, then: "
              "python -m traingen.discovery.merge_cli --all --apply")
        return

    if not args.all and not args.scenario:
        ap.error("pass --scenario <id> or --all")

    cfg = config.load_config()
    langs = [x.strip() for x in args.lang.split(",") if x.strip()]
    ids = ([s["scenario_id"] for s in config.load_scenarios()]
           if args.all else [args.scenario])

    for sid in ids:
        for lang in langs:
            run_one(sid, lang, cfg)


if __name__ == "__main__":
    main()
