# DESIGN.md — TrainGen Authoritative Design

This is the **decisive top-level design** for TrainGen. Where the detail docs overlap or
conflict, **this document wins**. It defines the unified architecture, the artifact
contracts, the SSOT schema, and the configuration surface, and it points to the four
detail docs for the full specification of each piece.

TrainGen generates narrated, subtitled, dual-language (BG + EN) MP4 training videos by
driving the *real* tourism-platform UI through Playwright. It is **living documentation**:
when the platform ships a UI change, the pipeline re-runs and every affected video
regenerates. The endpoint is a CI hook on release tags.

## How to read this

| Detail doc | Owns | Status |
|---|---|---|
| `BLUEPRINT.md` | Production pipeline (script→…→compose), the timing model, overlays, original build order | Authoritative **except** §10 (discovery), which is superseded — see Resolution 1 |
| `DISCOVERY.md` | Discovery architecture (Layers 1–3), provenance, prioritization, CI diff | Authoritative for discovery design |
| `FEATURE_INVENTORY.md` | Layer 1 data contract — `feature_inventory.json` | Authoritative for the inventory schema |
| `SYNTHESIZER.md` | Layer 2 LLM instruction set — `drafts.yaml` + the prompt | Authoritative for the synthesizer |

Read DESIGN.md for *what the system is and how the parts join*; drop into a detail doc
for *the exact schema or prompt*. The phased plan lives in `ROADMAP.md`.

---

## 1. Unified architecture

Two pipelines joined at one SSOT (`manifest/scenarios.yaml`). **Discovery** decides
*what to teach* and writes draft scenarios for human approval; **production** turns an
approved scenario into video. A CI loop wraps both: on a release tag, re-discover,
diff, and regenerate only what changed.

```
                          DISCOVERY  (what to teach)
  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌────────────┐
  │  Layer 1     │──▶│  Layer 2     │──▶│  Layer 3     │──▶│ human gate │
  │  extract.py  │   │ synthesize.py│   │  verify.py   │   │ approve /  │
  │ (determin.)  │   │ (temp-0 LLM) │   │ (caged crawl)│   │ trim/merge │
  └──────────────┘   └──────────────┘   └──────────────┘   └─────┬──────┘
  feature_inventory     drafts.yaml      enriched drafts          │
        .json          (provenance-tagged)                        ▼
                                                    manifest/scenarios.yaml  ◀── SSOT
                                                                  │
                          PRODUCTION  (how to teach)              ▼
  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐
  │script.py │─▶│narrate.py│─▶│choreograph.py│─▶│record.py │─▶│subtitle.py│─▶│compose.py│─▶ MP4 + VTT
  │(narration│  │(TTS wav  │  │(timeline.json│  │(Playwright│ │ (aeneas   │  │ (FFmpeg) │
  │ + steps) │  │ + durat.)│  │  predict)    │  │ + offsets)│ │  align)   │  └──────────┘
  └──────────┘  └──────────┘  └──────────────┘  └──────────┘  └───────────┘

           ╲___________________________ CI release loop _______________________╱
           on release tag → re-extract → diff inventory_hash → regenerate changed scenarios
```

`run.py` orchestrates production per `(scenario, lang)`. `discover.py` orchestrates the
three discovery layers. Production runs the full chain **once per language** (BG and EN
narration differ in length → different pacing → record twice).

---

## 2. Decisive resolutions

These resolve every conflict across the four docs. Each is a decision, not an option.

### R1 — Discovery is layered, not monolithic
BLUEPRINT §10 (single `crawl → LLM` step) is **superseded**. The authoritative design is
DISCOVERY.md's three layers, packaged as `traingen/discovery/`:

- `extract.py` — **Layer 1, deterministic.** Reads the FastAPI `openapi.json`, the Next.js
  `app/` tree, and GA4. Emits `feature_inventory.json` (facts only, zero judgment).
- `synthesize.py` — **Layer 2, temperature-0 LLM.** Consumes the inventory, emits
  provenance-tagged `drafts.yaml`. Batched per resource group. Never browses; never
  invents a selector.
- `verify.py` — **Layer 3, one caged Playwright crawl.** Confirms locators, expands
  runtime-only sub-steps, flags test-id gaps. Role-scoped, bounded, write-restricted to
  `drafts.yaml`.

`discover.py` is a thin orchestrator over these three. The human gate merges approved
drafts into the SSOT — discovery **never auto-commits**.

### R2 — Two pipelines, one SSOT
Discovery sits *ahead of* production and communicates only through
`manifest/scenarios.yaml`. Nothing in production reads discovery artifacts directly; the
human-approved SSOT is the sole interface. This keeps production runnable by hand on a
hand-written scenario (as in v0.1) with no discovery present.

### R3 — Lean SSOT; discovery metadata dropped at the gate
`scenarios.yaml` carries the BLUEPRINT §3 schema **plus two operational flags** that
record/seed need: `needs_seed_record` and `destructive`. Everything else that
`drafts.yaml` adds — `provenance`, `bound_via`, `usage_rank`, `source_refs`,
`open_questions`, `discovery_run` — is review scaffolding and is **stripped on merge**.
See §5 for the exact schema and drop-list.

### R4 — One locator priority
`testid > label > role+name`, everywhere. SYNTHESIZER's "testid > i18n_key/label > role"
is the same rule: an `i18n_key` resolves to its localized string and binds as a **label**
locator. Raw CSS is never used.

### R5 — Stack and discovery config are formalized
Discovery targets a **FastAPI + OpenAPI** backend, a **Next.js App Router** frontend, and
**GA4** for usage weighting. This adds configuration the current `Config` does not have
(frontend repo path, API spec URL, GA4 property/window, `extractor_version`). It is
**discovery-only** and namespaced separately from the production `Config` (§6).

### R6 — Artifact locations
- Discovery artifacts → `out/discovery/` (`feature_inventory.json`, `drafts.yaml`) —
  generated, gitignored.
- Production artifacts → `out/<scenario>/<lang>/` (unchanged from today).
- The SSOT (`manifest/scenarios.yaml`) and `assets/` (intro/outro) are committed.

### R7 — Determinism and caching
`inventory_hash` (sha256 over the inventory payload minus `generated_at`) is the CI diff
key: same commits ⇒ same hash ⇒ no re-discovery. Synthesis is cached per resource group
on that group's slice of the hash. Both reuse the existing `cache.py` digest/stamp
pattern. **Known gap:** `choreograph.py`, `record.py`, and `compose.py` are stateless
today; only `script.py` and `narrate.py` cache. Full per-stage cache coverage
("editing one narration line must not re-record unrelated scenarios") is a v0.5
deliverable (`ROADMAP.md`).

---

## 3. Artifact contract index

One row per artifact. Production JSON shapes below are the **actual** keys emitted by the
current code (verified against the stage modules), which are a superset of the BLUEPRINT
sketch (they additionally carry `scenario_id`/`lang`, and `record_log.json` carries a
`video` path).

| Artifact | Owner | Location | Schema source of truth |
|---|---|---|---|
| `feature_inventory.json` | `extract.py` (L1) | `out/discovery/` | `FEATURE_INVENTORY.md` |
| `drafts.yaml` | `synthesize.py` (L2) → enriched by `verify.py` (L3) | `out/discovery/` | `SYNTHESIZER.md` §3 |
| `manifest/scenarios.yaml` | human gate (approved) | repo (committed) | **§5 below** |
| `script.json` | `script.py` | `out/<scenario>/<lang>/` | this table |
| `narrate.json` | `narrate.py` | `out/<scenario>/<lang>/` | this table |
| `timeline.json` | `choreograph.py` | `out/<scenario>/<lang>/` | this table |
| `record_log.json` | `record.py` | `out/<scenario>/<lang>/` | this table |
| `final.mp4` (+ `final.<lang>.vtt` at v0.3) | `compose.py` (+ `subtitle.py`) | `out/<scenario>/<lang>/` | — |

Production JSON shapes (as emitted today):

```jsonc
// script.json
{ "scenario_id": str, "lang": str, "voice": str,
  "steps": [ { "id": str, "intent": str, "narration": str } ] }

// narrate.json
{ "scenario_id": str, "lang": str,
  "steps": [ { "id": str, "wav": "relpath", "duration": float } ] }

// timeline.json   (Phase A — predicted dwell durations)
{ "scenario_id": str, "lang": str, "fps": int, "rec_start_pad": float,
  "steps": [ { "id": str, "audio_duration": float, "step_duration": float } ] }

// record_log.json (Phase B — measured ground truth; pins audio in compose)
{ "scenario_id": str, "lang": str, "fps": int, "rec_start_pad": float,
  "video": "relpath",
  "steps": [ { "id": str, "measured_start": float, "measured_end": float } ] }
```

**The timing invariant (BLUEPRINT §4):** predicted `step_duration` decides *how long to
dwell*; `measured_start` decides *where audio goes*. `compose.py` places each narration
clip at its `measured_start` (`adelay`), never at the predicted offset, so drift cannot
accumulate. Any change to timing must preserve this split.

---

## 4. The discovery layers (decisive summary)

Full detail in DISCOVERY.md / FEATURE_INVENTORY.md / SYNTHESIZER.md; the binding rules:

- **Layer 1 Extract** — deterministic, reproducible, no LLM, no live crawl. Sources:
  OpenAPI `tags`/method+path/`operationId`/`requestBody`/`security`/`responses` (the task
  verbs); Next.js `app/**/page.tsx` tree, route groups, dynamic segments, layouts,
  `middleware.ts` guards, form controls, `data-testid` presence/absence, i18n catalogs
  (the surfaces); GA4 (usage weighting only — ranks, never enumerates). Output is
  facts-only with `*_hint` breadcrumbs and a first-class `testid_gaps[]` list.
- **Layer 2 Synthesize** — the one judgment step. Joins endpoints↔routes on
  `resource_hint`, decomposes features into tasks via the API verbs, sequences steps,
  binds locators to **inventoried controls only**, splits by role, tags **pre-crawl**
  provenance (`code:route+endpoint` | `code:route` | `code:endpoint` | `inferred`; never
  `crawl`). Temperature 0; schema-gated output.
- **Layer 3 Verify** — the only agentic step, caged: role-scoped, read-mostly (mutations
  only against the seeded demo tenant), step-bounded, writes `drafts.yaml` only. Confirms
  locators, expands runtime sub-steps, promotes provenance, resolves/escalates
  `open_questions`.
- **Human gate** — approve / trim / merge `drafts.yaml` → `scenarios.yaml`. Provenance
  turns review into triage, not authoring.

---

## 5. SSOT schema (`manifest/scenarios.yaml`)

Language-neutral. Narration text is **generated** (never written here). Locators are
semantic (R4). The decisive schema:

```yaml
defaults:                         # config seed (see §6)
  base_url, viewport, fps, cursor_travel_s, tail_pad_s, langs, voices
  login:                          # optional auth block consumed by record.py
    route, user_label, pass_label, submit_name, users: { admin: {...}, member: {...} }

scenarios:
  - scenario_id: str              # kebab-case, stable, used in filenames
    title: { bg: str, en: str }
    role: admin | member          # which seeded login to use
    goal: str                     # learning objective; feeds the script LLM
    entry_route: str              # path after base_url
    needs_seed_record: bool       # + survives the gate: task acts on an existing record
    destructive: bool             # + survives the gate: DELETE / irreversible action
    steps:
      - id: str
        intent: str               # the one thing the step teaches → seeds narration
        locator: { testid: ... } | { label: ... } | { role: ..., name: ... }
        action: click | fill | select | hover | wait | navigate
        value: str                # for fill/select/wait/navigate
        emphasis: highlight | zoom | none
        settle_ms: int            # extra dwell after the action
```

**Dropped at the human gate** (live in `drafts.yaml` only, never in the SSOT):
`discovery_run`, `provenance`, `bound_via`, `usage_rank`, `source_refs`, `open_questions`.
The merge tool (v0.4) strips these and keeps `needs_seed_record`/`destructive`.

---

## 6. Configuration surface

**Production `Config`** (`traingen/config.py`, sourced from `defaults:` + env overrides):
`base_url`, `viewport`, `fps`, `cursor_travel_s`, `tail_pad_s`, `langs`, `voices`,
`rec_start_pad_s` (0.5), `headless` (False), `tts_backend` (`offline` | `omnivoice`),
`login`. Env overrides: `TRAINGEN_BASE_URL`, `TRAINGEN_HEADLESS`, `TRAINGEN_TTS`.

**Discovery config (added by R5, namespaced — discovery-only):**

| Key | Meaning |
|---|---|
| `frontend.repo` / `frontend.commit` | Next.js repo path + SHA routes were extracted from |
| `api.spec_url` / `api.commit` | OpenAPI spec URL (e.g. `https://tourism-api.cdsv.dev/openapi.json`) + backend SHA |
| `ga4.property` / `ga4.window_days` | Usage source + lookback for prioritization |
| `extractor_version` / `synthesizer_version` | Bump invalidates cached inventories/drafts |

These belong to the discovery stage, not the production `Config`; production never reads
them.

---

## 7. Platform prerequisites (non-negotiable)

1. **`data-testid` on key interactive elements.** Role/label cover ~80%; icon-only or
   ambiguous controls need stable test-ids. `extract.py`'s `testid_gaps[]` is the
   standing ask list for the platform team.
2. **Seeded, resettable demo tenant on staging.** Training flows mutate data; record
   against a dedicated demo org and reset before each run
   (`scripts/reset_demo_tenant.sh`). **Never record against production** — this binds both
   `record.py` and Layer 3 `verify.py`.

---

## 8. References

| For… | See |
|---|---|
| Timing model, overlays, compose/FFmpeg, narration, subtitles | `BLUEPRINT.md` (§4–§9) |
| Why discovery is layered; provenance; prioritization rubric; CI diff | `DISCOVERY.md` |
| `feature_inventory.json` field-by-field contract + validation rules | `FEATURE_INVENTORY.md` |
| The Layer 2 output schema and the drop-in synthesizer prompt | `SYNTHESIZER.md` |
| The phased build plan and milestones | `ROADMAP.md` |
