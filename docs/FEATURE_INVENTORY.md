# FEATURE_INVENTORY.md — Layer 1 Artifact Contract

**Addendum to `DISCOVERY.md`.** Defines `feature_inventory.json` — the deterministic output of Layer 1 (Extraction) and the sole input to Layer 2 (Synthesis). Stack: **FastAPI + OpenAPI** backend, **Next.js App Router** frontend, **GA4** for usage weighting.

This is a data contract, not extraction logic.

---

## 1. Purpose & boundary

The inventory is **facts only, zero judgment.** It captures everything mechanically extractable from the repos and the spec, tags each item with deterministic breadcrumbs, and stops. It deliberately does **not** contain:

- reconciled features (route ↔ tag ↔ label joining is LLM judgment — Layer 2),
- scenarios, step ordering, or narration (downstream pipeline),
- any "importance" ranking beyond raw GA4 numbers (rubric is applied at review).

**Why the strict boundary:** reproducibility. The same two commits must always produce a byte-identical inventory (modulo timestamp). That guarantee is what makes the CI release-diff meaningful (§7). Any judgment in Layer 1 would break it.

---

## 2. Design principles

1. **Deterministic.** Same input commits ⇒ same `inventory_hash`. No network nondeterminism, no LLM, no live crawl.
2. **Source-parallel.** Backend, frontend, and analytics facts live in separate arrays. The join happens later, in Layer 2.
3. **Hint, don't decide.** Mechanical breadcrumbs (`resource_hint`, `task_verb_hint`) are provided to *accelerate* reconciliation. They are labelled as hints and the synthesizer may override them.
4. **Provenance-native.** Every record states its source, so downstream provenance tags (DISCOVERY.md §7) are traceable to here.
5. **Gap-surfacing.** Missing `data-testid`s are first-class output, not a side effect — they become the dev-team ask list.

---

## 3. Top-level shape

```json
{
  "meta":         { ... },     // extraction provenance + reproducibility hash
  "endpoints":    [ ... ],     // from OpenAPI  — task verbs + fields
  "routes":       [ ... ],     // from Next.js  — feature surfaces + controls
  "i18n":         { ... },     // BG/EN canonical strings
  "usage":        [ ... ],     // from GA4      — prioritization weights
  "testid_gaps":  [ ... ]      // aggregated    — dev-team action list
}
```

---

## 4. Sections

### 4.1 `meta` — reproducibility & CI anchor

| Field | Meaning |
|---|---|
| `generated_at` | ISO timestamp. **Excluded** from `inventory_hash`. |
| `frontend.repo` / `frontend.commit` | Next.js repo + commit SHA the routes were extracted from. |
| `api.repo` / `api.commit` | FastAPI repo + commit SHA. |
| `api.spec_url` / `api.openapi_version` | Where the spec was read, e.g. `https://tourism-api.cdsv.dev/openapi.json`. |
| `ga4.property` / `ga4.window_days` | Usage source + lookback. |
| `extractor_version` | Version of the extraction stage (bump invalidates cached inventories). |
| `inventory_hash` | `sha256` of the facts payload **excluding `generated_at`**. The CI diff key — same commits ⇒ same hash ⇒ no re-discovery needed. |

```json
"meta": {
  "generated_at": "2026-06-15T09:00:00Z",
  "frontend": { "repo": "wonderful-bg-web", "commit": "a1b2c3d", "framework": "next@15-app-router" },
  "api":      { "repo": "tourism-api", "commit": "e4f5g6h", "openapi_version": "3.1",
                "spec_url": "https://tourism-api.cdsv.dev/openapi.json" },
  "ga4":      { "property": "properties/XXXX", "window_days": 30 },
  "extractor_version": "0.1.0",
  "inventory_hash": "sha256:9f2c…"
}
```

### 4.2 `endpoints[]` — the task verbs (from OpenAPI)

The backbone of *what users can do*. One record per operation.

| Field | Source | Meaning |
|---|---|---|
| `operation_id` | `operationId` | Stable id; seeds scenario id/title. |
| `method` / `path` | path item | Raw operation. |
| `tag` | `tags[0]` | Feature grouping (`partners`, `leads`…). |
| `summary` / `description` | operation | Human intent; seeds `goal`. |
| `resource_hint` | path | **Hint.** Primary resource segment (`/partners/{id}` → `partners`). |
| `task_verb_hint` | method+path | **Hint.** `POST` (no id)→`create`; `PUT`/`PATCH`+id→`edit`; `DELETE`+id→`remove`; `GET` collection→`list`; `GET …/search`→`search`; `GET`+id→`view`. |
| `request_fields[]` | `requestBody` schema | `{name, type, required, enum?}` — the fields a form must fill. |
| `security` | `security` / scopes | Role/scope gate, e.g. `["admin"]`. |
| `response_states[]` | `responses` | `{status, meaning}` — states worth showing (e.g. `201 created`). |
| `provenance` | — | always `"openapi"`. |

```json
{
  "operation_id": "create_partner",
  "method": "POST", "path": "/partners", "tag": "partners",
  "summary": "Create a partner profile",
  "resource_hint": "partners", "task_verb_hint": "create",
  "request_fields": [
    { "name": "business_name", "type": "string", "required": true },
    { "name": "category", "type": "enum", "required": true,
      "enum": ["accommodation", "restaurant", "activity"] },
    { "name": "region", "type": "string", "required": true }
  ],
  "security": ["admin"],
  "response_states": [
    { "status": 201, "meaning": "created" },
    { "status": 422, "meaning": "validation_error" }
  ],
  "provenance": "openapi"
}
```

### 4.3 `routes[]` — the feature surfaces (from Next.js App Router)

One record per `page.tsx`. Statically extracted — no execution.

| Field | Source | Meaning |
|---|---|---|
| `route` | file path | URL after base (group segments stripped). |
| `file` | — | Source path, for traceability. |
| `segments[]` | path | `{name, type}` where `type ∈ static \| dynamic \| group`. `group` = `(…)`, no URL effect. |
| `dynamic_params[]` | `[param]` | e.g. `["id"]`. Presence ⇒ detail/edit surface. |
| `resource_hint` | path | **Hint.** Resource noun for the join. |
| `layout_chain[]` | nesting | Layouts wrapping this route → navigation context. |
| `role_gate` | `middleware.ts` matcher | `admin` \| `member` \| `public` — splits flows from code. |
| `requires_seed_record` | derived | `true` when `dynamic_params` non-empty ⇒ video needs a seeded record. |
| `controls[]` | forms/components | The interactive elements (below). |
| `testid_coverage` | aggregate | `{total_controls, with_testid, missing[]}`. |
| `provenance` | — | always `"next_app_router"`. |

**`controls[]` item:**

| Field | Meaning |
|---|---|
| `label` | Visible/accessible name → label-locator + narration anchor. |
| `control_type` | `text_input` \| `select` \| `button` \| `link` \| `checkbox` … |
| `role` | ARIA role → role-locator fallback. |
| `testid` | `data-testid` if present (preferred locator); `null` if missing → feeds `testid_gaps`. |
| `name_attr` | HTML `name` — used for deterministic field matching. |
| `i18n_key` | Translation key (if i18n is wired) → links to BG/EN strings. |
| `maps_to_field_hint` | **Hint.** Deterministic name/`name_attr` match to an endpoint `request_field`. Empty if no clean match. |

```json
{
  "route": "/admin/partners/new",
  "file": "app/admin/(dashboard)/partners/new/page.tsx",
  "segments": [
    { "name": "admin", "type": "static" },
    { "name": "(dashboard)", "type": "group" },
    { "name": "partners", "type": "static" },
    { "name": "new", "type": "static" }
  ],
  "dynamic_params": [],
  "resource_hint": "partners",
  "layout_chain": ["app/layout.tsx", "app/admin/(dashboard)/layout.tsx"],
  "role_gate": "admin",
  "requires_seed_record": false,
  "controls": [
    { "label": "Business name", "control_type": "text_input", "role": "textbox",
      "testid": "partner-business-name", "name_attr": "business_name",
      "i18n_key": "partners.form.business_name", "maps_to_field_hint": "business_name" },
    { "label": "Category", "control_type": "select", "role": "combobox",
      "testid": null, "name_attr": "category",
      "i18n_key": "partners.form.category", "maps_to_field_hint": "category" },
    { "label": "Region", "control_type": "select", "role": "combobox",
      "testid": "partner-region", "name_attr": "region",
      "i18n_key": "partners.form.region", "maps_to_field_hint": "region" },
    { "label": "Save draft", "control_type": "button", "role": "button",
      "testid": "partner-save-draft", "name_attr": null,
      "i18n_key": "partners.actions.save_draft", "maps_to_field_hint": null },
    { "label": "Publish", "control_type": "button", "role": "button",
      "testid": "partner-publish", "name_attr": null,
      "i18n_key": "partners.actions.publish", "maps_to_field_hint": null }
  ],
  "testid_coverage": { "total_controls": 5, "with_testid": 4, "missing": ["category"] },
  "provenance": "next_app_router"
}
```

### 4.4 `i18n` — canonical BG/EN strings

If the frontend has translation catalogs, mirror them here keyed by `i18n_key`. Gives label-locators their exact text *and* hands `script.py`/`subtitle.py` correct strings in both languages — no machine translation of UI terms.

```json
"i18n": {
  "locales": ["bg", "en"],
  "strings": {
    "partners.form.business_name": { "bg": "Име на бизнеса", "en": "Business name" },
    "partners.form.category":      { "bg": "Категория", "en": "Category" },
    "partners.form.region":        { "bg": "Регион", "en": "Region" },
    "partners.actions.save_draft": { "bg": "Запази чернова", "en": "Save draft" },
    "partners.actions.publish":    { "bg": "Публикувай", "en": "Publish" }
  }
}
```

If no i18n is wired, this is `{"locales": [...], "strings": {}}` and locators fall back to extracted labels.

### 4.5 `usage[]` — prioritization weights (from GA4)

Enumeration is already complete without this; usage only *ranks*. Keyed by route.

```json
"usage": [
  { "route": "/admin/partners",     "views_30d": 1240, "rank": 3 },
  { "route": "/admin/partners/new", "views_30d": 410,  "rank": 9 },
  { "route": "/dashboard",          "views_30d": 5300, "rank": 1 }
]
```

Missing route ⇒ treat as low frequency, not zero priority (onboarding-critical flows can be low-traffic).

### 4.6 `testid_gaps[]` — the dev-team ask list

Aggregated from every `control` with `testid: null`. Output directly to the platform team so the next sprint hardens the locators TrainGen depends on.

```json
"testid_gaps": [
  { "route": "/admin/partners/new", "control": "category", "label": "Category",
    "suggested_testid": "partner-category" }
]
```

---

## 5. Validation rules (what makes an inventory well-formed)

- Every `endpoints[].tag` and `routes[].resource_hint` is non-empty (extractor must assign a fallback, never blank).
- Every `controls[].testid` is either a string **or** explicitly `null` (never omitted) — gaps must be visible.
- `inventory_hash` is computed over a canonicalized payload (sorted keys, `generated_at` removed) so it is stable.
- `i18n.strings` keys referenced by any `control.i18n_key` must exist, or the control's `i18n_key` is set `null`.
- No record carries a reconciled `feature` field — its presence means Layer 2 logic leaked into Layer 1.

---

## 6. What Layer 2 does with this (handoff preview)

The synthesizer reads the whole inventory and:

1. joins `endpoints` ↔ `routes` on `resource_hint` (using the `*_hint` fields as a starting point, resolving mismatches),
2. turns each `task_verb_hint` into a candidate task → draft scenario,
3. binds steps to `controls` (locator priority: `testid` > `i18n`/label > `role`),
4. splits by `role_gate` / `security`,
5. flags `requires_seed_record` scenarios for the demo-tenant seed.

The inventory gives it everything it needs without ever touching the live app — that's Layer 3's job.

---

## 7. CI behaviour

```
on release tag
  → extract frontend@new_commit + api@new_commit  → new inventory
  → compare new.inventory_hash vs stored hash
      • unchanged → skip discovery entirely (no video regeneration triggered by discovery)
      • changed   → diff records → emit changed/added/removed features for re-synthesis + re-approval
```

Because the hash is deterministic over the two commits, an unrelated backend change won't needlessly re-trigger frontend video work, and vice versa. The inventory is the unit of change detection for the entire training library.
