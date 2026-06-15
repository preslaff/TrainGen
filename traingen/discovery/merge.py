"""The human gate — merge verified drafts into the SSOT (DISCOVERY §9, DESIGN §5).

Strips draft-only metadata (the DESIGN §5 drop-list), keeps the lean SSOT schema plus
needs_seed_record/destructive, and upserts selected scenarios into manifest/scenarios.yaml
by scenario_id. Discovery never auto-commits: merging requires explicit scenario selection
(or --all) and is a dry-run unless --apply is passed. Ineligible drafts (still flagged
needs_review or carrying drop_candidate steps) are skipped unless --include-unverified.

On --apply the `defaults:` header (with its comments) is preserved verbatim; only the
`scenarios:` block below it is regenerated, so the curated config is never clobbered.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .. import config as prod_config

# SSOT schema (DESIGN §5). Everything else a draft carries is dropped at the gate.
_SCENARIO_KEYS = ["scenario_id", "title", "role", "goal", "entry_route",
                  "needs_seed_record", "destructive", "steps"]
_STEP_KEYS = ["id", "intent", "locator", "action", "value", "emphasis", "settle_ms"]


def _step_to_ssot(step: dict) -> dict:
    out = {}
    for k in _STEP_KEYS:
        if k == "value":
            if step.get("value"):           # drop empty value (e.g. on clicks)
                out["value"] = step["value"]
        elif k in step:
            out[k] = step[k]
    return out


def to_ssot(draft: dict) -> dict:
    """Project a draft scenario onto the lean SSOT schema (drops provenance, bound_via,
    usage_rank, source_refs, open_questions, verification, drop_candidate, …)."""
    out = {}
    for k in _SCENARIO_KEYS:
        if k == "steps":
            out["steps"] = [_step_to_ssot(s) for s in draft.get("steps", [])]
        elif k in draft:
            out[k] = draft[k]
    return out


def eligibility(draft: dict, include_unverified: bool = False):
    """(eligible, reasons) — what would block this draft from the SSOT."""
    reasons = []
    if not include_unverified:
        if draft.get("verification", {}).get("needs_review"):
            reasons.append("needs_review")
        if any(s.get("drop_candidate") for s in draft.get("steps", [])):
            reasons.append("has drop_candidate step")
    title = draft.get("title", {})
    if not (title.get("bg") and title.get("en")):
        reasons.append("missing title{bg,en}")
    if not draft.get("steps"):
        reasons.append("no steps")
    for s in draft.get("steps", []):
        if not s.get("locator"):
            reasons.append(f"step '{s.get('id')}' has no locator")
    return (not reasons), reasons


def _split_header(text: str):
    """Return everything above the top-level `scenarios:` line, or None if not found."""
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("scenarios:"):
            return "".join(lines[:i])
    return None


def merge(drafts_doc: dict, manifest_path=None, scenario_ids=None,
          apply: bool = False, include_unverified: bool = False) -> dict:
    manifest_path = Path(manifest_path or prod_config.MANIFEST)
    text = manifest_path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    scenarios = data.setdefault("scenarios", [])
    index = {s["scenario_id"]: i for i, s in enumerate(scenarios)}

    drafts = drafts_doc.get("drafts", [])
    if scenario_ids is not None:
        wanted = set(scenario_ids)
        drafts = [d for d in drafts if d.get("scenario_id") in wanted]

    summary = {"added": [], "updated": [], "skipped": {}, "applied": False}
    for d in drafts:
        sid = d.get("scenario_id")
        ok, reasons = eligibility(d, include_unverified)
        if not ok:
            summary["skipped"][sid] = ", ".join(reasons)
            continue
        ssot = to_ssot(d)
        if sid in index:
            scenarios[index[sid]] = ssot
            summary["updated"].append(sid)
        else:
            scenarios.append(ssot)
            index[sid] = len(scenarios) - 1
            summary["added"].append(sid)

    if apply and (summary["added"] or summary["updated"]):
        header = _split_header(text)
        body = yaml.safe_dump({"scenarios": scenarios}, sort_keys=False, allow_unicode=True)
        new_text = (header + body) if header is not None else \
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        manifest_path.write_text(new_text, encoding="utf-8")
        summary["applied"] = True
    return summary
