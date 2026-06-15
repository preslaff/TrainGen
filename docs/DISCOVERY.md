# DISCOVERY.md — TrainGen Feature Discovery Design

**Addendum to `BLUEPRINT.md`.** Defines how TrainGen learns *what to teach* before it records anything. Stack-specific: **FastAPI + OpenAPI/Swagger** backend, **Next.js (App Router)** frontend.

This is a design document. No implementation — it specifies inputs, responsibilities, boundaries, and outputs for the discovery stage.

---

## 1. The governing principle

Discovery is **two distinct jobs**, and conflating them is the main failure mode:

| Job | Question | Right tool |
|---|---|---|
| **Enumerate** | What features and tasks exist? | Deterministic extraction from code + spec |
| **Capture** | What are the real selectors, states, sub-steps? | Bounded live crawl of the running app |

Blind-crawling the running app captures well but enumerates badly — it misses anything behind a modal, a wizard step, a role gate, or a data state the crawler never triggered. You own the repos and the spec, so **enumerate from sources that already list your features**, then crawl only to validate and fill gaps.

---

## 2. Three layers, one of them agentic

Reject "an agent does discovery." Most of discovery is deterministic and **must stay reproducible**, because the payoff is wiring this to CI so videos regenerate on each release. The same commit must always yield the same scenario set — an autonomous explorer breaks that.

```
LAYER 1 — EXTRACT (deterministic)      → enumeration, instant, reproducible
LAYER 2 — SYNTHESIZE (LLM, constrained)→ judgment: features → tasks → draft scenarios
LAYER 3 — VERIFY (one caged agent)     → live perception: confirm + expand + flag
```

Agency is confined to Layer 3, and even there it is caged (Section 6). Everything that *can* be deterministic *is* deterministic.

---

## 3. Layer 1 — Extraction sources

Two repos plus one spec. They reconcile on the **resource noun** (Section 4).

### 3a. FastAPI / OpenAPI — the task verbs (highest signal for *what users do*)

The Swagger spec (`/openapi.json`) is a machine-readable inventory of every capability. Extract:

| From the spec | Yields |
|---|---|
| **`tags`** | Feature grouping. Endpoints sharing a tag = one feature area (e.g. `partners`, `leads`). |
| **HTTP method + path** | The task verb, for free. `POST`=create, `PUT`/`PATCH`=edit, `DELETE`=remove, `GET …/search`=find. A mutation endpoint ≈ a task ≈ a candidate video. |
| **`operationId` / `summary` / `description`** | Human-readable task name and intent — seeds the scenario title and goal. |
| **`requestBody` schema** | The fields a user must supply → maps directly to the form fields the video must fill. |
| **`security` / auth dependencies** | Which endpoints are gated → first signal of admin-vs-member split. |
| **`responses`** | Success/error states worth showing (e.g. the "published" confirmation). |

This layer is the backbone: it produces a near-complete **task list** independent of how the UI happens to look.

### 3b. Next.js App Router — the feature surfaces and UI flow

The `app/` tree *is* the feature map. Extract (statically, no execution):

| From the frontend | Yields |
|---|---|
| **`app/**/page.tsx` tree** | Every route = a feature surface / a video setting. |
| **Route groups `(group)`** | Organizational only — no URL effect; don't treat as a step. |
| **Dynamic segments `[id]`** | Detail/edit surfaces; flag that the video needs a seeded record to exist. |
| **`layout.tsx` nesting** | Navigation context — how a user reaches a page (feeds entry_route + early steps). |
| **`middleware.ts` / route guards** | Role gating from code → splits admin vs member flows *without guessing*. |
| **Form components, inputs, labels, selects, submit buttons** | Per-page action detail → step granularity. |
| **`data-testid` attributes present** | Stable locators to prefer. |
| **`data-testid` *absent* on key controls** | The **"add test-ids here" list** handed back to the dev team. |
| **i18n catalogs (BG/EN), if present** | Canonical UI strings in both languages → better label-locators *and* more accurate narration/subtitles, for free. |

### 3c. GA4 — prioritization only (not enumeration)

Top pages and event funnels tell you which features are actually used. This is the **80/20 filter**: it never adds features, it ranks them so you build the 8 videos that matter before the 40 that don't.

**Layer 1 output → `feature_inventory.json`:** facts only, zero judgment, fully deterministic. Routes, endpoints, fields, role gates, test-id coverage, usage weights.

---

## 4. Reconciliation — the join key

A feature lives in three places; stitch them on the **resource noun** in the path:

```
Next.js route   /admin/partners , /admin/partners/[id]
FastAPI tag     partners
FastAPI paths   POST /partners · PUT /partners/{id} · DELETE /partners/{id} · GET /partners/search
UI form         business name · category · region · publish
        ▼ reconcile ▼
feature: "partner profiles"
  tasks: create · edit · publish · search · remove
  surfaces: list page, new page, edit page
  role: admin (from middleware + endpoint security)
```

Each reconciled **task** becomes one candidate scenario. This mapping is the core of discovery — *feature ≠ scenario; a task a user completes = scenario*, and the API verbs are what convert one into the other.

---

## 5. Layer 2 — Synthesis (the LLM's job)

The LLM does only what code can't: judgment. It receives `feature_inventory.json` and produces draft entries in the existing `scenarios.yaml` schema (defined in `BLUEPRINT.md` / starter manifest — not redefined here).

Its bounded responsibilities:

1. **Reconcile** the three sources into a clean feature list (resolve naming mismatches between route, tag, and form labels).
2. **Decompose** each feature into discrete user tasks using the API verbs.
3. **Sequence** each task into ordered steps a real user would perform end to end.
4. **Bind** each step to a locator from the inventory — **never invent selectors**; use only elements that were actually extracted (priority: testid > label > role+name).
5. **Tag provenance** on every draft (Section 7).
6. **Split by role** using the gate signals, not assumption.

Hard constraints in its instructions: output valid manifest YAML only; reference only inventoried elements; keep scenarios to 4–9 steps and split longer flows; one `intent` per step (that line later generates the narration).

What it must **not** do: browse the live app, decide what's "important" (that's the rubric in Section 8 + human review), or write narration text (that happens later in `script.py`).

---

## 6. Layer 3 — Live verification (the one caged agent)

Code tells you a "create partner" modal *exists*; it can't see the four conditionally-rendered steps *inside* it, or confirm that a label still matches after a copy change. That needs closed-loop perception — open, observe, decide, expand. This is the only place agency is justified.

The cage:

- **Role-scoped:** runs once authenticated as admin, once as member — never mixes.
- **Read-mostly:** confirms locators resolve and captures resulting dialog/wizard state; any mutation happens against the **seeded demo tenant**, never prod (per `BLUEPRINT.md` §11).
- **Bounded:** hard step ceiling per scenario; no open-ended exploration.
- **Write-restricted:** emits to `drafts.yaml` only; cannot touch the SSOT.

Its three outputs per draft scenario:

1. **Confirm** every code-derived locator actually exists in the running UI.
2. **Expand** sub-steps that only appear at runtime (modal stages, wizard pages, conditional fields).
3. **Flag** missing test-ids and any locator that resolved ambiguously.

---

## 7. Provenance — so review is triage, not authoring

Every draft scenario and step carries where its evidence came from:

| Provenance | Meaning | Reviewer action |
|---|---|---|
| `route + endpoint + crawl` | Triple-confirmed | Ship — spot check only |
| `endpoint + crawl` | Backed by API + live UI, no clean route | Quick read |
| `crawl-only` | Seen live, not in code/spec | **Verify deliberately** — most fragile |
| `inventory-only` | Enumerated, not yet crawl-confirmed | Confirm locators before recording |

This turns the human gate from "write scenarios" into "approve a well-evidenced draft."

---

## 8. Prioritization rubric — which drafts become videos first

Score each candidate 1–3 on three axes; build top-of-stack first:

- **Frequency** — GA4 usage. High-traffic flows lead.
- **Onboarding-criticality** — platform is unusable without it (login, create first profile).
- **Confusion** — generates the most "how do I…" questions.

High on all three → record now. Low on all three → skip, or a one-line text doc instead of a video.

---

## 9. Human gate

Discovery **never auto-commits** — same human-in-the-loop pattern used elsewhere in your stack. The flow ends at:

```
drafts.yaml  →  human approve / trim / merge  →  scenarios.yaml (SSOT)
```

Because Layers 1–2 deliver near-complete enumeration with provenance, the human is editing a strong draft, not authoring from a blank file.

---

## 10. Reproducibility & CI — why this design exists

The whole layered structure earns its keep at release time:

```
on release tag → re-extract from the new commit → re-synthesize → re-verify vs staging
              → diff against current SSOT → surface only changed/new/removed scenarios for re-approval
```

Deterministic extraction guarantees the diff is meaningful (same commit ⇒ same inventory). The LLM and the agent operate on top of that stable base, so discovery becomes a **repeatable release step**, not a one-off manual audit. This is the line between "we made some training videos once" and "our training library stays in sync with the product."

---

## 11. Stage outputs (artifact contract)

| Stage | Output | Nature |
|---|---|---|
| Layer 1 — Extract | `feature_inventory.json` | Deterministic facts |
| Layer 2 — Synthesize | draft scenarios (in `drafts.yaml`) | LLM judgment, provenance-tagged |
| Layer 3 — Verify | enriched + flagged `drafts.yaml` | Live-confirmed, test-id gaps listed |
| Human gate | `scenarios.yaml` | Approved SSOT, feeds the record pipeline |

`scenarios.yaml` then enters the production pipeline in `BLUEPRINT.md` (`script → narrate → choreograph → record → subtitle → compose`).
