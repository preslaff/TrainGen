"""record.py unit tests — offline, no browser. Cover the dynamic-content `settle` (wait
until text stops growing) and the do_action dispatch (incl. the new `press`/`settle`/
`navigate`). The full Playwright run is exercised live, not here.

    python -m tests.test_record
"""
from __future__ import annotations

import sys
import time

from traingen import record


class FakePage:
    """Returns a scripted sequence of innerText sizes; wait_for_timeout really sleeps so the
    settle()'s wall-clock quiet/timeout logic is exercised."""
    def __init__(self, sizes):
        self.sizes, self.i, self.goto_url = sizes, 0, None

    def evaluate(self, expr):
        v = self.sizes[min(self.i, len(self.sizes) - 1)]
        self.i += 1
        return v

    def wait_for_timeout(self, ms):
        time.sleep(ms / 1000.0)

    def wait_for_load_state(self, state=None):
        pass

    def goto(self, url):
        self.goto_url = url


class FakeEl:
    def __init__(self):
        self.calls = []

    def click(self): self.calls.append(("click",))
    def fill(self, v): self.calls.append(("fill", v))
    def press(self, k): self.calls.append(("press", k))
    def select_option(self, label=None): self.calls.append(("select", label))
    def hover(self): self.calls.append(("hover",))


def test_settle_returns_when_text_stabilizes():
    page = FakePage([10, 25, 40, 40, 40, 40, 40])    # grows, then stable at 40
    t0 = time.monotonic()
    record.settle(page, quiet_ms=300, timeout_ms=5000)
    assert page.i >= 4, "polled past the point where size stabilized"
    assert time.monotonic() - t0 < 4.0, "returned well before timeout once stable"
    print("OK  settle: returns once the streamed text stops growing")


def test_settle_times_out_when_text_keeps_growing():
    growing = FakePage(list(range(0, 1000, 10)))     # never stabilizes
    t0 = time.monotonic()
    record.settle(growing, quiet_ms=300, timeout_ms=600)
    assert 0.5 < time.monotonic() - t0 < 1.5, "bounded by timeout, did not hang"
    print("OK  settle: bounded by timeout when content never settles")


def test_do_action_dispatch():
    el = FakeEl()
    record.do_action(FakePage([0]), el, {"action": "press", "value": "Enter"})
    record.do_action(FakePage([0]), el, {"action": "fill", "value": "hi"})
    record.do_action(FakePage([0]), el, {"action": "click"})
    assert ("press", "Enter") in el.calls and ("fill", "hi") in el.calls and ("click",) in el.calls

    page = FakePage([0])                              # elementless navigate (el=None)
    record.do_action(page, None, {"action": "navigate", "value": "/en"})
    assert page.goto_url == "/en"

    record.do_action(FakePage([7, 7, 7, 7]), None, {"action": "settle"})  # routes to settle, no el
    print("OK  do_action: press/fill/click on element; navigate+settle are element-less")


class FakeLoc:
    def __init__(self, count, visible, sink):
        self._count, self._visible, self.sink = count, visible, sink

    def count(self): return self._count
    @property
    def first(self): return self
    def is_visible(self): return self._visible
    def click(self, timeout=None): self.sink.append("clicked")


def test_dismiss_overlays(monkeypatch=None):
    orig = record.resolve_locator
    try:
        sink = []
        record.resolve_locator = lambda page, loc: FakeLoc(1, True, sink)
        record.dismiss_overlays(FakePage([0]), [{"role": "button", "name": "Accept All"}])
        assert sink == ["clicked"], "present + visible overlay is clicked"

        absent = []
        record.resolve_locator = lambda page, loc: FakeLoc(0, False, absent)
        record.dismiss_overlays(FakePage([0]), [{"role": "button", "name": "Accept All"}])
        assert absent == [], "absent overlay is skipped (no error)"

        def boom(page, loc): raise RuntimeError("nope")
        record.resolve_locator = boom
        record.dismiss_overlays(FakePage([0]), [{"role": "button", "name": "x"}])  # must not raise
    finally:
        record.resolve_locator = orig
    print("OK  dismiss_overlays: clicks present overlays, skips absent, swallows errors")


def main() -> int:
    test_settle_returns_when_text_stabilizes()
    test_settle_times_out_when_text_keeps_growing()
    test_do_action_dispatch()
    test_dismiss_overlays()
    print("\nall record tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
