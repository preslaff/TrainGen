"""Layer 2 — Synthesize (SYNTHESIZER.md). The one judgment step in discovery.

Consumes feature_inventory.json, groups it by resource, and for each group asks the LLM
to reconcile sources → decompose into user tasks → sequence steps → bind locators to
INVENTORIED controls only → tag pre-crawl provenance. Output is validated against the
drafts schema AND semantically (every locator binds to an inventoried control or is marked
unbound; provenance never says "crawl"; 4–9 steps; single role); invalid output is
regenerated, never hand-fixed. Per-group results are cached on the group's slice hash, so
an unchanged feature is never re-synthesized. Emits out/discovery/drafts.yaml.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from .. import config as prod_config
from ..cache import digest
from . import config as dconfig
from .llm import get_backend

PROMPT_VERSION = "0.1.0"

PROVENANCE = ["code:route+endpoint", "code:route", "code:endpoint", "inferred"]
# weakest first — scenario provenance must equal the weakest step (DISCOVERY §7 / SYNTHESIZER §4)
_PROV_RANK = {"inferred": 0, "code:endpoint": 1, "code:route": 2, "code:route+endpoint": 3}
BOUND_VIA = ["testid", "label", "role", "unbound"]
ACTIONS = ["click", "fill", "select", "hover", "wait", "navigate"]
EMPHASIS = ["highlight", "zoom", "none"]

SYSTEM = """\
ROLE
You design software-training scenario DRAFTS for a tourism platform. You convert a
deterministic feature inventory into ordered, locator-bound user tasks. You are the only
judgment step in discovery: reconcile sources, decompose features into tasks, sequence
steps, bind locators, tag provenance — nothing more.

INPUT
A slice of feature_inventory.json for ONE resource group: endpoints[], routes[], i18n,
usage[], testid_gaps[]. Treat it as ground truth. You have NO other knowledge of the app.

PROCEDURE
1. RECONCILE endpoints and routes. The group's own `routes` may be empty or may not match
   the endpoints' noun. `candidate_routes` are same-role surfaces from elsewhere in the app
   whose noun may differ (e.g. an `announcements` API surfaced under a `communications`
   page). Pick the best-matching surface from `routes` OR `candidate_routes`, bind to ITS
   controls, and list the chosen route(s) in source_refs.routes. If no surface plausibly
   matches, leave steps unbound and record it in open_questions — do not force a join.
2. SELECT TASKS: emit a scenario only for real user tasks (create, edit, publish, remove,
   search). Fold list/view into other scenarios as nav/verification, not standalone
   scenarios. Skip health checks, webhooks, internal/utility endpoints.
3. SEQUENCE steps as a real user performs them: reach the surface, trigger the form/modal,
   fill REQUIRED request_fields in the order controls appear, optional field only if
   pedagogically necessary, submit/save, then a final step showing the success state.
   Keep scenarios to 4-9 steps; split anything longer.
4. BIND every step locator to a control that EXISTS in routes[].controls OR
   candidate_routes[].controls. Priority: testid > i18n_key/label > role+name. Set
   bound_via. NEVER bind by role alone without a specific accessible `name`, and never
   invent a selector. If no inventoried control matches an action, emit the step with
   bound_via=unbound, an empty locator {}, provenance=code:endpoint or inferred, and an
   open_question — an honest unbound step is correct; a guessed locator is not.
5. SPLIT BY ROLE: role = route role_gate, cross-checked against endpoint security. One role
   per scenario. If a feature serves both roles, emit two scenarios. On conflict pick the
   stricter and add an open_question.
6. TAG PROVENANCE per step (code:route+endpoint | code:route | code:endpoint | inferred).
   Scenario provenance = the WEAKEST step value. You MUST NOT write "crawl" anywhere.
7. FLAGS: needs_seed_record=true if the task acts on an existing record (dynamic route or
   {id} path). destructive=true for DELETE/irreversible (also set needs_seed_record).
   usage_rank = pass through from usage[] (0 if absent).

DEFAULTS
- emphasis: highlight for clicks/nav; zoom for fills and the final confirmation; none for waits.
- settle_ms: click 800, fill 400, select 600, submit/save 1200, publish/destructive 1500.
- value: realistic sample data; for BG-facing fields use plausible Bulgarian content.

HARD RULES
- intent is a short objective, NOT a spoken sentence. Do not write voiced narration.
- Reference only elements present in the input. Do not browse or assume.
- Every scenario has a goal and title{bg,en}; every step has exactly one intent.
- Tag provenance on every scenario and step; never "crawl".
Return output conforming exactly to the provided JSON schema — nothing else.
"""


def _draft_schema() -> dict:
    locator = {
        "type": "object", "additionalProperties": False,
        "properties": {"testid": {"type": "string"}, "label": {"type": "string"},
                       "role": {"type": "string"}, "name": {"type": "string"}},
    }
    step = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "id": {"type": "string"}, "intent": {"type": "string"},
            "locator": locator, "action": {"type": "string", "enum": ACTIONS},
            "value": {"type": "string"},
            "emphasis": {"type": "string", "enum": EMPHASIS},
            "settle_ms": {"type": "integer"},
            "provenance": {"type": "string", "enum": PROVENANCE},
            "bound_via": {"type": "string", "enum": BOUND_VIA},
        },
        "required": ["id", "intent", "locator", "action", "emphasis",
                     "settle_ms", "provenance", "bound_via"],
    }
    scenario = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "scenario_id": {"type": "string"},
            "title": {"type": "object", "additionalProperties": False,
                      "properties": {"bg": {"type": "string"}, "en": {"type": "string"}},
                      "required": ["bg", "en"]},
            "role": {"type": "string"}, "goal": {"type": "string"},
            "entry_route": {"type": "string"},
            "needs_seed_record": {"type": "boolean"},
            "destructive": {"type": "boolean"},
            "usage_rank": {"type": "integer"},
            "provenance": {"type": "string", "enum": PROVENANCE},
            "source_refs": {"type": "object", "additionalProperties": False,
                            "properties": {"routes": {"type": "array", "items": {"type": "string"}},
                                           "endpoints": {"type": "array", "items": {"type": "string"}}},
                            "required": ["routes", "endpoints"]},
            "steps": {"type": "array", "items": step},
            "open_questions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["scenario_id", "title", "role", "goal", "entry_route",
                     "needs_seed_record", "destructive", "usage_rank", "provenance",
                     "source_refs", "steps", "open_questions"],
    }
    return {"type": "object", "additionalProperties": False,
            "properties": {"drafts": {"type": "array", "items": scenario}},
            "required": ["drafts"]}


_SCOPES = ("admin", "member")


def _group_scopes(endpoints: list) -> set:
    """All role scopes a group's endpoints touch (path segments or security), plus
    `public` always — a feature can span admin (review) and public (submit), so candidate
    routes must cover every scope present, not just the dominant one."""
    scopes = set()
    for e in endpoints:
        for seg in e.get("path", "").strip("/").split("/"):
            if seg in _SCOPES:
                scopes.add(seg)
                break
        for sec in e.get("security", []):
            if sec in _SCOPES:
                scopes.add(sec)
    scopes.add("public")
    return scopes


def group_by_resource(inventory: dict) -> dict:
    """Join endpoints and routes on resource_hint; attach the per-group i18n/usage/gaps
    slices (SYNTHESIZER §2). Also attach `candidate_routes` — same-role surfaces from
    elsewhere in the app whose noun may differ from the endpoints' (e.g. an `announcements`
    API surfaced under a `communications` page) — so Layer 2 can reconcile across nouns."""
    groups: dict = {}
    for e in inventory.get("endpoints", []):
        groups.setdefault(e["resource_hint"], {"endpoints": [], "routes": []})["endpoints"].append(e)
    for r in inventory.get("routes", []):
        groups.setdefault(r["resource_hint"], {"endpoints": [], "routes": []})["routes"].append(r)

    all_routes = inventory.get("routes", [])
    for res, g in groups.items():
        own = {r["route"] for r in g["routes"]}
        scopes = _group_scopes(g["endpoints"])
        g["resource"] = res
        g["i18n"] = inventory.get("i18n", {})
        g["usage"] = [u for u in inventory.get("usage", []) if u.get("route") in own]
        g["testid_gaps"] = [gp for gp in inventory.get("testid_gaps", []) if gp.get("route") in own]
        g["candidate_routes"] = [
            r for r in all_routes
            if r["route"] not in own and r.get("controls")
            and r.get("role_gate") in scopes
        ] if g["endpoints"] else []
    return groups


def _control_index(group: dict):
    testids, labels, roles = set(), set(), set()
    for r in group["routes"] + group.get("candidate_routes", []):
        for c in r.get("controls", []):
            if c.get("testid"):
                testids.add(c["testid"])
            if c.get("label"):
                labels.add(c["label"])
            if c.get("i18n_key"):
                labels.add(c["i18n_key"])
            if c.get("role"):
                roles.add(c["role"])
    i18n_strings = (group.get("i18n") or {}).get("strings") or {}
    for key, by_lang in i18n_strings.items():
        labels.add(key)
        for v in (by_lang or {}).values():
            labels.add(v)
    return testids, labels, roles


def validate_drafts(result: dict, group: dict) -> list:
    """Semantic checks the JSON schema can't express (SYNTHESIZER §5 self-check)."""
    errs = []
    if not isinstance(result, dict) or "drafts" not in result:
        return ["missing 'drafts' array"]
    testids, labels, roles = _control_index(group)
    for s in result["drafts"]:
        sid = s.get("scenario_id", "<no id>")
        if not (s.get("title", {}).get("bg") and s["title"].get("en")):
            errs.append(f"{sid}: title.bg/en required")
        if not s.get("goal"):
            errs.append(f"{sid}: goal required")
        if not s.get("role"):
            errs.append(f"{sid}: role required (single value)")
        steps = s.get("steps", [])
        if not (4 <= len(steps) <= 9):
            errs.append(f"{sid}: {len(steps)} steps (must be 4-9; split longer tasks)")
        for st in steps:
            sp = st.get("provenance")
            if sp not in PROVENANCE:
                errs.append(f"{sid}/{st.get('id')}: bad/crawl provenance {sp!r}")
            bv, loc = st.get("bound_via"), st.get("locator", {})
            if bv == "testid" and loc.get("testid") not in testids:
                errs.append(f"{sid}/{st.get('id')}: testid {loc.get('testid')!r} not in inventory")
            elif bv == "label" and loc.get("label") not in labels:
                errs.append(f"{sid}/{st.get('id')}: label {loc.get('label')!r} not in inventory")
            elif bv == "role" and (not loc.get("name") or loc.get("role") not in roles
                                   or loc.get("name") not in labels):
                errs.append(f"{sid}/{st.get('id')}: role+name not in inventory "
                            "(bind by name, or mark unbound)")
            elif bv == "unbound" and not s.get("open_questions"):
                errs.append(f"{sid}/{st.get('id')}: unbound step needs an open_question")
    # scenario provenance is derived (the weakest step) — normalized, not validated
    return errs


def normalize(result: dict) -> dict:
    """Derive each scenario's provenance from its steps (the weakest = risk floor), so a
    model inconsistency on this computed field never fails an otherwise-valid group."""
    for s in result.get("drafts", []):
        provs = [st.get("provenance", "inferred") for st in s.get("steps", [])]
        if provs:
            s["provenance"] = min(provs, key=lambda p: _PROV_RANK.get(p, 0))
    return result


def _group_slice(group: dict) -> dict:
    return {k: group.get(k) for k in
            ("resource", "endpoints", "routes", "candidate_routes", "i18n", "usage", "testid_gaps")}


def synthesize_group(group: dict, cfg, backend) -> dict:
    """Generate + validate one group's drafts, regenerating on validation failure."""
    schema = _draft_schema()
    payload = _group_slice(group)
    user = ("Resource group inventory (JSON):\n"
            + json.dumps(payload, ensure_ascii=False, indent=2))
    last_errs: list = []
    for attempt in range(cfg.synth_max_retries + 1):
        prompt = user if attempt == 0 else (
            user + "\n\nYour previous output had these problems — fix them:\n- "
            + "\n- ".join(last_errs))
        result = normalize(backend.complete_json(SYSTEM, prompt, schema))
        last_errs = validate_drafts(result, group)
        if not last_errs:
            return {"drafts": result["drafts"], "errors": []}
    return {"drafts": result.get("drafts", []), "errors": last_errs}


def run(inventory: dict, cfg=None, backend=None, resources=None) -> dict:
    cfg = cfg or dconfig.load_discovery_config()
    backend = backend or get_backend(cfg)
    out_dir = prod_config.OUT / "discovery"
    cache_dir = out_dir / "drafts_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    inv_hash = inventory.get("meta", {}).get("inventory_hash", "")
    groups = group_by_resource(inventory)
    only = set(resources) if resources else None   # synthesize just these groups (cheap trial)
    all_drafts, failures = [], {}

    for res, group in sorted(groups.items()):
        if only is not None and res not in only:
            continue
        if not group["endpoints"]:           # routes with no API backing — skip (nav-only)
            continue
        key = digest(_group_slice(group), cfg.synthesizer_version, PROMPT_VERSION,
                     cfg.synth_model, cfg.synth_effort)
        cache_f = cache_dir / f"{res}.json"
        hash_f = cache_dir / f"{res}.hash"
        if cache_f.exists() and hash_f.exists() and hash_f.read_text().strip() == key:
            group_drafts = json.loads(cache_f.read_text())
        else:
            out = synthesize_group(group, cfg, backend)
            if out["errors"]:
                failures[res] = out["errors"]
            group_drafts = out["drafts"]
            cache_f.write_text(json.dumps(group_drafts, ensure_ascii=False, indent=2))
            hash_f.write_text(key)
        all_drafts.extend(group_drafts)

    doc = {
        "discovery_run": {
            "inventory_hash": inv_hash,
            "synthesizer_version": cfg.synthesizer_version,
            "prompt_version": PROMPT_VERSION,
            "model": cfg.synth_model,
            "groups": len(groups),
            "failures": failures,
        },
        "drafts": all_drafts,
    }
    (out_dir / "drafts.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return doc
