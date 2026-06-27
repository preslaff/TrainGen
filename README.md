# TrainGen

**Auto-generated, narrated, dual-language (BG + EN) video training for the Wonderful Bulgaria tourism platform — and, by design, for systems beyond it.**

TrainGen drives the **real** platform UI through Playwright and produces subtitled MP4 walkthroughs. It is **living documentation, not a video editor**: when the platform's UI changes, re-running the pipeline regenerates every affected video. The intended endpoint is a CI hook on release tags.

```
script → narrate → choreograph → record → subtitle → compose
```

Each `(scenario, language)` pair runs the full chain once. The narration is spoken (TTS), the cursor glides and highlights/zooms on the controls it talks about, subtitles are forced-aligned, and the finished clip is muxed with the recorded screen capture. Output lands at `out/<scenario>/<lang>/final.mp4` plus a `final.<lang>.vtt` sidecar.

---

## Why it exists

Hand-made screencasts rot the moment the UI shifts, and re-recording them by hand is expensive. TrainGen treats training videos as a build artifact derived from a language-neutral source of truth (`manifest/scenarios.yaml`): change a scenario or ship a UI change, re-run the pipeline, and the video catches up. The same source feeds **discovery** — a layered crawler that proposes new scenarios from the platform's own OpenAPI + frontend.

## Built to travel to other systems

TrainGen began as the trainer for one platform, but the architecture deliberately keeps the system-specific knowledge at the edges so the engine can be pointed at **other applications**:

- **One language-neutral SSOT.** Scenarios describe *intent + semantic targets*, never literal pages or rendered strings. Routes carry no locale; locators name controls by accessibility role / i18n key. Swapping the target app means swapping the manifest and the catalog, not the engine.
- **Everything is configuration.** Target URL, browser args, TTS backend, message catalog, voices, credentials — all `TRAINGEN_*` vars in `.env` or structured manifest blocks. No target-specific constants are baked into the pipeline.
- **Pluggable seams, not hard-coded paths.** TTS backends (`offline` / `omnivoice` / `omnivoice_remote`), the discovery LLM backend, the `Driver` protocol, and the locator-matcher interface are all swappable implementations behind small contracts — so a new app, a new voice engine, or a new model is an additive plug, not a rewrite.
- **The framework lock lives in exactly one place.** Today's deterministic extractor parses FastAPI OpenAPI + Next.js; the **multimodal layer below is what lifts that lock** for apps we didn't write a parser for. Discovery's drafts are written *only* from a crawled catalog, so the engine never invents knowledge specific to one product.

The endgame, sketched in `docs/MULTIMODAL.md`, is the step from *"documents my app"* to *"a product that documents other apps."*

## Hardening UI decoding with a multimodal approach

Across live runs, the pipeline works end to end; the quality ceiling is **UI understanding** — zero `data-testid`s, i18n-key labels, placeholder-named fields, runtime sub-steps, and API-nouns that don't match UI-nouns. Every real binding failure was an *understanding* failure. So TrainGen adds vision exactly where understanding is needed, under strict principles:

1. **Vision lives only in the non-deterministic layers.** Layer 1 extraction stays byte-deterministic — it is the CI diff anchor. Vision belongs in verification/expansion, an optional enrichment pass, and recording QA, where agency already lives.
2. **Hybrid locators: vision *understands*, the semantic tree *provides the durable locator*.** When a step won't resolve from code, the crawl screenshots the page and asks Claude *which control performs this step* — then binds to that control's **DOM/accessibility selector** (`testid` › `role`+`name` › `label` › `title` › `css` escape hatch). Pixels stay durable because the stored locator is semantic; coordinate locators are a fragility-tagged escape hatch for genuinely non-semantic UIs (canvas/games), never the default.
3. **Targeted, not blanket.** Images are token-heavy, so vision is a *fallback* (DOM matching failed) or an *opt-in enrichment pass* — cached on the screenshot hash, never one call per step by default.

This shows up in code as three capabilities (`traingen/discovery/verify.py`, `enrich.py`):

- **`VisionMatcher` — bind steps the DOM names badly.** The crawl snapshot now includes **icon-only controls with no accessible name** (captured with an icon hint like `lucide-pencil`, row-context text, and a best-effort CSS selector), so Claude can pick them by sight. A `title`/`css` bind is flagged as a `needs-a-data-testid` open question; provenance stays `crawl-only` and becomes deterministic once the platform adds the test-id. Live result: **25 controls found vs 2 from the static scan**, including the announcement-row edit pencil that was previously invisible to the parser.
- **Visual discovery enrichment — framework-agnostic feature comprehension.** A crawl pass screenshots each route and asks *what feature is this, what can a user do, what's the primary action* — reading the rendered UI (and real BG/EN text) instead of i18n keys. Because it reads a screenshot + the accessibility snapshot rather than parsed source, this is what lets TrainGen comprehend apps it has no parser for.
- **Visual QA of recordings — catch what timing can't.** Sample a frame at each step's `measured_start` and ask *does the visible state match the intent + narration, did the action succeed, is the right element highlighted.*

Matchers are selected by config (`HeuristicMatcher` default, `LLMMatcher`, `VisionMatcher` via `verify_matcher=vision`), all sharing one `match(step, controls, screenshot)` contract with heuristic fallback on any error.

## The core invariant

Auto-screencasts desync because *predicted* timing drifts from *actual* playback. TrainGen separates the two:

- **Predicted durations decide only how long to dwell** on each step (`choreograph.py` → `timeline.json`).
- **Measured offsets decide where the audio goes** (`record.py` → `record_log.json`; `compose.py` pins every narration clip to the recorded `measured_start`).

Because audio is anchored to recorded ground truth rather than to predictions, drift cannot accumulate. **Any change to timing logic must preserve this separation.**

## Pipeline stages

| Stage | File | Does |
|---|---|---|
| script | `traingen/script.py` | Scenario goal + per-step `intent` → narration text (BG + EN) + step plan |
| narrate | `traingen/narrate.py` | Narration text → one WAV per step per language (TTS); returns durations |
| choreograph | `traingen/choreograph.py` | **Predict** — builds `timeline.json` (per-step dwell = `max(audio, cursor+action+settle) + tail`) |
| record | `traingen/record.py` | **Measure** — Playwright executes steps, injects cursor/highlight/zoom overlays, writes actual `measured_start`/`measured_end` |
| subtitle | `traingen/subtitle.py` | Per-step VTT sidecar (optional `aeneas` forced alignment), shifted by `measured_start` |
| compose | `traingen/compose.py` | FFmpeg — places each clip at its `measured_start` via `adelay`, muxes onto video, prepends intro / appends outro |

Every stage is **idempotent and cacheable** (`traingen/cache.py`): inputs are hashed, unchanged stages are skipped. Editing one narration line never forces re-recording unrelated scenarios.

Overlays (cursor glide, highlight, zoom) are **injected DOM nodes** (`page.add_init_script`, `traingen/overlays/*.js`), so they're frame-accurate in any capture; zoom is a CSS transform on `<html>`, not an FFmpeg post-effect.

## Deterministic narration

The narration LLM (Claude Opus 4.8) is non-deterministic, so generated text is **frozen in a git-tracked store** `narration/<scenario>.<lang>.json` (step-id → text, hand-editable). First generation auto-saves the store; every later run reuses it **verbatim** with no LLM call, surviving `rm -rf out/`. This keeps the spoken words — and the lexicon an OmniVoice voice is tuned for — stable across runs.

Three regeneration modes (see `run.py`):

- `--regenerate-audio` — re-synthesize audio from the **kept** script and recompose onto the **existing** video (no LLM, no re-record). This is how a server-side OmniVoice-BG stress/lexicon fix reaches finished videos.
- `--regenerate-script` — force fresh narration text (overwrites the store), then re-narrate + re-record (wording/durations change).
- `--recompose` — re-run only subtitle + compose from the cached recording.

## Quick start

```bash
make install        # pip deps + playwright install chromium
make env            # cp .env.example .env  — then edit it
make selftest       # prove the timing model offline (no platform/browser needed)
make run-one        # python run.py --scenario add-partner-profile --lang bg
```

`make selftest` runs the full timing/compose chain against a synthetic video + fabricated `record_log.json` and ffprobes the result — no platform or browser required. Run it after touching timing or compose.

### CLI

```bash
python run.py --scenario add-partner-profile --lang bg     # one scenario, one language
python run.py --all --lang bg,en                           # every scenario, both languages
python run.py --scenario X --lang bg --regenerate-audio    # re-synth audio onto existing video
python run.py --discover --role admin                      # run the discovery chain (no human gate)
```

Running a real recording needs a live staging target (`TRAINGEN_BASE_URL`) and Chromium. **Never record against production** — use a seeded, resettable demo tenant.

## Configuration

All config lives in a repo-root **`.env`** (autoloaded by `traingen/env.py`, no dependency; `make env` seeds it from `.env.example`). Every scalar/secret is a `TRAINGEN_*` var (or `ANTHROPIC_API_KEY`). Precedence: shell env > `.env` > manifest `defaults:` > built-in. `.env` is gitignored.

Structured blocks (`voices`, `login` selectors) stay in `manifest/scenarios.yaml`; login credentials come from `TRAINGEN_<ROLE>_PASSWORD`.

**External deps:** `ffmpeg` (compose) and, for audible offline narration, `espeak-ng` (without it the offline backend emits silent WAVs sized by word count — timing stays valid).

> **GPU note:** recording is Chromium at fixed 1920×1080@30fps. Headed rendering is truest, but headed Chromium can hard-freeze some GPUs (confirmed amdgpu/Polaris display hang). On AMD/older GPUs prefer `TRAINGEN_HEADLESS=1` + `TRAINGEN_BROWSER_ARGS=--disable-gpu,--disable-dev-shm-usage`.

### Bulgarian TTS

For production Bulgarian narration, set `TRAINGEN_TTS=omnivoice_remote`: `traingen/tts.py`'s `RemoteOmniVoiceBackend` POSTs text to an **OmniVoice-BG** LAN server (a fine-tuned Bulgarian OmniVoice with server-side stress correction and deterministic voice cloning). Configure `TRAINGEN_OMNIVOICE_URL` and per-voice references in `TRAINGEN_VOICE_DIR`. The server, the stress engine, and the full TTS design live in the OmniVoice-BG repo (`~/WORK/OmniVoice/OMNIVOICE_BG.md`); this repo holds only the thin client.

## The SSOT — `manifest/scenarios.yaml`

Language-neutral. Defines **intent + semantic targets only** — narration text is *generated*, never hand-written into the manifest.

- **Locator priority:** `testid` > `placeholder`/`label` > `role`+`name` > `title` > `css` (flagged escape hatch). Never raw CSS for semantic controls. `*_key` variants resolve i18n per locale; `nth` disambiguates a repeated accessible name.
- `scenario_id` is kebab-case, stable, and used in output filenames — don't rename casually.
- Schema and field meanings: `docs/BLUEPRINT.md` §3.

27 scenarios across three roles:

- **public (6)** — concierge chatbot, explore map, find partner, plan trip, become partner, platform overview.
- **member (10 + tour)** — onboarding tour, profile, offerings, events, stories, reviews, bookings, analytics, QR codes, marketplace.
- **admin (11)** — applications, members, communications, expos, reviews, itineraries (real mutating actions), plus the guided tour and read-only sections (overview, bookings, leads, marketplace).

### Admin scenarios perform real actions

The `admin-*` scenarios approve applications, create announcements/expos/itineraries, moderate reviews, and edit members. The demo admin key is **org-scoped (org_id=7)** and those flows consume/accumulate rows, so the demo org must be **reset + seeded to a known state before each mutating run**:

```bash
bash scripts/record_admin.sh admin-communications en      # seed + record
bash scripts/record_admin.sh admin-overview en --no-seed  # read-only sections skip the seed
```

`record_admin.sh` applies `scripts/seed_demo_admin_data.sql` (sentinel-scoped, idempotent) then runs the pipeline.

## Dual-language

The full chain runs **once per language** — BG and EN narration durations differ, so pacing differs, so the recording happens twice. The recorded **UI is in the run's language too**: the SSOT stays neutral (`entry_route`/`navigate` carry no locale; `localize_route` inserts it at record time), and locators name controls by i18n **key** which `record.localize_locator` resolves via the app's next-intl catalog (`TRAINGEN_MESSAGES_DIR`). No catalog → falls back to the literal value, so offline runs still work.

## Discovery (proposes what to teach)

A layered crawler that drafts new scenarios from the platform itself — outputs are **human-approved before merge**, never auto-committed to the SSOT, and built only from elements present in the crawled catalog (never invented).

- **Layer 1 — Extract** (`make extract`) → `feature_inventory.json` from OpenAPI (exact) + a Next.js control scan (heuristic). **Byte-deterministic** — it is the CI diff anchor.
- **Layer 2 — Synthesize** (`make synthesize`) → `drafts.yaml` via Claude (structured output, semantic validation, per-group cache).
- **Layer 3 — Verify** (`make verify`) → `drafts.verified.yaml` via a caged Playwright crawl (role-scoped, step-bounded, read-mostly, write-restricted) that resolves locators and flags unresolved ones, with the **agentic vision expansion** described above.
- **Enrich** (`make enrich`) → optional vision pass augmenting the inventory with framework-agnostic feature semantics.
- **Human gate + orchestrator** — `make merge` (dry-run by default; `--apply` writes, preserving the `defaults:` header) and `python run.py --discover [--role R] [--skip-verify]`.

## Repository layout

```
run.py                     CLI orchestrator (no n8n)
manifest/scenarios.yaml    the SSOT (language-neutral scenarios)
narration/                 frozen, git-tracked narration text (step-id → text)
traingen/                  pipeline package
  script/narrate/choreograph/record/subtitle/compose.py
  cache.py env.py config.py llm.py i18n.py tts.py
  overlays/*.js            injected cursor/highlight/zoom DOM
  discovery/               extract / synthesize / verify / merge / enrich (+ vision matchers)
scripts/                   demo-tenant seed + reset + record helpers
docs/                      DESIGN.md (authoritative) + detail docs
tests/                     offline test suites (make test)
assets/                    intro/outro clips, voice references
```

## Documentation

- **`docs/DESIGN.md`** — the authoritative top-level design; read this first when extending. It resolves conflicts across the detail docs and indexes them.
- `docs/MULTIMODAL.md` — the vision / "decode any UI" plan and the productization roadmap.
- `docs/ROADMAP.md` — the phased plan.
- `docs/BLUEPRINT.md` — production-pipeline detail (schema, timing model, overlays, build order).
- `docs/DISCOVERY.md`, `docs/SYNTHESIZER.md`, `docs/FEATURE_INVENTORY.md` — discovery detail.
- `docs/HOW_TO_GUIDE.md` — operational how-to.
- `CLAUDE.md` — working notes / instructions for AI assistants in this repo.

## Status

The v0.1 production chain (script → … → compose) is built and offline-proven. Overlays (v0.2), per-language narration, subtitles + intro/outro composition (v0.3), and the full discovery chain (Layers 1–3 + human gate, including vision-based control binding and enrichment) run end to end as code. Live stages (synthesize, verify, recording) need an API key and a running demo tenant. The CI release loop (v0.5) and runtime sub-step *insertion* are not yet built. The offline test suite (`make test`) is green across 19 suites.

## Tests

```bash
make test       # all offline suites (no platform/browser/API needed)
make selftest   # just the timing-model proof
```
