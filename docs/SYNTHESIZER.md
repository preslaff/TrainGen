# SYNTHESIZER.md — Layer 2 Instruction Set

**Addendum to `DISCOVERY.md` and `FEATURE_INVENTORY.md`.** Defines the constrained LLM that consumes `feature_inventory.json` (Layer 1) and emits provenance-tagged `drafts.yaml` for human approval. This is the one judgment step in discovery; everything around it is deterministic.

Contains: the output schema, the operating rules, and the **ready-to-use instruction set** (the prompt). No extraction code.

---

## 1. Position & mandate

```
feature_inventory.json ──▶ [ SYNTHESIZER (LLM) ] ──▶ drafts.yaml ──▶ human gate ──▶ scenarios.yaml
```

The synthesizer does exactly the work code can't: reconcile sources, decompose features into user tasks, sequence steps, bind locators, tag provenance, split by role. It does **not** browse the live app (Layer 3), rank importance beyond passing through GA4 (review rubric), or write voiced narration (`script.py`).

Two non-negotiables that shape everything: **never invent a selector** (bind only to inventoried controls), and **never overclaim evidence** (emit pre-crawl provenance only).

---

## 2. Operating mode (determinism within an LLM step)

- **Temperature 0.** Same inventory ⇒ same drafts (as close as an LLM allows).
- **Batched per resource group.** The orchestrator groups `endpoints` + `routes` by `resource_hint` and calls the synthesizer once per feature group. Bounded context, reviewable diffs, per-feature caching keyed on the group's slice of `inventory_hash`.
- **Schema-gated output.** Raw output is validated against the `drafts.yaml` schema before it's accepted; a malformed draft is rejected and regenerated, never hand-fixed silently.

---

## 3. Output schema — `drafts.yaml`

Extends the `scenarios.yaml` schema (BLUEPRINT) with discovery metadata the reviewer and Layer 3 consume. Fields beyond the SSOT schema are marked **+**.

```yaml
discovery_run:                      # + provenance of this synthesis pass
  inventory_hash: "sha256:9f2c…"
  resource_group: "partners"
  synthesizer_version: "0.1.0"
  generated_at: "2026-06-15T09:10:00Z"

drafts:
  - scenario_id: add-partner-profile
    title: { bg: "...", en: "..." }      # metadata translation OK (NOT narration)
    role: admin
    goal: "..."                          # one objective; seeds narration downstream
    entry_route: "/admin/partners"
    needs_seed_record: false             # + true if task acts on an existing record
    destructive: false                   # + true for DELETE / irreversible actions
    usage_rank: 9                        # + pass-through from GA4; reviewer adds rubric
    provenance: "code:route+endpoint"    # + weakest step provenance (the risk floor)
    source_refs:                         # + traceability back to inventory
      routes: ["/admin/partners", "/admin/partners/new"]
      endpoints: ["create_partner", "publish_partner"]
    steps:
      - id: open-new-form
        intent: "Open the new-partner form from the partners list"
        locator: { testid: "partners-add-btn" }
        action: click
        value: null
        emphasis: highlight
        settle_ms: 800
        provenance: "code:route"         # + pre-crawl, per-step
        bound_via: testid                # + testid | label | role | unbound
    open_questions:                      # + everything the reviewer/crawl must resolve
      - "No data-testid on 'Category'; bound by label (i18n partners.form.category). Confirm in crawl."
```

---

## 4. Provenance — what the synthesizer may assign

It only knows what's in code/spec, so it emits **pre-crawl** values. Layer 3 promotes them.

| Synthesizer emits | Meaning | Layer 3 promotes to (DISCOVERY §7) |
|---|---|---|
| `code:route+endpoint` | Control in a route **and** backed by an endpoint action/field | `route+endpoint+crawl` |
| `code:route` | Control in a route, no endpoint backing (pure-UI nav) | confirmed, or `crawl-only` |
| `code:endpoint` | Endpoint action exists, **no matching control found** | `endpoint+crawl`, or dropped |
| `inferred` | Step added that isn't directly evidenced (implied confirmation, etc.) | crawl-verified **or dropped** |

Scenario-level `provenance` = the **weakest** step value, so the reviewer sees the riskiest link first. The synthesizer must never write `crawl` in any provenance — that evidence doesn't exist yet.

---

## 5. The instruction set (drop-in prompt)

> Supplied to the model with the resource-group slice of `feature_inventory.json` as input. Temperature 0.

```
ROLE
You design software-training scenario DRAFTS for a tourism platform. You convert a
deterministic feature inventory into ordered, locator-bound user tasks. You are the
only judgment step in discovery: you reconcile sources, decompose features into tasks,
sequence steps, bind locators, and tag provenance — nothing more.

INPUT
A slice of feature_inventory.json for ONE resource group, containing: endpoints[],
routes[], i18n, usage[], testid_gaps[]. Field meanings are defined by the inventory
contract. Treat all of it as ground truth. You have NO other knowledge of the app.

PROCEDURE
1. RECONCILE. Join endpoints and routes on resource_hint. Use task_verb_hint and
   maps_to_field_hint as starting points; correct obvious naming mismatches between an
   endpoint field, a route control, and its i18n label. If a join is unclear, do not
   force it — record it in open_questions.
2. SELECT TASKS. Emit a scenario only for endpoints that represent a real user task:
   create, edit, publish, remove, search. Fold list/view (GET collection / GET by id)
   into other scenarios as navigation or verification steps, not standalone scenarios.
   Skip health checks, webhooks, and internal/utility endpoints.
3. SEQUENCE STEPS. Order each task as a real user performs it, end to end:
   (a) reach the surface (nav/link to entry_route),
   (b) trigger the form/modal (the "Add"/"Edit" control),
   (c) fill REQUIRED request_fields, in the order the controls appear in routes.controls,
   (d) include an optional field only if it is pedagogically necessary,
   (e) submit/save,
   (f) a final verification step that shows the success state (from response_states).
   Keep scenarios to 4–9 steps. Split anything longer into multiple scenarios.
4. BIND LOCATORS. For every step, bind to a control that EXISTS in routes.controls.
   Priority: testid > i18n_key/label > role+name. Set bound_via accordingly.
   If no control exists for a required action, emit the step with the best available
   reference, set bound_via=unbound, provenance=code:endpoint or inferred, and add an
   open_question. NEVER invent a selector.
5. SPLIT BY ROLE. role = the route role_gate, cross-checked against endpoint security.
   Each scenario is single-role. If a feature serves both roles differently, emit two
   scenarios. If role_gate and security conflict, pick the stricter and add an
   open_question.
6. TAG PROVENANCE. Per step, assign one of: code:route+endpoint, code:route,
   code:endpoint, inferred (definitions given). Scenario provenance = the weakest step.
   You MUST NOT write "crawl" anywhere.
7. FLAGS. needs_seed_record = true if the task acts on an existing record (route has
   dynamic_params or endpoint path has {id}). destructive = true for DELETE/irreversible
   actions (also set needs_seed_record). usage_rank = pass through from usage[]; do not
   compute any other priority.

DEFAULTS
- emphasis: highlight for clicks/nav; zoom for field fills and the final confirmation;
  none for waits.
- settle_ms: click 800, fill 400, select 600, submit/save 1200, publish/destructive 1500.
- value: realistic sample data; for BG-facing fields use plausible Bulgarian content.

HARD RULES
MUST: output valid drafts.yaml only — no prose, no markdown fences.
MUST: bind every step locator to an inventoried control, or mark it unbound + open_question.
MUST: give every scenario a goal and title{bg,en}, and every step exactly one intent.
MUST: tag provenance on every scenario and every step.
MUST NOT: write voiced narration (intent is a short objective, not a spoken sentence).
MUST NOT: browse, assume, or reference any element not present in the input.
MUST NOT: rank importance beyond passing through usage_rank.
MUST NOT: emit a reconciled "feature" object — emit scenarios only.

SELF-CHECK (verify before output; if any fails, fix and re-verify)
[ ] every step locator exists in routes.controls OR bound_via=unbound + open_question
[ ] every scenario has 4–9 steps; longer tasks were split
[ ] one intent per step; no spoken sentences
[ ] title{bg,en} + goal present on every scenario
[ ] provenance on every scenario and step; no "crawl" used
[ ] role single-valued; conflicts flagged
[ ] needs_seed_record / destructive set correctly
[ ] no invented selectors; no feature objects
OUTPUT: drafts.yaml for this resource group, nothing else.
```

---

## 6. Edge handling (must be covered by open_questions, never silently)

| Situation | Synthesizer behaviour |
|---|---|
| Endpoint action with no matching control | Emit step, `bound_via: unbound`, `provenance: code:endpoint`, open_question "needs locator — confirm/​add in crawl". |
| Control with no endpoint backing (pure UI) | Allowed as `code:route` step (nav, toggles). |
| `role_gate` ≠ endpoint `security` | Choose stricter, open_question with both values. |
| `resource_hint` join ambiguous | Don't force; open_question naming the candidates. |
| Required field has no control | Step `unbound` + open_question; do not skip the field silently. |
| DELETE / irreversible | `destructive: true`, `needs_seed_record: true`, `settle_ms: 1500`. |
| Missing testid (in `testid_gaps`) | Bind by label/i18n, `bound_via: label`, open_question referencing the suggested_testid. |
| Task > 9 steps | Split into multiple scenarios sharing the resource group. |

---

## 7. Worked example (inventory slice → drafts.yaml)

**Input (abbreviated):** the `partners` group from FEATURE_INVENTORY §4 — `create_partner` (POST, fields business_name/category/region, security admin), `publish_partner`, routes `/admin/partners` and `/admin/partners/new` (role_gate admin), category control missing its testid.

**Output (one draft):**

```yaml
discovery_run:
  inventory_hash: "sha256:9f2c…"
  resource_group: "partners"
  synthesizer_version: "0.1.0"
  generated_at: "2026-06-15T09:10:00Z"
drafts:
  - scenario_id: add-partner-profile
    title: { bg: "Добавяне на партньорски профил", en: "Adding a partner profile" }
    role: admin
    goal: >
      Teach an admin to create a new partner profile, fill the required fields,
      and publish it so it appears in search.
    entry_route: "/admin/partners"
    needs_seed_record: false
    destructive: false
    usage_rank: 9
    provenance: "code:route"          # weakest step (nav) is code:route
    source_refs:
      routes: ["/admin/partners", "/admin/partners/new"]
      endpoints: ["create_partner", "publish_partner"]
    steps:
      - { id: open-new-form, intent: "Open the new-partner form from the list",
          locator: { testid: "partners-add-btn" }, action: click, value: null,
          emphasis: highlight, settle_ms: 800, provenance: "code:route", bound_via: testid }
      - { id: enter-name, intent: "Enter the partner's business name",
          locator: { testid: "partner-business-name" }, action: fill,
          value: "Хотел Морска Звезда", emphasis: zoom, settle_ms: 400,
          provenance: "code:route+endpoint", bound_via: testid }
      - { id: select-category, intent: "Choose the partner category",
          locator: { label: "Category" }, action: select, value: "accommodation",
          emphasis: highlight, settle_ms: 600,
          provenance: "code:route+endpoint", bound_via: label }
      - { id: select-region, intent: "Set the region used for location search",
          locator: { testid: "partner-region" }, action: select, value: "Varna",
          emphasis: none, settle_ms: 600,
          provenance: "code:route+endpoint", bound_via: testid }
      - { id: save-draft, intent: "Save the profile as a draft",
          locator: { testid: "partner-save-draft" }, action: click, value: null,
          emphasis: highlight, settle_ms: 1200, provenance: "code:route", bound_via: testid }
      - { id: publish, intent: "Publish so the profile appears in search",
          locator: { testid: "partner-publish" }, action: click, value: null,
          emphasis: zoom, settle_ms: 1500, provenance: "code:route+endpoint", bound_via: testid }
    open_questions:
      - "Category select has no data-testid (gap: suggested 'partner-category'); bound by label. Confirm in crawl."
      - "Endpoint security=admin matches route role_gate=admin. OK."
```

Note how it maps back to the hand-written `scenarios.yaml` starter — the synthesizer reconstructs that flow from inventory facts alone, then flags the one weak spot (the missing testid) instead of hiding it.

---

## 8. Handoff to Layer 3

`drafts.yaml` carries everything the caged crawler needs: which locators to confirm, which `unbound`/`code:endpoint` steps need a live target, which `open_questions` to resolve, and which scenarios need a seeded record. Layer 3 promotes provenance, fills sub-steps, and either answers or escalates each open_question — then the human approves the result into `scenarios.yaml`.
