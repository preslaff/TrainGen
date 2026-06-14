"""Stage 4 — record (Phase B, measure). Drive the real UI with Playwright,
dwelling per timeline.json, and log the ACTUAL wall-clock start/end offset of each
step relative to recording start. compose.py pins narration to these measured
offsets, so drift cannot accumulate (BLUEPRINT §4, §5).

v0.1: no overlays, Playwright-native webm capture, headed Chromium.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from . import config


def resolve_locator(page, loc: dict):
    """Semantic locators only — never raw CSS (BLUEPRINT §3)."""
    if "testid" in loc:
        return page.get_by_test_id(loc["testid"])
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
    elif action == "wait":
        page.wait_for_timeout(int(step.get("value", 500)))
    elif action == "navigate":
        page.goto(step.get("value", "/"))
    else:
        raise ValueError(f"unknown action: {action}")


def login(page, role: str, cfg: config.Config) -> None:
    """Authenticate as the seeded demo user for `role` against the staging demo
    tenant (BLUEPRINT §11). Configure via a `login:` block in the manifest defaults:

        login:
          route: /login
          user_label: "Email"
          pass_label: "Password"
          submit_name: "Sign in"
          users: { admin: {username: ..., password: ...}, member: {...} }

    If no login block is present this is a no-op and recording starts at entry_route.
    Never record against production.
    """
    lc = cfg.login
    if not lc:
        return
    page.goto(lc["route"])
    page.wait_for_load_state("networkidle")
    user = lc["users"][role]
    page.get_by_label(lc["user_label"]).fill(user["username"])
    page.get_by_label(lc["pass_label"]).fill(user["password"])
    page.get_by_role("button", name=lc["submit_name"]).click()
    page.wait_for_load_state("networkidle")


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

        login(page, scenario["role"], cfg)
        page.goto(scenario["entry_route"])
        page.wait_for_load_state("networkidle")

        t0 = time.monotonic()
        page.wait_for_timeout(int(cfg.rec_start_pad_s * 1000))   # rec_start_pad

        for step in scenario["steps"]:
            start = time.monotonic() - t0
            el = resolve_locator(page, step["locator"])
            el.scroll_into_view_if_needed()
            do_action(page, el, step)

            plan = plan_by_id[step["id"]]
            elapsed = (time.monotonic() - t0) - start
            dwell = plan["step_duration"] - elapsed
            page.wait_for_timeout(max(0, int(dwell * 1000)))

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
