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

from . import config

OVERLAYS = Path(__file__).parent / "overlays"

# Steps that act on the page, not on a located element (skip cursor/emphasis/box).
_ELEMENTLESS = {"wait", "settle", "navigate"}


def ready(page) -> None:
    """Wait for the document to be ready. We avoid networkidle: apps with streaming/polling
    (e.g. a chat warmup) may never reach it, so networkidle would hang the recorder."""
    try:
        page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass


def dismiss_overlays(page, locators) -> None:
    """Best-effort close of pre-roll overlays (cookie consent, etc.) BEFORE recording timing
    starts — so they never become a taught step and don't blur/obscure the recorded flow.
    Each is a semantic locator; click it only if present and visible; never fail the run."""
    for loc in locators or []:
        try:
            found = resolve_locator(page, loc)
            if found.count() > 0 and found.first.is_visible():
                found.first.click(timeout=2000)
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


def resolve_locator(page, loc: dict):
    """Semantic locators only — never raw CSS (BLUEPRINT §3)."""
    if "testid" in loc:
        return page.get_by_test_id(loc["testid"])
    if "placeholder" in loc:
        return page.get_by_placeholder(loc["placeholder"])
    if "label" in loc:
        return page.get_by_label(loc["label"])
    return page.get_by_role(loc["role"], name=loc["name"])


def do_action(page, el, step: dict) -> None:
    action = step["action"]
    if action == "click":
        el.click()
    elif action == "fill":
        el.fill(step.get("value", ""))
    elif action == "select":
        el.select_option(label=step.get("value"))
    elif action == "hover":
        el.hover()
    elif action == "press":
        el.press(step.get("value", "Enter"))
    elif action == "wait":
        page.wait_for_timeout(int(step.get("value", 500)))
    elif action == "settle":
        settle(page)
    elif action == "navigate":
        page.goto(step.get("value", "/"))
        ready(page)
    else:
        raise ValueError(f"unknown action: {action}")


def login(page, role: str, cfg: config.Config) -> None:
    """Authenticate as `role` against the seeded demo tenant (BLUEPRINT §11). Per-role
    config lives in the manifest defaults `login:` block; secrets come from env vars and
    are NEVER stored in the git-tracked manifest. Each field's locator is semantic
    (testid/placeholder/label/role+name):

        login:
          admin:
            route: "/admin/en/login"
            fields:
              - { locator: { placeholder: "Enter admin key" }, from_env: TRAINGEN_ADMIN_PASSWORD }
            submit: { role: button, name: "Sign In" }

    No config or missing secret for this role => no-op (starts unauthenticated). Never prod.
    """
    import os
    lc = (cfg.login or {}).get(role)
    if not lc:
        return
    page.goto(lc["route"])
    ready(page)
    for f in lc.get("fields", []):
        value = os.environ.get(f["from_env"]) if f.get("from_env") else f.get("value", "")
        if not value:
            return  # missing credential — bail unauthenticated rather than submit a blank form
        resolve_locator(page, f["locator"]).first.fill(value)
    submit = lc.get("submit")
    if submit:
        resolve_locator(page, submit).first.click()
        ready(page)


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
        "steps": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=cfg.headless)
        ctx = browser.new_context(
            base_url=cfg.base_url,
            viewport=cfg.viewport,
            record_video_dir=str(ld),
            record_video_size=cfg.viewport,
        )
        page = ctx.new_page()
        for js in ("cursor.js", "highlight.js", "zoom.js"):     # demo-mode overlays (BLUEPRINT §5)
            page.add_init_script(path=str(OVERLAYS / js))

        login(page, scenario["role"], cfg)
        page.goto(scenario["entry_route"])
        ready(page)
        dismiss_overlays(page, (cfg.dismiss or []) + scenario.get("dismiss", []))

        t0 = time.monotonic()
        page.wait_for_timeout(int(cfg.rec_start_pad_s * 1000))   # rec_start_pad

        for step in scenario["steps"]:
            start = time.monotonic() - t0
            elementless = step.get("action") in _ELEMENTLESS or not step.get("locator")

            if elementless:
                do_action(page, None, step)                      # wait / settle / navigate
            else:
                el = resolve_locator(page, step["locator"]).first
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
                do_action(page, el, step)

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

    log["video"] = str(dst.relative_to(config.OUT))
    (ld / "record_log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    return log
