"""Overlay JS tests — load the injected cursor/highlight/zoom scripts in a real headless
Chromium against a tiny page and assert the window.__tg API mutates the DOM. Self-skips
(exit 0) if Playwright or its browser isn't installed, so `make test` stays portable.

    python -m tests.test_overlays
"""
from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

OVERLAYS = Path(__file__).resolve().parent.parent / "traingen" / "overlays"
PAGE = """<!doctype html><html><head></head><body>
  <button id="target" style="position:absolute;left:100px;top:120px;width:80px;height:30px">Go</button>
</body></html>"""
PAGE_URL = "data:text/html," + urllib.parse.quote(PAGE)   # real navigation -> init scripts run


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("SKIP test_overlays: playwright not installed")
        return 0

    try:
        pw = sync_playwright().start()
    except Exception as e:
        print(f"SKIP test_overlays: {e}")
        return 0

    try:
        try:
            browser = pw.chromium.launch(headless=True)
        except Exception as e:
            print(f"SKIP test_overlays: chromium unavailable ({e})")
            return 0

        page = browser.new_context(viewport={"width": 800, "height": 600}).new_page()
        for js in ("cursor.js", "highlight.js", "zoom.js"):
            page.add_init_script(path=str(OVERLAYS / js))
        page.goto(PAGE_URL, wait_until="load")

        box = page.locator("#target").bounding_box()

        # cursor glides to the element centre
        page.evaluate("(b) => window.__tg.cursorTo(b)", box)
        left = page.eval_on_selector("#__tg_cursor", "e => e.style.left")
        assert abs(float(left.rstrip("px")) - (box["x"] + box["width"] / 2)) < 1.0, \
            f"cursor not centred: {left}"

        # highlight ring appears over the element
        page.evaluate("(b) => window.__tg.highlight(b)", box)
        assert page.locator("#__tg_highlight").count() == 1, "highlight ring not drawn"

        # zoom applies a transform on <html>
        page.evaluate("(b) => window.__tg.zoom(b, 1.4)", box)
        transform = page.eval_on_selector("html", "e => e.style.transform")
        assert "scale(1.4)" in transform, f"zoom not applied: {transform!r}"

        # reset clears highlight + zoom (chained across all three overlays)
        page.evaluate("() => window.__tg.reset()")
        assert page.locator("#__tg_highlight").count() == 0, "highlight not cleared"
        assert page.eval_on_selector("html", "e => e.style.transform") == "scale(1)", "zoom not reset"

        browser.close()
        print("OK  overlays: cursor positions, highlight ring draws, zoom transforms, reset clears all")
        return 0
    finally:
        pw.stop()


if __name__ == "__main__":
    sys.exit(main())
