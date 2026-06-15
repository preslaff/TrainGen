# ROADMAP.md — TrainGen Development Plan

The phased build plan. Architecture and contracts live in `DESIGN.md`; this doc is the
sequence of work. Each milestone lists its **deliverable**, the **files** it creates or
changes, what it **proves**, and what it **depends on**.

## Current state

**v0.1 is built and offline-proven.** The production chain
`script → narrate → choreograph → record → compose` runs end to end; `cache.py` provides
digest/stamp idempotency (script + narrate stages); TTS has an offline (espeak-ng /
silent fallback) and an OmniVoice backend. `tests/test_timing.py` proves the
measured-offset timing model with a synthetic video — **but nothing has yet been recorded
against the real platform.** Not built: overlays, EN path exercised end to end,
`subtitle.py`, intro/outro, the discovery layers, and cache coverage on
choreograph/record/compose.

## Sequencing decision

**Polish-first (BLUEPRINT build order), with Layer-1 Extract pulled forward as a parallel
spike.** Discovery's payoff is *more scenarios* — but feeding an immature pipeline just
yields more unpolished videos. Mature the pipeline to *shippable* on one flow before
scaling the library. The single exception is **Layer 1 Extract**: it is cheap,
deterministic, independent of the rest of discovery, and it emits `testid_gaps[]`, which
the platform team needs lead time to act on. So pull just that one piece forward; the rest
of discovery stays at v0.4.

```
v0.1 (done) ─▶ v0.1-live ─▶ v0.2 ─▶ v0.3 ─▶ v0.4 ─▶ v0.5
                   └────────▶ Extract spike ──────────▲  (parallel; feeds v0.4)
```

---

## v0.1-live — validate against the real platform

**Deliverable:** record `add-partner-profile` (BG) against the real staging demo tenant,
start to finish, producing a synced `final.mp4`.

**Work:**
- Set `TRAINGEN_BASE_URL` to staging; add the `login:` block to `manifest/scenarios.yaml`
  `defaults:` and confirm `record.login()` authenticates as `admin`.
- Confirm every locator/test-id in the scenario resolves against the live UI; file any
  misses as platform test-id asks.
- Implement `scripts/reset_demo_tenant.sh` (currently a stub) for a clean pre-run state.
- Confirm the timing model holds on a *real* capture (not just the synthetic test).

**Files:** `manifest/scenarios.yaml` (login block), `scripts/reset_demo_tenant.sh`.
**Proves:** the model survives contact with reality — the prerequisite for everything else.
**Depends on:** staging demo tenant + seeded credentials.

---

## Extract spike (parallel) — Layer 1 only — IN PROGRESS

**Deliverable:** `feature_inventory.json` + a `testid_gaps[]` list handed to the platform
team. Layer 1 of discovery, standalone.

**Done (first cut):**
- `traingen/discovery/{openapi,nextjs,extract,config}.py`: parse the FastAPI `openapi.json`
  (endpoints, fields, security, response states — exact) and statically parse the Next.js
  `app/` tree (routes, segments, dynamic params, layout chain, controls + `data-testid`
  presence/absence — heuristic). Emits the inventory per the `FEATURE_INVENTORY.md`
  contract with `inventory_hash` and aggregated `testid_gaps[]`. Discovery config keys
  added (`DESIGN.md` §6); `make extract` / `make test`; fixture tests in
  `tests/test_extract.py` pass.

**Remaining for full Layer 1:**
- GA4 `usage[]` weighting (needs API credentials).
- i18n catalog mirroring (`i18n.strings`).
- `middleware.ts` parsing for `role_gate` (currently a prefix heuristic).
- A real TSX parse / Layer 3 crawl to harden control extraction beyond the regex scan.

**Files:** `traingen/discovery/*.py`; output to `out/discovery/feature_inventory.json`.
**Proves:** deterministic enumeration works; surfaces the test-id ask list early.
**Depends on:** read access to the two repos + the OpenAPI spec URL + GA4 property.
**Note:** must stay deterministic (no LLM, no live crawl) — it is the CI diff anchor.

---

## v0.2 — overlays + dual-language

**Deliverable:** demo-mode visual quality (animated cursor, highlight ring, zoom) and the
EN language path exercised end to end.

**Work:**
- `traingen/overlays/{cursor.js,highlight.js,zoom.js}` (skeletons in `BLUEPRINT.md` §5).
- `record.py`: inject overlays via `page.add_init_script`, animate cursor to each target's
  bounding box, apply `emphasis` (highlight/zoom), reset after each step. Fold
  `cursor_travel_s` into the per-step dwell.
- Run `add-partner-profile` for `--lang bg,en`; confirm independent pacing per language.

**Files:** `traingen/overlays/*.js`, `traingen/record.py`.
**Proves:** demo-mode quality + the dual-language flow (record twice, one per language).
**Depends on:** v0.1-live.

---

## v0.3 — subtitles + intro/outro (shippable)

**Deliverable:** a help-center-ready video: soft VTT sidecar per language + branded
intro/outro.

**Work:**
- `traingen/subtitle.py`: aeneas forced alignment per step (lang codes `bul`/`eng`),
  shift each fragment by its `measured_start` (from `record_log.json`), concatenate to one
  `final.<lang>.vtt`. (No transcription — we know the text.)
- `compose.py`: add intro/outro concat (normalize assets to `1920x1080@30 h264/aac` first),
  keep the VTT as a sidecar (no hard-burn for help center).
- `assets/{intro,outro}_{bg,en}.mp4`.
- Wire `subtitle` into the `run.py` chain between record and compose.

**Files:** `traingen/subtitle.py`, `traingen/compose.py`, `run.py`, `assets/*.mp4`.
**Proves:** the output is shippable to the help center.
**Depends on:** v0.2.

---

## v0.4 — full discovery (scale the library) — IN PROGRESS

**Deliverable:** discovery end to end — inventory → drafts → live-verified drafts → human
approval → SSOT — producing many scenarios instead of one hand-written flow.

**Done — Layer 2 Synthesize:**
- `traingen/discovery/synthesize.py` + `llm.py` + `synthesize_cli.py`: per `SYNTHESIZER.md`
  — batched per resource group, schema-gated (structured `output_config.format` JSON, not
  raw YAML), regenerate-on-failure. Consumes the inventory; emits provenance-tagged
  `out/discovery/drafts.yaml`. Semantic validation enforces: every locator binds to an
  inventoried control or is `unbound` + open_question; provenance never says `crawl`;
  4–9 steps; single role; scenario provenance = weakest step. Per-group cache on the
  group's slice hash. Pluggable Claude backend (`claude-opus-4-8`); `make synthesize`;
  fixture tests in `tests/test_synthesize.py` pass offline via a stub backend.
  Note: "temperature 0" in SYNTHESIZER.md predates Opus 4.8 (which removes `temperature`);
  determinism is approached via `effort` + the self-check instead.

**Remaining for v0.4:**
- `traingen/discovery/verify.py`: Layer 3 caged crawl — role-scoped, bounded,
  write-restricted to `drafts.yaml`; confirms locators, expands runtime sub-steps,
  promotes provenance, resolves/escalates `open_questions`. (First real Playwright use.)
- A merge/approve tool: strips draft-only metadata (`DESIGN.md` §5 drop-list), keeps
  `needs_seed_record`/`destructive`, merges approved drafts into `manifest/scenarios.yaml`.
- `traingen/discover.py`: thin orchestrator over extract→synthesize→verify; CLI
  `python run.py --discover --role admin`.
- Refine Layer 1 `resource_hint` for nested APIs (`/admin/leads` → `leads`, not `admin`) so
  synthesis groups are feature-sized, not one giant `admin` group.

**Files:** `traingen/discovery/{synthesize,llm,synthesize_cli}.py` (done);
`{verify}.py`, `traingen/discover.py`, the merge tool, `run.py` (`--discover`) (remaining).
**Proves:** the library scales from sources with a strong human-review draft.
**Depends on:** the Extract spike (inventory) + v0.3 (so generated scenarios produce
shippable videos).

---

## v0.5 — cache coverage + CI (the moat)

**Deliverable:** living documentation — videos stay in sync with the product, regenerating
only what changed on each release.

**Work:**
- Close the caching gap: add digest/stamp coverage to `choreograph.py`, `record.py`, and
  `compose.py` (keyed on timeline/record_log/narrate hashes) so editing one narration line
  never re-records unrelated scenarios.
- CI hook on release tags: re-extract inventory at the new commits, diff `inventory_hash`,
  emit changed/added/removed scenarios for re-synthesis + re-approval, then re-record on
  staging only the affected `(scenario, lang)` pairs.

**Files:** `traingen/{choreograph,record,compose}.py` (cache), a CI workflow + a diff tool
over `feature_inventory.json`.
**Proves:** TrainGen is a repeatable release step, not a one-off video shoot.
**Depends on:** v0.4 + the deterministic `inventory_hash` from Extract.

---

## Dependency notes

- **v0.4 Synthesize consumes the Extract-spike artifact** — the spike is not throwaway; it
  is Layer 1 of the final discovery pipeline, just delivered early.
- **v0.5 CI relies on `inventory_hash` being deterministic** — keep `extract.py` free of
  LLM calls and live crawls (per `DESIGN.md` R7).
- Each milestone keeps the prior one runnable: production never depends on discovery
  (DESIGN.md R2), so the hand-written `add-partner-profile` flow stays exercisable
  throughout.
