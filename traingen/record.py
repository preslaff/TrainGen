"""Stage 4 — record (Phase B, measure). Drive the real UI with Playwright,
dwelling per timeline.json, and log the ACTUAL wall-clock start/end offset of each
step relative to recording start. compose.py pins narration to these measured
offsets, so drift cannot accumulate (BLUEPRINT §4, §5).

v0.2: demo-mode overlays (cursor/highlight/zoom) injected as DOM nodes; dual-language.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from . import config, i18n

OVERLAYS = Path(__file__).parent / "overlays"

# Steps that act on the page, not on a located element (skip cursor/emphasis/box).
_ELEMENTLESS = {"wait", "settle", "navigate", "wait_for"}

# Known UI locales (next-intl [locale] segment). Used to strip/insert the locale in routes.
_LOCALES = {"en", "bg", "de", "ro"}
# Locator fields that carry an i18n KEY (resolved per language) -> their concrete counterpart.
_KEY_FIELDS = {"name_key": "name", "placeholder_key": "placeholder",
               "label_key": "label", "title_key": "title"}


def localize_route(route: str, lang: str | None, scopes=("admin", "member")) -> str:
    """Insert the run's locale into a (language-neutral) route, matching the app's layout:
    /explore -> /bg/explore ; /member/dashboard -> /member/bg/dashboard. Any locale already
    present is stripped first, so the SSOT can stay neutral OR carry a stale /en — both work."""
    parts = [p for p in (route or "/").strip("/").split("/") if p]
    if parts and parts[0] in scopes:                       # strip an existing post-scope locale
        if len(parts) > 1 and parts[1] in _LOCALES:
            parts.pop(1)
    elif parts and parts[0] in _LOCALES:                   # strip a leading locale
        parts.pop(0)
    if not lang:
        return "/" + "/".join(parts)
    if parts and parts[0] in scopes:
        return "/" + "/".join([parts[0], lang, *parts[1:]])
    return "/" + "/".join([lang, *parts])


def localize_locator(loc: dict, lang: str | None, messages_dir: str | None) -> dict:
    """Resolve any i18n-key locator field (*_key) to the rendered string for `lang` via the
    app's message catalog, so a language-neutral SSOT records a correct /en AND /bg video.
    Plain locators (testid/css/literal name) pass through unchanged."""
    if not loc or not any(k in loc for k in _KEY_FIELDS):
        return loc
    out = {k: v for k, v in loc.items() if k not in _KEY_FIELDS}
    for kf, base in _KEY_FIELDS.items():
        if kf not in loc:
            continue
        val = i18n.resolve(lang, loc[kf], messages_dir) if lang else None
        if val is not None:
            out[base] = val
        elif base not in out:                # unresolved (no catalog/key): keep the literal if any,
            out[base] = loc[kf]              # else fall back to the key so the failure is visible
    return out


def ready(page) -> None:
    """Wait for the document to be ready. We avoid networkidle: apps with streaming/polling
    (e.g. a chat warmup) may never reach it, so networkidle would hang the recorder."""
    try:
        page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass


def dismiss_overlays(page, locators, timeout_ms: int = 6000, lang=None, messages_dir=None) -> None:
    """Best-effort close of pre-roll overlays (cookie consent, etc.) BEFORE recording timing
    starts — so they never become a taught step and don't blur/obscure the recorded flow.
    Each is a semantic locator; WAIT for it to appear (consent banners often mount a few
    seconds after load), then click. If it never appears, skip; never fail the run."""
    for loc in locators or []:
        try:
            el = resolve_locator(page, loc, lang, messages_dir).first
            el.wait_for(state="visible", timeout=timeout_ms)   # raises if it never shows -> skip
            el.click(timeout=2000)
            page.wait_for_timeout(400)
        except Exception:
            pass


def settle(page, quiet_ms: int = 1000, timeout_ms: int = 15000) -> None:
    """Wait until the visible text stops growing for `quiet_ms` (a streamed reply has
    finished), or `timeout_ms`. Robust where networkidle never fires."""
    import time
    deadline = time.monotonic() + timeout_ms / 1000.0
    last, stable_since = None, None
    while time.monotonic() < deadline:
        try:
            size = page.evaluate("() => document.body ? document.body.innerText.length : 0")
        except Exception:
            return
        now = time.monotonic()
        if size == last:
            if stable_since is not None and (now - stable_since) * 1000 >= quiet_ms:
                return
        else:
            last, stable_since = size, now
        page.wait_for_timeout(200)


def resolve_locator(page, loc: dict, lang=None, messages_dir=None):
    """Locator priority: testid > placeholder > label > role+name (BLUEPRINT §3).

    i18n-key fields (name_key/placeholder_key/label_key/title_key) resolve to the rendered
    string for `lang` first, so the same neutral locator records /en and /bg correctly.

    `css` is a FLAGGED escape hatch for genuinely non-semantic UIs — e.g. Mapbox pins
    that are real DOM nodes but carry only a class, no testid/accessible name
    (MULTIMODAL.md §1/§8). Prefer filing a test-id gap over leaving a css locator.
    """
    loc = localize_locator(loc, lang, messages_dir)
    if "testid" in loc:
        return page.get_by_test_id(loc["testid"])
    if "placeholder" in loc:
        return page.get_by_placeholder(loc["placeholder"])
    if "label" in loc:
        return page.get_by_label(loc["label"])
    if "role" in loc:
        return page.get_by_role(loc["role"], name=loc.get("name"))
    if "title" in loc:
        return page.get_by_title(loc["title"])   # icon-button tooltip (semantic-ish)
    if "css" in loc:
        return page.locator(loc["css"])     # escape hatch — fragility-tagged
    raise ValueError(f"unresolvable locator: {loc}")


def do_action(page, el, step: dict, cfg=None, lang=None) -> None:
    action = step["action"]
    mdir = getattr(cfg, "messages_dir", None)
    scopes = tuple(getattr(cfg, "locale_scopes", ["admin", "member"]))
    if action == "click":
        n = max(1, int(step.get("repeat", 1)))     # e.g. zoom-in N times on a map control
        for i in range(n):
            el.click()
            if i < n - 1:
                page.wait_for_timeout(int(step.get("repeat_delay_ms", 400)))
    elif action == "fill":
        value = step.get("value", "")
        delay = getattr(cfg, "type_delay_ms", 0) or 0
        if value and delay:                       # visible, human-paced typing
            try:
                el.press_sequentially(value, delay=delay)
            except AttributeError:
                el.type(value, delay=delay)       # older Playwright
        else:
            el.fill(value)
    elif action == "select":
        el.select_option(label=step.get("value"))
    elif action == "hover":
        el.hover()
    elif action == "point":
        pass            # explain-only beat: the run loop already glided the cursor + drew the
                        # emphasis; we dwell while narration explains, without interacting
    elif action == "press":
        el.press(step.get("value", "Enter"))
    elif action == "wait":
        page.wait_for_timeout(int(step.get("value", 500)))
    elif action == "wait_for":
        # block until the step's locator is visible — for content that opens late/async (e.g. a
        # tour overlay that races the dwell). Robust whether it opens in 0.1s or several seconds.
        try:
            resolve_locator(page, step["locator"], lang, mdir).first.wait_for(
                state="visible", timeout=int(step.get("timeout_ms", 15000)))
        except Exception:
            pass   # best effort; if it never appears the following steps will simply not bind
    elif action == "settle":
        settle(page)
    elif action == "navigate":
        page.goto(localize_route(step.get("value", "/"), lang, scopes))
        ready(page)
    else:
        raise ValueError(f"unknown action: {action}")


def _resolve_secrets(d: dict) -> dict:
    """Map a {key: value | {from_env: VAR}} dict to concrete values (env-resolved)."""
    import os
    out = {}
    for k, v in (d or {}).items():
        out[k] = os.environ.get(v["from_env"]) if isinstance(v, dict) and v.get("from_env") else v
    return out


def login(page, role: str, cfg: config.Config, lang=None) -> None:
    """Authenticate as `role` against the seeded demo tenant (BLUEPRINT §11). Per-role config
    lives in the manifest defaults `login:` block; secrets come from env vars and are NEVER
    stored in the git-tracked manifest.

    Two modes. An `api:` block (preferred — a gated POST that yields a session; `page.request`
    shares the context cookie jar) handles both the admin cookie-login and the staging member
    test-session seam (POST returns a verify_url we then visit, exercising the real /verify
    path; TrainGen never holds the signing secret). Or a `fields:`/`submit:` UI form with
    semantic locators (testid/placeholder/label/role+name).

        login:
          admin:                       # cookie set by the POST response
            api: { route: "/api/admin/login", json: { key: { from_env: TRAINGEN_ADMIN_PASSWORD } } }
          member:                      # POST to the backend -> visit the verify URL (mints the session)
            api:
              base_env: TRAINGEN_API_BASE_URL    # backend origin (the route lives there, not the frontend)
              route: "/api/v1/member/test-session"
              headers: { X-Test-Session-Secret: { from_env: TRAINGEN_MEMBER_TEST_SECRET } }
              json:    { slug: "demo-hotel" }
              visit:   { path: "/member/login/verify?token={token}" }   # built on OUR frontend base_url
          admin_ui:                    # legacy UI form, still supported
            route: "/admin/en/login"
            fields: [ { locator: { placeholder: "Enter admin key" }, from_env: TRAINGEN_ADMIN_PASSWORD } ]
            submit: { role: button, name: "Sign In" }

    No config or missing secret for this role => no-op (starts unauthenticated). Never prod.
    """
    import os
    lc = (cfg.login or {}).get(role)
    if not lc:
        return

    api = lc.get("api")
    if api:
        body = _resolve_secrets(api.get("json"))
        headers = _resolve_secrets(api.get("headers"))
        base = ""
        if api.get("base_env"):                  # POST to another origin (e.g. the backend API)
            base = os.environ.get(api["base_env"], "")
            if not base:
                print(f"[login] {role}: {api['base_env']} unset; proceeding unauthenticated.")
                return
        if any(v in (None, "") for v in list(body.values()) + list(headers.values())):
            return  # missing credential — stay unauthenticated rather than POST a blank token
        try:
            resp = page.request.post(base + api["route"], data=body, headers=headers or None)
            if not resp.ok:        # surface bad creds — never let a 401 masquerade as a real session
                print(f"[login] {role}: auth POST {api['route']} -> HTTP {resp.status}; "
                      "proceeding UNAUTHENTICATED (check the credential).")
                return
            visit = api.get("visit")
            if visit:    # e.g. member: build the verify URL from the response, on OUR frontend, and
                data = resp.json() or {}    # visit it (the real /verify path mints the session cookie)
                try:
                    url = visit["path"].format(**data)
                except Exception:
                    print(f"[login] {role}: response missing fields for visit path; unauthenticated.")
                    return
                page.goto(url)
                ready(page)
                # the verify page sets the cookie ASYNC (client verify -> set cookie -> redirect);
                # wait for the session cookie before returning, or we navigate away mid-verify.
                want = visit.get("await_cookie")
                if want:
                    for _ in range(int(visit.get("await_timeout_ms", 15000) / 500)):
                        if any(c["name"] == want for c in page.context.cookies()):
                            break
                        page.wait_for_timeout(500)
                    else:
                        print(f"[login] {role}: '{want}' cookie not set after verify; unauthenticated.")
        except Exception as e:
            print(f"[login] {role}: auth failed ({e}); proceeding unauthenticated.")
            return
        return

    page.goto(lc["route"])
    ready(page)
    for f in lc.get("fields", []):
        value = os.environ.get(f["from_env"]) if f.get("from_env") else f.get("value", "")
        if not value:
            return  # missing credential — bail unauthenticated rather than submit a blank form
        resolve_locator(page, f["locator"], lang, getattr(cfg, "messages_dir", None)).first.fill(value)
    submit = lc.get("submit")
    if submit:
        resolve_locator(page, submit, lang, getattr(cfg, "messages_dir", None)).first.click()
        ready(page)


def rec_offset(record_log: dict) -> float:
    """Seconds of video pre-roll (login/goto/dismiss) before step timing's t0. compose +
    subtitle add this to each step's measured offset so narration aligns to the UI, not to
    video frame 0. Uses the value stored at record time; for legacy logs without it, derives
    it as (video duration - last measured_end) ≈ the pre-roll, so old recordings re-compose
    correctly without re-recording."""
    off = record_log.get("rec_offset")
    if off is not None:
        return float(off)
    steps = record_log.get("steps") or []
    if not steps or not record_log.get("video"):
        return 0.0
    try:
        import subprocess
        dur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(config.OUT / record_log["video"])],
            capture_output=True, text=True).stdout.strip())
        return max(0.0, round(dur - max(s["measured_end"] for s in steps), 3))
    except Exception:
        return 0.0


def run(scenario: dict, timeline: dict, cfg: config.Config) -> dict:
    from playwright.sync_api import sync_playwright

    sid, lang = scenario["scenario_id"], timeline["lang"]
    ld = config.lang_dir(sid, lang)
    plan_by_id = {s["id"]: s for s in timeline["steps"]}
    log = {
        "scenario_id": sid,
        "lang": lang,
        "fps": cfg.fps,
        "rec_start_pad": cfg.rec_start_pad_s,
        "rec_offset": 0.0,        # video pre-roll before t0; set below (see rec_offset note)
        "steps": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=cfg.headless, args=cfg.browser_args or [])
        ctx = browser.new_context(
            base_url=cfg.base_url,
            viewport=cfg.viewport,
            record_video_dir=str(ld),
            record_video_size=cfg.viewport,
        )
        page = ctx.new_page()
        t_video = time.monotonic()      # video recording begins ~here (at page creation)
        for js in ("cursor.js", "highlight.js", "zoom.js"):     # demo-mode overlays (BLUEPRINT §5)
            page.add_init_script(path=str(OVERLAYS / js))

        mdir = getattr(cfg, "messages_dir", None)
        scopes = tuple(getattr(cfg, "locale_scopes", ["admin", "member"]))
        login(page, scenario["role"], cfg, lang)
        page.goto(localize_route(scenario["entry_route"], lang, scopes))
        ready(page)
        dismiss_overlays(page, (cfg.dismiss or []) + scenario.get("dismiss", []),
                         lang=lang, messages_dir=mdir)

        t0 = time.monotonic()
        # Pre-roll (login + goto + dismiss) is in the video BEFORE step timing starts. measured_*
        # are relative to t0, but the video's frame 0 is t_video — so compose/subtitle must shift
        # narration by this offset, or audio leads the UI (badly for slow member login). (BLUEPRINT §4)
        rec_offset = round(t0 - t_video, 3)
        page.wait_for_timeout(int(cfg.rec_start_pad_s * 1000))   # rec_start_pad

        for step in scenario["steps"]:
            start = time.monotonic() - t0
            elementless = step.get("action") in _ELEMENTLESS or not step.get("locator")

            if elementless:
                do_action(page, None, step, cfg, lang)           # wait / settle / navigate
            else:
                el = resolve_locator(page, step["locator"], lang, mdir).first
                el.scroll_into_view_if_needed()
                box = el.bounding_box()
                if box:                                          # glide the cursor, then emphasise
                    page.evaluate("(b) => window.__tg && window.__tg.cursorTo(b)", box)
                    page.wait_for_timeout(int(cfg.cursor_travel_s * 1000))
                    emphasis = step.get("emphasis", "none")
                    if emphasis == "highlight":
                        page.evaluate("(b) => window.__tg && window.__tg.highlight(b)", box)
                    elif emphasis == "zoom":
                        page.evaluate("(b) => window.__tg && window.__tg.zoom(b, 1.4)", box)
                do_action(page, el, step, cfg, lang)

            plan = plan_by_id[step["id"]]
            elapsed = (time.monotonic() - t0) - start
            dwell = plan["step_duration"] - elapsed
            page.wait_for_timeout(max(0, int(dwell * 1000)))
            page.evaluate("() => window.__tg && window.__tg.reset()")   # clear highlight/zoom

            log["steps"].append({
                "id": step["id"],
                "measured_start": round(start, 3),
                "measured_end": round(time.monotonic() - t0, 3),
            })

        video = page.video
        ctx.close()                      # finalizes the webm
        dst = ld / "video.webm"
        shutil.move(video.path(), str(dst))
        browser.close()

    log["rec_offset"] = rec_offset
    log["video"] = str(dst.relative_to(config.OUT))
    (ld / "record_log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    return log
