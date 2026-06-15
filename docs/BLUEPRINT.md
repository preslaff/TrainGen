# TrainGen — Auto-Generated Video Training Pipeline

**Purpose:** Generate narrated, subtitled MP4 training videos for the tourism platform by driving the *real* UI through Playwright. Manifest-driven, dual-language (BG + EN), regenerable on every release.

**Core principle:** This is **living documentation**, not a video tool. When the platform ships a UI change, re-run the pipeline and every affected video regenerates. Wire it to CI.

---

## 1. Architecture

```
scenarios.yaml (SSOT)
      │
      ▼
┌─────────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐
│ discover.py │──▶│script.py │──▶│narrate.py│──▶│choreograph.py│
│ (LLM draft) │   │(narration│   │(TTS wav  │   │(step timing  │
│  → human    │   │ + steps) │   │ + durat.)│   │  model)      │
│  approval)  │   └──────────┘   └──────────┘   └──────┬───────┘
└─────────────┘                                        │
                                                       ▼
                          ┌──────────┐   ┌───────────┐   ┌──────────┐
                          │record.py │──▶│subtitle.py│──▶│compose.py│──▶ MP4 + VTT
                          │(Playwright│  │ (aeneas   │   │ (FFmpeg) │
                          │ + overlays│  │  align)   │   └──────────┘
                          │ + offsets)│  └───────────┘
                          └──────────┘
```

Orchestrator = custom Python (`run.py`). No n8n.

Each stage is **idempotent and cacheable** — hash the inputs, skip if unchanged. Editing one narration line should not force a full re-record of unrelated scenarios.

---

## 2. Repo structure

```
traingen/
├── manifest/
│   └── scenarios.yaml            # SSOT — hand-edited, LLM-seeded
├── traingen/
│   ├── config.py                 # paths, base URLs, langs, fps
│   ├── discover.py               # crawl app → LLM → draft scenarios
│   ├── script.py                 # scenario → narration (bg+en) + step plan
│   ├── narrate.py                # text → wav clips + durations
│   ├── choreograph.py            # build timeline.json (desired durations)
│   ├── record.py                 # Playwright run + overlay injection + record_log.json
│   ├── subtitle.py               # aeneas forced alignment → SRT/VTT
│   ├── compose.py                # FFmpeg: audio bed + mux + intro/outro
│   └── overlays/
│       ├── cursor.js
│       ├── highlight.js
│       └── zoom.js
├── assets/
│   ├── intro_bg.mp4  intro_en.mp4
│   └── outro_bg.mp4  outro_en.mp4
├── out/
│   └── <scenario>/<lang>/         # wavs, video, logs, final mp4, vtt
├── run.py                         # CLI orchestrator
└── Makefile                       # seed/reset demo tenant, run-all
```

---

## 3. The SSOT — scenarios.yaml

Language-neutral. Defines *intent + targets*, never narration text (that's generated). Locators are **semantic** (role/label/test-id), never brittle CSS.

See `manifest/scenarios.yaml` for the working starter. Schema:

```yaml
scenario_id: string            # kebab-case, stable, used in filenames
title: { bg: string, en: string }
role: admin | member           # which seeded login to use
goal: string                   # plain-language learning objective (feeds script LLM)
entry_route: "/partners/new"   # path after base_url
steps:
  - id: string
    intent: string             # what this step teaches (feeds narration LLM)
    locator:                   # ONE of: role+name, testid, label
      role: button
      name: "Add partner"
    action: click | fill | select | hover | wait | navigate
    value: string              # for fill/select
    emphasis: highlight | zoom | none
    settle_ms: 800             # extra dwell after action for UI to react
```

---

## 4. The timing model (the part that makes it not suck)

Auto-screencasts desync because narration and on-screen action drift apart. Solution = two-phase timing:

**Phase A — predict (choreograph.py).** Narration audio is generated *first*. Each step's on-screen duration must be long enough to contain its narration:

```
step_duration = max(
    audio_duration,
    cursor_travel + action_exec_estimate + settle_ms/1000
) + TAIL_PAD          # TAIL_PAD ≈ 0.4s breathing room
```

Output: `timeline.json` — the recorder reads this to know how long to dwell on each step.

**Phase B — measure (record.py).** The recorder executes each step, dwelling `step_duration`, and logs the **actual** wall-clock start offset of each step relative to recording start:

```json
// record_log.json
{ "fps": 30, "rec_start_pad": 0.5,
  "steps": [ {"id":"open-form","measured_start":0.50,"measured_end":8.62}, ... ] }
```

**compose.py places each narration clip at its `measured_start`** — not at the predicted offset. Drift cannot accumulate because audio is pinned to ground truth. Predicted durations only ever decide *how long to dwell*; measured offsets decide *where audio goes*.

---

## 5. Recording + demo-mode overlays

Overlays are injected DOM nodes, so they appear in any capture method and are frame-accurate.

**record.py skeleton:**

```python
from playwright.sync_api import sync_playwright
import json, time

def record(scenario, lang, timeline, cfg):
    log = {"fps": cfg.fps, "rec_start_pad": 0.5, "steps": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)   # headed: real rendering
        ctx = browser.new_context(
            base_url=cfg.base_url,
            viewport={"width": 1920, "height": 1080},
            record_video_dir=f"out/{scenario['scenario_id']}/{lang}/",
            record_video_size={"width": 1920, "height": 1080},
        )
        page = ctx.new_page()
        for js in ("cursor.js", "highlight.js", "zoom.js"):
            page.add_init_script(path=f"traingen/overlays/{js}")

        login(page, scenario["role"], cfg)             # seeded demo tenant
        page.goto(scenario["entry_route"])
        page.wait_for_load_state("networkidle")

        t0 = time.monotonic()
        page.wait_for_timeout(500)                     # rec_start_pad

        for step, plan in zip(scenario["steps"], timeline["steps"]):
            start = time.monotonic() - t0
            el = resolve_locator(page, step["locator"])
            box = el.bounding_box()

            page.evaluate("(b)=>window.__tg.cursorTo(b)", box)   # animate cursor
            page.wait_for_timeout(int(cfg.cursor_travel*1000))
            if step["emphasis"] == "highlight":
                page.evaluate("(b)=>window.__tg.highlight(b)", box)
            if step["emphasis"] == "zoom":
                page.evaluate("(b)=>window.__tg.zoom(b,1.4)", box)

            do_action(page, el, step)                  # click/fill/etc

            dwell = plan["step_duration"] - (time.monotonic()-t0 - start)
            page.wait_for_timeout(max(0, int(dwell*1000)))
            page.evaluate("()=>window.__tg.reset()")   # clear zoom/highlight

            log["steps"].append({"id": step["id"],
                                 "measured_start": round(start,3),
                                 "measured_end": round(time.monotonic()-t0,3)})
        ctx.close(); browser.close()
    return log
```

**Locator resolution — semantic only:**

```python
def resolve_locator(page, loc):
    if "testid" in loc:  return page.get_by_test_id(loc["testid"])
    if "label"  in loc:  return page.get_by_label(loc["label"])
    return page.get_by_role(loc["role"], name=loc["name"])
```

**overlays/cursor.js:**

```javascript
(() => {
  const c = document.createElement('div');
  c.style.cssText = `position:fixed;width:22px;height:22px;z-index:2147483647;
    pointer-events:none;background:url('data:image/svg+xml;utf8,
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
    <path d="M3 2l7 18 2.5-7.5L20 10z" fill="black" stroke="white" stroke-width="1.5"/>
    </svg>') no-repeat;transition:left .8s cubic-bezier(.4,0,.2,1),
    top .8s cubic-bezier(.4,0,.2,1);left:50%;top:50%;`;
  document.documentElement.appendChild(c);
  window.__tg = window.__tg || {};
  window.__tg.cursorTo = b => { c.style.left=(b.x+b.width/2)+'px';
                                c.style.top=(b.y+b.height/2)+'px'; };
})();
```

**overlays/highlight.js:**

```javascript
(() => {
  let ring;
  window.__tg = window.__tg || {};
  window.__tg.highlight = b => {
    ring = document.createElement('div');
    ring.style.cssText = `position:fixed;z-index:2147483646;pointer-events:none;
      left:${b.x-6}px;top:${b.y-6}px;width:${b.width+12}px;height:${b.height+12}px;
      border:3px solid #ff5a36;border-radius:8px;
      box-shadow:0 0 0 4px rgba(255,90,54,.25);
      animation:tgpulse 1s ease-in-out infinite;`;
    document.documentElement.appendChild(ring);
    if(!document.getElementById('tgkf')){const s=document.createElement('style');
      s.id='tgkf';s.textContent='@keyframes tgpulse{50%{box-shadow:0 0 0 10px rgba(255,90,54,0)}}';
      document.head.appendChild(s);}
  };
  const reset = window.__tg.reset || (()=>{});
  window.__tg.reset = () => { reset(); if(ring){ring.remove();ring=null;} };
})();
```

**overlays/zoom.js** — CSS transform on `<html>` with origin at the element center; cheaper and more accurate than FFmpeg `zoompan`:

```javascript
(() => {
  const root = document.documentElement;
  window.__tg = window.__tg || {};
  window.__tg.zoom = (b, scale=1.4) => {
    root.style.transition='transform .5s ease';
    root.style.transformOrigin=`${b.x+b.width/2}px ${b.y+b.height/2}px`;
    root.style.transform=`scale(${scale})`;
  };
  const reset = window.__tg.reset || (()=>{});
  window.__tg.reset = () => { reset(); root.style.transform='scale(1)'; };
})();
```

> v2 escape hatch: if Playwright's native webm gives variable framerate or quality problems, swap `record.py` to headed Chromium under **Xvfb + `ffmpeg -f x11grab`** at fixed 30fps. The overlay code and timing model are unchanged.

---

## 6. Narration (narrate.py)

`script.py` produces, per step, narration text in **both** languages. `narrate.py` calls your TTS (OmniVoice / XTTS-v2 candidate) → one wav per step per language. Duration via `soundfile` or `ffprobe`. Cache key = `sha256(text+voice+lang)` so unchanged lines never re-synthesize.

```python
import soundfile as sf
def synth(text, lang, voice, out_path):
    tts_generate(text=text, lang=lang, voice=voice, out=out_path)  # your engine
    return sf.info(out_path).duration
```

Keep a fixed voice per language in `config.py` for consistency across the whole video library.

---

## 7. Subtitles (subtitle.py) — forced alignment with aeneas

We know the exact text and the exact audio. Don't transcribe — align.

```python
# per step: align narration text to its wav → word/fragment timings
from aeneas.executetask import ExecuteTask
from aeneas.task import Task

def align(text_path, audio_path, lang):   # lang: "bul" | "eng"
    cfg = f"task_language={lang}|os_task_file_format=json|is_text_type=plain"
    task = Task(config_string=cfg)
    task.audio_file_path_absolute = audio_path
    task.text_file_path_absolute  = text_path
    ExecuteTask(task).execute()
    return task.sync_map.fragments   # [{begin, end, text}, ...]
```

Then shift every fragment by that step's `measured_start` (from `record_log.json`) and concatenate all steps → one `.vtt` per language for the whole scenario. Ship **soft VTT sidecar** for the help-center HTML5 player (no re-encode, switchable BG/EN). Hard-burn only for social cuts.

aeneas language codes: Bulgarian `bul`, English `eng`. CPU-only, runs in seconds.

---

## 8. Compose (compose.py) — FFmpeg

**Step 1 — build one continuous audio track**, placing each step clip at its `measured_start`:

```bash
ffmpeg -i video.webm \
  -i step_00.wav -i step_01.wav -i step_02.wav \
  -filter_complex "\
    [1:a]adelay=500|500[a0];\
    [2:a]adelay=8620|8620[a1];\
    [3:a]adelay=15040|15040[a2];\
    [a0][a1][a2]amix=inputs=3:normalize=0[aout]" \
  -map 0:v -map "[aout]" -c:v libx264 -crf 18 -preset medium \
  -c:a aac -b:a 192k -pix_fmt yuv420p body.mp4
```

- `adelay` value = `measured_start * 1000` ms (per channel, `L|R`).
- `normalize=0` on amix prevents the volume drop you'd otherwise get.
- Transcode video here (webm→h264) so intro/outro concat is clean.

**Step 2 — prepend intro / append outro** (must match res/fps/codec — normalize first if your assets differ):

```bash
printf "file 'assets/intro_%s.mp4'\nfile 'body.mp4'\nfile 'assets/outro_%s.mp4'\n" $LANG $LANG > concat.txt
ffmpeg -f concat -safe 0 -i concat.txt -c copy final.mp4
```

If assets don't match, normalize each to `1920x1080@30 yuv420p h264/aac` first, then concat.

**Step 3 — subtitles:** keep `final.<lang>.vtt` as a sidecar next to `final.<lang>.mp4`. Help-center player loads it as a `<track>`.

---

## 9. Dual-language flow

Manifest is language-neutral. The pipeline runs the full chain **once per language** because BG and EN narration durations differ → different pacing → record twice:

```
out/add-partner-profile/bg/final.mp4 + final.bg.vtt
out/add-partner-profile/en/final.mp4 + final.en.vtt
```

Re-running Playwright is cheap. This guarantees each language is perfectly synced rather than compromising pacing to fit both.

---

## 10. LLM-assisted scenario drafting (discover.py)

Crawl → propose → **human approves** → merge into SSOT. Never auto-commit drafts.

```python
def crawl(page, routes):
    catalog = []
    for r in routes:
        page.goto(r); page.wait_for_load_state("networkidle")
        catalog.append({
            "route": r,
            "a11y": page.accessibility.snapshot(),       # roles + names
            "interactives": page.evaluate("""() =>
                [...document.querySelectorAll('button,a,input,select,[role=button]')]
                  .map(e=>({tag:e.tagName, role:e.getAttribute('role'),
                            name:(e.innerText||e.ariaLabel||e.name||'').trim().slice(0,60),
                            testid:e.getAttribute('data-testid')}))
                  .filter(e=>e.name)"""),
        })
    return catalog
```

Crawl **once per role** (admin, member) so role-gated flows are discovered separately.

**LLM prompt (script-drafting):**

```
You are designing software training scenarios for a tourism platform.
INPUT: a catalog of routes with their accessibility trees and interactive
elements (role, accessible name, data-testid).

Propose 5–8 training scenarios a NEW {role} must learn. For each, output a
scenarios.yaml entry following this schema exactly:
  scenario_id, title{bg,en}, role, goal, entry_route, steps[]
Each step: id, intent, locator (prefer testid > label > role+name),
action, value?, emphasis, settle_ms.

Rules:
- Use ONLY elements present in the catalog. Never invent selectors.
- Order steps as a real user would perform the task end to end.
- intent = the ONE thing the step teaches (used to generate narration later).
- Keep scenarios to 4–9 steps. Split longer flows.
Output valid YAML only.
```

Then `script.py` takes the approved scenario + the step `intent`s and generates the actual BG/EN narration sentences (tone: calm, instructional, second person).

---

## 11. Two hard requirements on the platform side

1. **`data-testid` on key interactive elements.** Role/label locators cover ~80%, but anything ambiguous or icon-only needs a stable test-id. One-time add; it future-proofs every video against copy changes.
2. **Seeded demo tenant + reset.** Training flows mutate data (create partner, capture lead). Record against a dedicated demo org on staging, reset before each run:

   ```makefile
   seed:    ## reset demo tenant to known state
   	./scripts/reset_demo_tenant.sh   # DB snapshot restore or transactional seed
   ```

   Never record against production.

---

## 12. Orchestrator + CLI

```bash
python run.py --scenario add-partner-profile --lang bg,en
python run.py --all --lang bg,en            # full library
python run.py --discover --role admin       # crawl → draft → out/drafts.yaml
```

Pipeline per (scenario, lang): `script → narrate → choreograph → record → subtitle → compose`. Each stage checks its cache hash and skips if inputs unchanged.

---

## 13. Build order (don't boil the ocean)

| Phase | Deliverable | Proves |
|---|---|---|
| **v0.1** | One hand-written scenario, BG only, no overlays, Playwright-native video, narration pinned by measured offsets | The timing model works end to end |
| **v0.2** | Add cursor + highlight + zoom overlays; add EN | Demo-mode quality + dual-language |
| **v0.3** | aeneas subtitles (VTT sidecar) + intro/outro compose | Shippable to help center |
| **v0.4** | `discover.py` LLM drafting + human approval merge | Scale to full library |
| **v0.5** | Cache hashing + CI hook on release tag against staging | Living documentation / the moat |

Ship v0.1 against one real flow before building anything else. If measured-offset audio placement holds sync on a 6-step scenario, the rest is assembly.
