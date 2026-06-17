# ROADMAP.md — TrainGen Development Plan

The phased build plan. Architecture and contracts live in `DESIGN.md`; this doc is the
sequence of work. Each milestone lists its **deliverable**, the **files** it creates or
changes, what it **proves**, and what it **depends on**.

## Current state

**v0.1–v0.3 are built; v0.1-live is achieved.** The production chain
`script → narrate → choreograph → record → subtitle → compose` runs end to end and has now
produced a **real, synced, dual-language captioned MP4 against the live platform** — the
public `concierge-chatbot` flow (BG + EN, ~43s, OmniVoice voice via the LAN
`omnivoice_remote` backend, per-step VTT). The measured-offset timing model held on real
capture, not just the synthetic `tests/test_timing.py`. `cache.py` provides digest/stamp
idempotency on the script + narrate stages; TTS has offline (espeak-ng / silent fallback),
in-process OmniVoice, and remote-OmniVoice backends. Overlays, the EN path, `subtitle.py`,
and intro/outro compose are all built. Not built: cache coverage on
choreograph/record/compose, the v0.5 CI loop, and runtime sub-step insertion in discovery.

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

> **Revised target (see `docs/MULTIMODAL.md`):** dogfood Phase 0 on **public tourist flows**
> (browse, chatbot, itinerary scheduler) — anonymous, **no login/tenant/OTP** — so the first
> real video doesn't wait on auth. Multimodal understanding (vision) is planned as the
> binding + framework-agnostic-discovery layer and the path to productizing TrainGen.

## v0.1-live — validate against the real platform — DONE (public flow)

**Deliverable:** a real synced `final.mp4` for a **public** flow (no auth); the
`add-partner-profile`/member flows follow once a non-OTP login exists.

**Done:** `concierge-chatbot` recorded live in BG + EN — synced, captioned, OmniVoice voice;
the timing model survived real capture. Achieved via MULTIMODAL.md M2 (Phase 0 dogfood).
The `add-partner-profile`/member flows still wait on a non-OTP login + seeded tenant.

**Work (original, for the authenticated flows):**
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

## v0.2 — overlays + dual-language — DONE (overlays)

**Deliverable:** demo-mode visual quality (animated cursor, highlight ring, zoom) and the
EN language path exercised end to end.

**Done:**
- `traingen/overlays/{cursor,highlight,zoom}.js`: DOM-node overlays (BLUEPRINT §5).
  Lazily read `documentElement` (init scripts run at document_start before it exists — a
  bug the real-browser test caught).
- `record.py`: injects the three overlays via `page.add_init_script`, glides the cursor to
  each target's bounding box (waits `cursor_travel_s`), applies `emphasis` highlight/zoom,
  runs the action, then `reset()`s.
- `tests/test_overlays.py`: drives the overlay JS in headless Chromium (cursor positions,
  ring draws, zoom transforms, reset clears); self-skips where Playwright/Chromium absent
  so `make test` stays portable. All seven suites pass.
- EN path: the pipeline runs per language (`--lang bg,en`) with independent pacing, AND
  narration text is now genuinely per-language — `script.py` calls Claude
  (`AnthropicNarrator`, one call per scenario/lang, calm/instructional/second-person in the
  target language) via the shared `traingen/llm.py`, falling back to `EchoNarrator` (the
  step intent) when there's no API key so offline runs still work. `tests/test_script.py`.

**Files:** `traingen/overlays/*.js`, `traingen/record.py`, `traingen/script.py`,
`traingen/llm.py`, `tests/{test_overlays,test_script}.py`.
**Proves:** demo-mode quality + the dual-language flow (record twice, one per language).
**Depends on:** v0.1-live.

---

## v0.3 — subtitles + intro/outro (shippable) — DONE

**Deliverable:** a help-center-ready video: soft VTT sidecar per language + branded
intro/outro.

**Done:**
- `traingen/subtitle.py`: per-step VTT cues (default, deterministic — each step's narration
  spans its measured [start,end]; no dependency), with an optional `aeneas` aligner
  (`subtitles: aeneas`, lang codes bul/eng) for finer fragment timing shifted by
  `measured_start`. Emits `final.<lang>.vtt`. `tests/test_subtitle.py`.
- `compose.py`: builds the body (adelay+mux), then if `assets/{intro,outro}_<lang>.mp4`
  exist, normalizes each segment to a canonical 1920x1080@fps h264 / 48k-stereo-aac (keeps
  source audio; synthesizes silence only for video-only bumpers) and concats with the
  demuxer. No bumpers → the body is the final. `tests/test_compose.py` (synthesizes clips
  with ffmpeg).
- `subtitle` wired into `run.py` between record and compose; `assets/README.md` documents
  the bumper naming. VTT is a soft sidecar — not hard-burned.

**Files:** `traingen/subtitle.py`, `traingen/compose.py`, `run.py`, `assets/`,
`tests/{test_subtitle,test_compose}.py`.
**Proves:** the output is shippable to the help center (switchable BG/EN captions + branding).
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

**Done — Layer 3 Verify (cage logic):**
- `traingen/discovery/verify.py` + `verify_cli.py`: role-scoped (one browser context per
  role), step-bounded (`verify_max_steps`, default 12), write-restricted to
  `out/discovery/drafts.verified.yaml`. Per step it resolves the code-derived locator
  against the live DOM and promotes provenance (`code:route+endpoint` →
  `route+endpoint+crawl`, etc.); unresolved/ambiguous locators are flagged as
  `open_questions`, and unconfirmed `code:endpoint`/`inferred` steps are marked
  `drop_candidate`. Scenario provenance recomputed as the weakest step (risk floor).
  Read-mostly: advances the flow on the demo tenant but never runs a destructive final
  step. Cage logic is stub-tested offline (`tests/test_verify.py`); the Playwright driver
  reuses `record.py` (resolve_locator/do_action/login) and is unrun without a live app.

**Done — human gate + orchestrator:**
- `traingen/discovery/merge.py` + `merge_cli.py`: strips draft-only metadata (DESIGN §5
  drop-list), keeps the lean SSOT schema + `needs_seed_record`/`destructive`, upserts
  selected scenarios into `manifest/scenarios.yaml` by id. Dry-run by default; `--apply`
  preserves the `defaults:` header/comments (regenerates only the `scenarios:` block);
  skips `needs_review`/`drop_candidate` drafts unless `--include-unverified`. `make merge`.
- `traingen/discovery/discover.py` + `run.py --discover [--role R] [--skip-verify]`:
  chains extract → synthesize → verify, stops at `drafts.verified.yaml`, points the user
  at the explicit merge step (never auto-commits). `make discover`.
- Stub/monkeypatched offline tests: `tests/test_merge.py`, `tests/test_discover.py`.

**Done — Layer 3 agentic expansion (live control discovery):**
- `verify.py`: when a step's code locator doesn't resolve, the crawl snapshots the page's
  real interactive controls off the rendered DOM and a pluggable matcher binds the step to
  an actual control (provenance `crawl-only`). Sidesteps the app's missing test-ids and the
  static scan's blindness to imported components. Matcher: `HeuristicMatcher` (default,
  offline) or `LLMMatcher` (optional, `verify_matcher: llm`). Config `verify_expand`.
  Live-validated: `/en/partner/apply` snapshot found 25 controls vs 2 from the static scan.

**Remaining for v0.4 (optional):**
- Inserting brand-new sub-steps for runtime-only wizard/modal stages no step predicts
  (expansion currently binds the steps Layer 2 proposed; it doesn't yet invent new ones).

v0.4 runs end to end as code (extract → synthesize → verify+expand → human-gate merge);
the live stages (synthesize, verify) await an API key and a running demo tenant.

**Done — `resource_hint` refinement:** `discovery/resource.py` strips a configurable scope
set (`api`, `v{n}`, `admin`, `member`, `me`, `dashboard`, …) and takes the first remaining
segment, applied identically to endpoints and routes. On the real API this split the
89-endpoint `admin` / 39-endpoint `member` blobs into 43 feature-sized groups (members,
analytics, applications, bookings, leads, …).

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
