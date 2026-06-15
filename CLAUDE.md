# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

TrainGen is an auto-generated, narrated, dual-language (BG + EN) video training pipeline for a tourism platform. It drives the **real** platform UI through Playwright and produces subtitled MP4s. It is **living documentation, not a video editor**: when the platform's UI changes, re-running the pipeline regenerates every affected video. The intended endpoint is a CI hook on release tags.

**Status:** v0.1 scaffolded. The full pipeline exists under `traingen/` (script → narrate → choreograph → record → compose), driven by `run.py`. Overlays, subtitles (`subtitle.py`), intro/outro compose, and LLM discovery (`discover.py`) are **not yet built** — they are v0.2+. **`docs/DESIGN.md` is the authoritative top-level design** (it resolves conflicts across the detail docs and indexes them); `docs/ROADMAP.md` is the phased plan; `docs/BLUEPRINT.md` holds the production-pipeline detail. Read DESIGN.md first when extending. The manifest now lives at `manifest/scenarios.yaml`.

## Commands

- `make install` — pip deps + `playwright install chromium`.
- `make selftest` (or `python -m tests.test_timing`) — **proves the timing model offline**: runs the real script/narrate/choreograph/compose stages against a synthetic video + fabricated `record_log.json`, then ffprobes the result. No platform or browser needed. Run this after touching timing or compose.
- `make run-one` — the v0.1 target: `python run.py --scenario add-partner-profile --lang bg`. Needs a live staging target (set `TRAINGEN_BASE_URL`) and Chromium.
- Env knobs: `TRAINGEN_BASE_URL`, `TRAINGEN_TTS` (`offline` default | `omnivoice`), `TRAINGEN_HEADLESS=1`.

**External deps:** `ffmpeg` (compose) and, for audible offline narration, `espeak-ng` — without it the offline TTS backend emits silent WAVs sized by word count (timing still valid, just no audio). `omnivoice` backend needs `pip install omnivoice torch` and a GPU.

## Pipeline architecture

Per `(scenario, lang)` the chain is:

```
script → narrate → choreograph → record → subtitle → compose
```

- `script.py` — scenario goal + per-step `intent` → narration text in BG and EN, plus a step plan.
- `narrate.py` — narration text → one WAV per step per language (TTS); returns durations. Cache key = `sha256(text+voice+lang)`.
- `choreograph.py` — **Phase A (predict)**: builds `timeline.json`. Each step's on-screen duration = `max(audio_duration, cursor_travel + action_exec + settle_ms) + TAIL_PAD`. This decides *how long to dwell*.
- `record.py` — **Phase B (measure)**: Playwright executes steps, dwelling per `timeline.json`, injecting DOM overlays. Writes `record_log.json` with the **actual** wall-clock `measured_start`/`measured_end` of every step.
- `subtitle.py` — aeneas **forced alignment** (not transcription — we already know the text), shifted by each step's `measured_start`, concatenated to one VTT per language.
- `compose.py` — FFmpeg. Places each narration clip at its `measured_start` via `adelay`, muxes onto video, prepends intro / appends outro.

`run.py` is the CLI orchestrator (no n8n). Every stage is **idempotent and cacheable** — hash inputs, skip if unchanged. Editing one narration line must not force re-recording unrelated scenarios.

## The core invariant (do not break this)

Auto-screencasts desync because predicted timing drifts from actual playback. The fix: **predicted durations only decide how long to dwell; measured offsets decide where audio goes.** `compose.py` pins every narration clip to `record_log.json`'s `measured_start`, never to the predicted `timeline.json` offset. Drift cannot accumulate because audio is anchored to recorded ground truth. Any change to timing logic must preserve this separation.

## scenarios.yaml — the SSOT

Language-neutral. Defines **intent + semantic targets only**. Narration text is *generated* from `goal` + per-step `intent` and must never be hand-written into the manifest.

- **Locator priority: `testid` > `label` > `role+name`. Never raw CSS** (brittle against copy/markup changes).
- `scenario_id` is kebab-case, stable, and used in output filenames — don't rename casually.
- Schema and field meanings are in `docs/BLUEPRINT.md` §3.

## Dual-language

The full chain runs **once per language**. BG and EN narration durations differ → different pacing → record twice. Re-running Playwright is cheap and guarantees each language stays perfectly synced. Output: `out/<scenario>/<lang>/final.mp4` + `final.<lang>.vtt` (soft VTT sidecar for the help-center player; hard-burn only for social cuts).

## Conventions and constraints

- **Recording is headed Chromium** (`headless=False`) for real rendering, at fixed 1920×1080@30fps.
- **Overlays (cursor/highlight/zoom) are injected DOM nodes** (`page.add_init_script`), so they're frame-accurate in any capture. Zoom is a CSS transform on `<html>`, not FFmpeg `zoompan`.
- aeneas language codes: Bulgarian = `bul`, English = `eng`. CPU-only.
- **Never record against production.** Use a seeded demo tenant on staging; reset before each run.
- `discover.py` LLM scenario drafting is **human-approved before merge** — never auto-commit drafts to the SSOT. It must use only elements present in the crawled catalog (never invent selectors), and crawls once per role (admin, member) for role-gated flows.
- Two platform-side prerequisites: stable `data-testid`s on key interactive elements, and a seeded/resettable demo tenant.

## Build order

Follow `docs/BLUEPRINT.md` §13. Ship **v0.1 first**: one hand-written scenario, BG only, no overlays, Playwright-native video, narration pinned by measured offsets. If measured-offset audio placement holds sync on a ~6-step scenario, the rest is assembly. Don't build overlays, EN, subtitles, discovery, or CI until v0.1 proves the timing model.

## CLI

```bash
python run.py --scenario add-partner-profile --lang bg     # implemented (v0.1)
python run.py --all --lang bg,en                           # implemented
python run.py --discover --role admin                      # NOT yet (v0.4)
```
