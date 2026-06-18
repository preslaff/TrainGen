# MULTIMODAL.md — Visual Understanding & Productization Plan

**Addendum to `DESIGN.md`.** Plans (a) multimodal/visual understanding of the target app —
using screenshots so an LLM comprehends the GUI and binds steps the code/DOM can't describe
— and (b) the path from "documents my app" to "a product that documents other apps." No
implementation here; this is the design + sequenced roadmap to review before building.

Context: across live runs the pipeline works end to end; the quality ceiling is **UI
understanding** (zero `data-testid`s, i18n-key labels, placeholder-named fields, runtime
sub-steps, API-noun ≠ UI-noun). Every real binding failure was an understanding failure.
Vision targets exactly that.

---

## 1. Principles (what constrains the design)

1. **Vision lives only in the non-deterministic layers.** Layer 1 Extract stays
   byte-deterministic (it is the CI diff anchor). Vision belongs in Layer 3 (verify/expand),
   an optional discovery-enrichment pass, and recording QA — where agency already lives.
2. **Locator philosophy = vision understands, the semantic tree provides the durable
   locator (hybrid).** Vision *chooses* the element; we store a DOM/accessibility selector
   (testid › role+name › label). Pixel/coordinate locators are an explicit, fragility-tagged
   escape hatch for genuinely non-semantic UIs (canvas/games), never the default. Rationale
   and worked examples: see the locator discussion that produced this plan.
3. **Reuse the seams we already have.** The pluggable matcher interface
   (`get_matcher`, `HeuristicMatcher`/`LLMMatcher`), the `Driver` protocol, provenance, and
   `.env` config all extend naturally — vision is additive, not a rewrite.
4. **Targeted, not blanket.** Images are token-heavy; vision is a *fallback* (when DOM
   matching fails) or an *opt-in enrichment pass*, cached — never one call per step by default.

---

## 2. The three vision capabilities (priority order)

### C1 — VisionMatcher: bind steps the DOM names badly (the wedge)
A new matcher alongside heuristic/llm. When a step won't resolve, screenshot the page, send
Claude the image + step intent + the DOM control list (each with its bounding box), ask
*which control performs this step*. Fixes icon-only buttons, placeholder-named fields,
data-named rows — the announcements/applications failures. **Lowest risk, highest immediate
value; validates the whole thesis cheaply.**

### C2 — Visual discovery enrichment: framework-agnostic feature comprehension (the product lever)
A crawl pass that screenshots each route and asks *what feature is this, what can a user do,
what's the primary action* — augmenting the inventory with semantics the code can't give
(bridges API-noun↔UI-noun, reads rendered BG/EN instead of i18n keys). **Strategic
importance:** today Layer 1 is locked to FastAPI+**Next.js**; a vision/accessibility crawl is
**framework-agnostic**, so this is what lets TrainGen work on apps we didn't write a parser
for — the precondition for selling it.

### C3 — Visual QA of recordings: catch what the timing model can't
Sample a frame at each step's `measured_start`, screenshot, ask *does the visible state match
the step intent + narration; did the action succeed; is the right element highlighted*. Feeds
the human gate with visual evidence; catches wrong-element/desync bugs structurally invisible
to predict-vs-measure.

---

## 3. The grounding mechanism (vision → durable DOM locator)

The core trick that keeps locators durable while using vision to find elements:

1. `driver.screenshot()` the viewport (track `devicePixelRatio` for pixel→CSS mapping).
2. Send Claude (Opus 4.8, multimodal) the PNG + step intent + DOM candidates (role, name,
   `getBoundingClientRect`). Ask for the chosen candidate index, or a bounding box.
3. `document.elementFromPoint(centerX, centerY)` → the real DOM node under that point.
4. Read that node's attributes → store the **most durable semantic locator** (testid ›
   role+name › label). If nothing stable exists → record a fragile/coords locator AND emit a
   **test-id gap** so the platform can make it durable (the §11 ask, evidence-driven).

So pixels are used only to *identify*; the persisted artifact is a semantic selector that
survives re-layout/restyle on the next release. Opus 4.7+ high-res vision returns
pixel-accurate coordinates, which makes step 3 reliable.

---

## 4. Components to build (and where they plug in)

| Component | Where | Notes |
|---|---|---|
| `AnthropicBackend.complete_vision(system, user, image)` | `traingen/llm.py` | image content block; reused by C1–C3 |
| `VisionMatcher` | `traingen/discovery/verify.py` | new `get_matcher` option `vision`; grounding via `elementFromPoint` |
| `PlaywrightDriver.screenshot()` + control bboxes | `verify.py` | `snapshot()` already returns controls; add `getBoundingClientRect` |
| Visual enrichment pass | `traingen/discovery/` (new, optional) | screenshots → inventory `visual_features`; never feeds L1 hash |
| Visual QA checker | post-`record` (new, optional) | frame sample → verdicts → human gate |
| Config | `.env` | `TRAINGEN_VERIFY_MATCHER=vision`, `TRAINGEN_VISION_MODEL`, enrichment/QA toggles |

**Provenance:** a vision-bound step is `crawl-only` (most fragile tier) → always surfaced for
human review. **Caching:** vision results keyed on `(screenshot hash, step, candidates)` so
re-runs don't re-pay. **Determinism:** none of this touches L1 / `inventory_hash`.

---

## 5. Platform generalization (kept in view, not built yet)

The product ambition means not staying web-locked. The architecture already points the way;
formalize three seams when native is on the table:
- **Driver** (automate): `PlaywrightDriver` (web) → `AppiumDriver` (Windows UIA / Android
  resource-id / iOS / macOS — semantic locators, same hybrid philosophy) → `ComputerUseDriver`
  (Claude computer-use, pure vision+coords, for no-accessibility UIs).
- **Recorder** (capture): browser webm → OS screen capture (gdigrab/scrcpy/x11grab/AVFoundation).
- **Overlay**: DOM injection → **post-composite** cursor/highlight/zoom in FFmpeg using the
  measured offsets + target bboxes (more uniform across platforms).

The production half (script/narrate/choreograph/subtitle/compose + the timing model) is
already platform-agnostic. Vision (C2) is what makes *discovery* platform-agnostic.

---

## 6. Phase 0 — dogfood on PUBLIC tourist flows (the unblock)

The platform is usable anonymously (browse/discover, the **chatbot**, the **itinerary
scheduler**) — **no login, no seeded tenant, no OTP.** So Phase 0 needs none of the auth
work.

**Chosen first flow: the concierge chatbot** — "ask the concierge a travel question." It's a
single screen (input + send + read the reply), public, no wizard, no seeded record — so
VisionMatcher already binds it and there's nothing blocking a complete first video. The
multi-screen apply form and admin CRUD wait for sub-step insertion + seeded data.
- Target the **public** chatbot route — public Next.js route + the concierge endpoints.
- Run discovery (extract public surface → synthesize → verify **with VisionMatcher** →
  human-gate merge), then record (no login) → narrate (OmniVoice BG/EN) → subtitle → compose.
- Output: a real captioned, dual-language MP4 — your deliverable *and* your demo reel.
- **Dynamic-content caveat:** chatbot/scheduler stream responses; recording must wait for the
  reply to settle before dwelling/advancing (a `wait_for`-style settle per step). Handle in
  `record`/`choreograph` (the timing model already separates dwell from measured offsets).
- **Member dashboard:** deferred until you develop a non-OTP (or API-token) login; then the
  same pipeline extends to member/admin flows.

**Second public flow shipped — `explore-map` (interactive Mapbox map).** A real synced BG +
EN captioned video of the `/explore` map: zoom into a town to uncluster pins → click a place
→ read its detail card. Validated live under headless + `--disable-gpu` (SwiftShader WebGL
paints; the "Zoom in" control unclusters canvas symbols into DOM pins). This was the chosen
**locator-fragility stress test**: every control binds semantically (role+name / aria-label)
**except the map pin** — a real `<button>` with only a CSS class, no testid/accessible name.
It uses the new **flagged `css` escape hatch** in `resolve_locator` (§1/§8), and `record.py`
gained a `repeat` field for repeated control clicks (the zoom).
**PLATFORM TEST-ID GAP:** add `data-testid` (e.g. `map-marker`) to `PinMarker` so the pin
binds durably instead of via the css escape hatch.

---

## 7. Sequenced roadmap

| Milestone | Deliverable | Proves | Offline-testable |
|---|---|---|---|
| **M1 — VisionMatcher (C1)** — DONE & VALIDATED | `llm.complete_vision` + `VisionMatcher` (picks among DOM candidates by screenshot, binds the durable semantic locator, `crawl-only` provenance, heuristic fallback) wired into L3 as `verify_matcher=vision`; `PlaywrightDriver.screenshot()` + per-control bounding boxes; `tests/test_vision.py`. **Live result on /partner/apply: 2/7 → 4/7 bound** — vision bound the placeholder-named fields heuristics couldn't (business name "e.g. Hotel Residence Plovdiv", phone "+359…"). Remaining gaps are NOT vision: wizard sub-steps (screen 3 not rendered) and seeded data (empty admin list). | ✅ vision lifts binding on the exact bad-name failures | stub offline ✓; real bbox+screenshot in Chromium ✓; live ✓ |
| **M2 — Phase 0 dogfood: concierge chatbot — DONE** | the **chatbot concierge** flow (single-screen, public, no login/wizard/seed) recorded live → **real synced captioned BG + EN MP4** (~43s each, OmniVoice voice via the LAN `omnivoice_remote` backend, 3 VTT cues each). The dynamic-content settle (`read-answer` waits for the streamed reply) and the measured-offset timing both held. | ✅ end-to-end product works on a real flow | n/a (live, public — no secrets) |
| **M3 — Visual discovery enrichment (C2) — DONE (public; admin/member gated)** | `traingen/discovery/enrich.py` + `enrich_cli.py` (`make enrich`): screenshot-crawls inventory routes role by role, asks Claude vision per page for `{feature_title, summary, user_actions, primary_action, ui_nouns, rendered_language}`, writes the SIDECAR `out/discovery/visual_features.json` (provenance `crawl-only`, **never** the L1 `inventory_hash`). Vision cached on the screenshot hash; banner dismissed + dynamic/`needs-login` routes surfaced, not dropped. **Live-validated on 10 public routes** — read each feature's purpose + primary action from pixels, bridged API-noun↔UI-noun, with no Next.js parser. **Now live-validated across all three surfaces — 43 routes (10 public + 19 admin + 14 member).** Admin authenticates via the API-key POST to `/api/admin/login`; member via the staging test-session seam (POST to the backend → visit the verify URL built from the returned token → `await_cookie: member_session`). Captured real feature semantics behind auth (e.g. admin "Communications Management / New Announcement", member "Business Profile Editor / Save Changes", "QR Code Generator"). Known overlay artifact: the member onboarding tour modal overlays some member pages (→ vision reports "Next"), same class as the cookie banner — dismiss it for a cleaner member pass. `tests/test_enrich.py` + `test_record` login-api tests. | ✅ framework-agnostic feature comprehension on real screenshots, all roles | enrichment logic offline ✓; live public+admin+member crawl ✓ |
| **M4 — Visual QA (C3)** | frame-checks feeding the human gate | catches wrong-element/desync | verdict logic offline |
| **M5 — Curation UI / control plane** | review surface (screenshots + provenance + ship-list) | humans steer, not edit YAML | — |
| **M6 — Native seams (Driver/Recorder/Overlay)** | Appium + computer-use drivers | other platforms | — |

M1 → M2 is the critical path to a shipped video — **now complete: a real BG/EN video is
shipped.** M3 is the productization bet. M5–M6 are product build-out, after value is proven.

---

## 8. Risks & decisions

- **Coordinate fragility** → mitigated by hybrid (semantic locator persisted), coords only as
  flagged escape hatch.
- **Cost/latency** → vision targeted + cached; never default per-step.
- **Hallucination** → vision-bound = `crawl-only` provenance, always human-reviewed.
- **Dynamic content** (chatbot/scheduler) → per-step settle/wait before timing.
- **devicePixelRatio / scroll** → normalize screenshot pixels → CSS px before `elementFromPoint`.
- **Privacy (product)** → screenshots may contain PII; a product needs retention/redaction policy.
- **Adoption friction (product)** → seeded tenant + automatable login remain the gate for
  *mutating/authenticated* flows; vision removes the test-id ask but not these.

---

## 9. What stays unchanged

The matcher interface, provenance model, `.env` config, the timing model, the SSOT schema,
and the entire production half. Vision is an additive perception layer in the agentic tiers —
not a redesign.
