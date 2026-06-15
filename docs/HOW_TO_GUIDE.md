# HOW_TO_GUIDE — Working with TrainGen

A practical, task-oriented guide to operating TrainGen. This is a **living document**:
it is updated as each `docs/ROADMAP.md` milestone lands, so it always reflects what the
app can actually do today, not just what is designed.

For the *why* and the architecture, see `docs/DESIGN.md`. For the build sequence, see
`docs/ROADMAP.md`. This guide is the *how*.

## Status legend

Each section is tagged so you know what is real versus planned:

- **[available]** — implemented and usable now.
- **[planned vX.Y]** — designed, not yet built; lands in that ROADMAP milestone.

Current baseline: production chain (offline-proven) + demo-mode overlays (v0.2) + the full
discovery pipeline (extract → synthesize → verify+expand → human-gate merge). Subtitles,
intro/outro, and the CI loop are not yet built.

---

## 1. What TrainGen does (in one minute)

TrainGen generates narrated, dual-language (BG + EN) training videos by driving a target
app's real UI through Playwright. You describe *what to teach* in a manifest of scenarios;
TrainGen records the flow, narrates it, and produces an MP4 (plus subtitles, once v0.3
lands). When the target app changes, you re-run and the affected videos regenerate.

There are two halves:
- **Production** — turns an approved scenario into a video. **[available]** (v0.1).
- **Discovery** — turns a target app's repos into draft scenarios automatically.
  **[planned v0.4]**; until then you author scenarios by hand (Section 5).

---

## 2. Install **[available]**

```bash
make install        # pip deps + Playwright Chromium
```

System tools you also need:
- **ffmpeg** — required for compose (muxing audio onto video).
- **espeak-ng** — optional; gives audible offline narration. Without it, the offline TTS
  backend emits silent WAVs sized by word count (timing is still correct, just no audio).

```bash
# Debian/Ubuntu
sudo apt install ffmpeg espeak-ng
```

---

## 3. Prove it works without a target app **[available]**

Before pointing at any real app, confirm the timing model end to end offline (no browser,
no platform):

```bash
make selftest        # python -m tests.test_timing
```

This runs the real script/narrate/choreograph/compose stages against a synthetic video and
ffprobes the result. A passing run prints the step count, duration, and codecs.

---

## 4. Configure for a target app **[available]**

Configuration comes from the `defaults:` block of `manifest/scenarios.yaml`, with a few
environment overrides.

Key settings in `defaults:`:
- `base_url` — the target app's **staging** URL (never production).
- `viewport`, `fps`, `cursor_travel_s`, `tail_pad_s` — capture/timing knobs.
- `langs` — e.g. `[bg, en]`.
- `voices` — fixed voice per language for library consistency.
- `login:` — optional auth block so the recorder can sign in (see below).

Environment overrides:
- `TRAINGEN_BASE_URL` — override `base_url` per run.
- `TRAINGEN_TTS` — `offline` (default) or `omnivoice`.
- `TRAINGEN_HEADLESS` — `1` to run the browser headless (default headed for real rendering).

**Login block** (add under `defaults:` if the app requires auth):

```yaml
login:
  route: /login
  user_label: "Email"
  pass_label: "Password"
  submit_name: "Sign in"
  users:
    admin:  { username: "...", password: "..." }
    member: { username: "...", password: "..." }
```

If no `login:` block is present, recording starts directly at the scenario's `entry_route`.

**Demo tenant.** Training flows mutate data, so record against a seeded demo tenant and
reset it before each run via `scripts/reset_demo_tenant.sh` (currently a stub — wire it to
your platform). Never record against production.

---

## 5. Author a scenario by hand **[available]**

Until discovery is built (v0.4), you write scenarios into `manifest/scenarios.yaml`. The
schema is the SSOT defined in `docs/DESIGN.md` §5. A scenario is language-neutral and
describes *intent + semantic targets* — never the narration text (that is generated).

```yaml
scenarios:
  - scenario_id: add-partner-profile      # kebab-case, stable, used in filenames
    title: { bg: "...", en: "..." }
    role: admin                           # which seeded login to use
    goal: "What a new user should learn from this flow."
    entry_route: "/admin/partners"        # path after base_url
    steps:
      - id: open-new-form
        intent: "Open the new-partner form from the list"
        locator: { testid: "partners-add-btn" }   # testid > label > role+name
        action: click                              # click|fill|select|hover|wait|navigate
        emphasis: highlight                         # highlight|zoom|none (overlays: v0.2)
        settle_ms: 800
```

Locator rule: prefer `testid`, then `label`, then `role+name`. Never raw CSS. Keep
scenarios to 4–9 steps.

---

## 6. Generate videos **[available]**

```bash
python run.py --scenario add-partner-profile --lang bg        # one scenario, one language
python run.py --scenario add-partner-profile --lang bg,en     # both languages
python run.py --all --lang bg,en                              # the whole manifest
```

The pipeline runs `script → narrate → choreograph → record → compose` per
`(scenario, lang)`. Stages are cached: re-running skips work whose inputs are unchanged
(script and narrate today; full coverage is v0.5).

---

## 7. Find the output **[available]**

Everything lands under `out/<scenario_id>/<lang>/`:

| File | What it is |
|---|---|
| `script.json` | Per-step narration text |
| `audio/step_NN.wav` | TTS clip per step |
| `narrate.json` | Audio paths + measured durations |
| `timeline.json` | Predicted dwell durations |
| `video.webm` | Raw Playwright capture |
| `record_log.json` | Measured per-step offsets (pins the audio) |
| `final.mp4` | The finished video |

`out/` is gitignored.

---

## 8. Troubleshooting **[available]**

- **A locator fails to resolve** — the control's `testid`/`label`/`role+name` does not
  match the live UI. Confirm the element exists and ask the platform team to add a stable
  `data-testid` if it is icon-only or ambiguous.
- **No audio in the video** — `espeak-ng` is not installed and the offline backend wrote
  silent WAVs. Install it, or switch `TRAINGEN_TTS=omnivoice`.
- **compose fails** — check `ffmpeg` is on `PATH`.
- **Login does nothing / starts logged out** — confirm the `login:` block labels match the
  app's form, and that the demo credentials are valid on staging.

---

## 9. Not yet available (coming with the ROADMAP)

These are designed and will get their own sections here as they ship:

- **Sub-step *insertion*** — inventing brand-new sub-steps for runtime-only wizard/modal
  stages no step predicts (`docs/DISCOVERY.md`). **[planned v0.4]**. The full discovery
  chain — extract → synthesize → verify (with live control discovery) → human-gate merge —
  is available; see Sections 10–14.
- **Overlays** — animated cursor, highlight ring, zoom. **[available]** — DOM-node overlays
  in `traingen/overlays/`, injected by `record.py`; the `emphasis` field per step
  (`highlight`/`zoom`) drives them. Validated by `tests/test_overlays.py` in real Chromium.
- **Subtitles** — soft VTT sidecar per language via aeneas. **[planned v0.3]**
- **Intro/outro** — branded bookends in compose. **[planned v0.3]**
- **CI loop** — regenerate only changed videos on a release tag. **[planned v0.5]**

---

## 10. Generate the feature inventory — discovery Layer 1 **[available]**

Layer 1 reads the target app's **OpenAPI spec** and **Next.js `app/` tree** and emits a
deterministic `feature_inventory.json` — the task/route/control facts plus a
`testid_gaps[]` list to hand the platform team. No LLM, no live crawl.

Configure either via the manifest `defaults.discovery:` block (see `manifest/scenarios.yaml`)
or env/flags, then:

```bash
# via env
TRAINGEN_OPENAPI_URL=https://api.example.com/openapi.json \
TRAINGEN_FRONTEND_APP=../frontend/app \
make extract

# or directly, overriding config
python -m traingen.discovery.extract --spec <url|path> --app <next-app-dir>
```

Output goes to `out/discovery/feature_inventory.json` and the command prints the
endpoint/route/gap counts and the `inventory_hash` (the CI diff key — same commits yield
the same hash). Control extraction is a heuristic regex scan of each page file (it does
not follow imported components), so treat `testid_gaps` as a strong signal to confirm, not
gospel. Verify offline with `make test`.

## 11. Draft scenarios from the inventory — discovery Layer 2 **[available]**

Layer 2 turns `feature_inventory.json` into `drafts.yaml`: it groups the inventory by
resource, and for each group asks Claude to reconcile endpoints↔routes, decompose features
into user tasks, sequence steps, and bind each step to an **inventoried** control (never an
invented selector), tagging pre-crawl provenance. Output is schema-constrained and
semantically validated (bindings, provenance, 4–9 steps, single role); invalid output is
regenerated. Results are cached per resource group.

Needs the Anthropic SDK and a key:

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
make synthesize            # reads out/discovery/feature_inventory.json
# tuning: TRAINGEN_SYNTH_MODEL (default claude-opus-4-8), TRAINGEN_SYNTH_EFFORT (default medium)
```

Output is `out/discovery/drafts.yaml` (a `discovery_run` header + provenance-tagged
`drafts[]`). It is **not** the SSOT — a human approves/trims/merges drafts into
`manifest/scenarios.yaml` (the Layer 3 verify + merge step, v0.4). The command prints any
groups that failed validation after retries. Cost scales with the number of resource
groups, so review one group before running the whole inventory.

## 12. Verify drafts against the running app — discovery Layer 3 **[available]**

Layer 3 is the caged crawl: for each draft it opens the running app (one browser context
per role), checks that each step's locator actually resolves in the live DOM, and promotes
provenance (`code:route+endpoint` → `route+endpoint+crawl`, …). Unresolved or ambiguous
locators become `open_questions`; unconfirmed `code:endpoint`/`inferred` steps are marked
`drop_candidate`. It is **read-mostly** (advances the flow on the seeded demo tenant, never
runs a destructive final step), **bounded** (a per-scenario step ceiling), and
**write-restricted** — it emits `out/discovery/drafts.verified.yaml` and never the SSOT.

Needs Playwright + a running, seeded demo tenant (set `TRAINGEN_BASE_URL` and a `login:`
block; reset the tenant first):

```bash
make install            # Playwright + Chromium, if not already
make verify             # reads out/discovery/drafts.yaml -> drafts.verified.yaml
```

It also **discovers controls live**: when a step's locator doesn't resolve, it snapshots the
page's real interactive controls and binds the step to an actual one (provenance
`crawl-only`) — sidestepping missing test-ids and components the static scan can't see.
Matcher is `heuristic` by default; set `TRAINGEN`-config `verify_matcher: llm` for the
LLM matcher. The command lists scenarios that `need review`; a human then merges the
verified drafts (Section 13).

## 13. Merge verified drafts into the SSOT — the human gate **[available]**

Discovery never auto-commits. When you're happy with `drafts.verified.yaml`, merge selected
scenarios into `manifest/scenarios.yaml`:

```bash
make merge                                                   # dry-run: shows what would merge
python -m traingen.discovery.merge_cli --all --apply         # write the SSOT
python -m traingen.discovery.merge_cli --scenario add-partner-profile --apply
```

The merge strips all draft-only metadata (provenance, bound_via, usage_rank, source_refs,
open_questions, verification) down to the lean SSOT schema, keeping `needs_seed_record`/
`destructive`. It upserts by `scenario_id`, **preserves the `defaults:` header and its
comments** (only the `scenarios:` block is regenerated), and skips drafts still flagged
`needs_review` or carrying `drop_candidate` steps unless you pass `--include-unverified`.
Dry-run is the default; `--apply` writes.

## 14. Run discovery end to end **[available]**

```bash
python run.py --discover                 # extract → synthesize → verify
python run.py --discover --role admin    # restrict to admin-gated scenarios
python run.py --discover --skip-verify   # stop after synthesize (no live crawl)
# then review out/discovery/drafts.verified.yaml and run the merge (Section 13)
```

Needs the inputs each layer needs (OpenAPI URL + Next.js path for extract; Anthropic key
for synthesize; Playwright + demo tenant for verify). It stops at the verified drafts and
points you at the explicit merge step.

## Maintenance note

When you implement a ROADMAP milestone, update the matching section here: flip its tag
from **[planned]** to **[available]**, add the new commands/flags, and move anything from
Section 9 into a real section. Keep this guide honest about the current state of the code.
