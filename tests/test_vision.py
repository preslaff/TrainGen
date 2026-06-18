"""VisionMatcher tests (MULTIMODAL.md M1).

Offline: a stub vision backend stands in for Claude — proves the matcher passes the
screenshot through, picks the model's chosen control, and binds to its DURABLE semantic
locator (vision understands, DOM locates). Plus a real-Chromium smoke that the perception
primitives (per-control bounding boxes + PNG screenshot) actually work; self-skips if
Playwright/Chromium is absent.

    python -m tests.test_vision
"""
from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

from traingen.discovery import verify

CONTROLS = [
    {"role": "button", "name": "×", "testid": None, "box": [10, 10, 20, 20]},          # icon, bad name
    {"role": "button", "name": "Save announcement", "testid": "ann-save", "box": [100, 200, 140, 40]},
]


class StubVision:
    """Returns a fixed index, and asserts the screenshot was passed through."""
    def __init__(self, index):
        self.index = index
        self.got_image = None

    def complete_vision(self, system, user, image, schema):
        self.got_image = image
        return {"index": self.index}


class VDriver:
    def __init__(self, controls, shot=b"PNGDATA"):
        self.controls, self.shot = controls, shot

    def goto(self, r): pass
    def resolve(self, loc): return ("unresolved", 0)     # nothing binds via code
    def snapshot(self): return self.controls
    def screenshot(self): return self.shot
    def advance(self, s): pass
    def close(self): pass


def _scenario():
    return {"scenario_id": "s", "role": "admin", "entry_route": "/x", "destructive": False,
            "provenance": "inferred", "open_questions": [],
            "steps": [{"id": "save", "intent": "Save the announcement", "locator": {},
                       "action": "click", "emphasis": "none", "settle_ms": 0,
                       "provenance": "code:endpoint", "bound_via": "unbound"}]}


def test_vision_binds_chosen_control_via_semantic_locator():
    backend = StubVision(index=1)                         # model "looks" and picks the Save button
    scen = _scenario()
    verify.verify_scenario(scen, VDriver(CONTROLS), max_steps=12,
                           matcher=verify.VisionMatcher(backend))
    st = scen["steps"][0]
    assert backend.got_image == b"PNGDATA", "screenshot passed to the vision backend"
    assert st["bound_via"] == "testid" and st["locator"] == {"testid": "ann-save"}, \
        "bound to the DURABLE semantic locator, not pixels"
    assert st["provenance"] == "crawl-only" and st["verified"]["status"] == "bound_by_crawl"
    print("OK  vision: binds the screenshot-chosen control via its testid (durable, not coords)")


def test_vision_binds_icononly_control_via_escape_hatch():
    # a pen icon button on an announcement row: no name, no testid — only an icon + row context
    icon = {"role": "button", "name": "", "title": "", "icon": "lucide lucide-pencil",
            "near": "EU Tourism Digitalization Grant", "testid": None,
            "css": "button:nth-of-type(3)", "box": [300, 120, 24, 24]}
    scen = _scenario()
    verify.verify_scenario(scen, VDriver([icon, CONTROLS[1]]), max_steps=12,
                           matcher=verify.VisionMatcher(StubVision(index=0)))   # vision picks the pen
    st = scen["steps"][0]
    assert st["bound_via"] == "css" and st["locator"] == {"css": "button:nth-of-type(3)"}, \
        "icon-only control binds via the css escape hatch (vision saw it; no semantic locator exists)"
    assert st["provenance"] == "crawl-only"
    assert any("icon-only" in q and "data-testid" in q for q in scen["open_questions"]), \
        "fragile (icon-only) bind is flagged as a test-id gap"
    print("OK  vision: icon-only control binds via css escape hatch + flags a test-id gap")


def test_vision_falls_back_without_screenshot():
    m = verify.VisionMatcher(StubVision(index=1))
    # no screenshot -> heuristic fallback; intent 'Save the announcement' matches by token
    chosen = m.match({"action": "click", "intent": "Save announcement", "locator": {}},
                     CONTROLS, screenshot=None)
    assert chosen and chosen["testid"] == "ann-save"
    print("OK  vision: falls back to heuristic when no screenshot is available")


def test_real_browser_perception_smoke():
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("SKIP test_vision (browser): playwright not installed")
        return
    try:
        pw = sync_playwright().start()
    except Exception as e:
        print(f"SKIP test_vision (browser): {e}")
        return
    try:
        try:
            b = pw.chromium.launch(headless=True)
        except Exception as e:
            print(f"SKIP test_vision (browser): chromium unavailable ({e})")
            return
        pg = b.new_context(viewport={"width": 400, "height": 300}).new_page()
        page = ('<button id="t" style="position:absolute;left:60px;top:80px;width:90px;'
                'height:32px">Go</button>')
        pg.goto("data:text/html," + urllib.parse.quote(page), wait_until="load")
        box = pg.eval_on_selector("#t", "e => { const r=e.getBoundingClientRect();"
                                  "return [Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)]; }")
        shot = pg.screenshot(type="png")
        assert box == [60, 80, 90, 32], f"bounding box wrong: {box}"
        assert shot[:8] == b"\x89PNG\r\n\x1a\n", "screenshot is not PNG"
        b.close()
        print(f"OK  vision: real Chromium yields control box {box} + PNG screenshot ({len(shot)} bytes)")
    finally:
        pw.stop()


def main() -> int:
    test_vision_binds_chosen_control_via_semantic_locator()
    test_vision_binds_icononly_control_via_escape_hatch()
    test_vision_falls_back_without_screenshot()
    test_real_browser_perception_smoke()
    print("\nall vision tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
