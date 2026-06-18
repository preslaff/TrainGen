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
    def press_sequentially(self, v, delay=None): self.calls.append(("type", v, delay))
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


def test_point_is_noop():
    el = FakeEl()
    record.do_action(FakePage([0]), el, {"action": "point"})   # explain-only beat
    assert el.calls == [], "point must not interact (cursor glide + emphasis happen in the run loop)"
    print("OK  do_action: point is a no-op (explains a control without clicking it)")


class _Cfg:
    type_delay_ms = 50


def test_fill_types_visibly_with_delay():
    el = FakeEl()
    record.do_action(FakePage([0]), el, {"action": "fill", "value": "hi there"}, _Cfg())
    assert ("type", "hi there", 50) in el.calls, "with a type delay, fill types char-by-char"

    el2 = FakeEl()                                   # no cfg -> instant fill (e.g. tests/back-compat)
    record.do_action(FakePage([0]), el2, {"action": "fill", "value": "x"})
    assert ("fill", "x") in el2.calls
    print("OK  do_action: visible typing when type_delay_ms set; instant fill otherwise")


class FakeLoc:
    def __init__(self, appears, sink):
        self._appears, self.sink = appears, sink

    @property
    def first(self): return self
    def wait_for(self, state=None, timeout=None):
        if not self._appears:
            raise Exception("timeout waiting for overlay")   # never shows -> skipped
    def click(self, timeout=None): self.sink.append("clicked")


def test_dismiss_overlays(monkeypatch=None):
    orig = record.resolve_locator
    try:
        sink = []
        record.resolve_locator = lambda page, loc: FakeLoc(True, sink)
        record.dismiss_overlays(FakePage([0]), [{"role": "button", "name": "Accept All"}])
        assert sink == ["clicked"], "overlay that appears (even late) is clicked"

        absent = []
        record.resolve_locator = lambda page, loc: FakeLoc(False, absent)
        record.dismiss_overlays(FakePage([0]), [{"role": "button", "name": "Accept All"}], timeout_ms=10)
        assert absent == [], "overlay that never appears is skipped (no error)"

        def boom(page, loc): raise RuntimeError("nope")
        record.resolve_locator = boom
        record.dismiss_overlays(FakePage([0]), [{"role": "button", "name": "x"}])  # must not raise
    finally:
        record.resolve_locator = orig
    print("OK  dismiss_overlays: waits for late overlays, clicks them, skips/ swallows the rest")


class _RoutePage:
    """Records which Playwright getter resolve_locator routes to."""
    def get_by_test_id(self, v): return ("testid", v)
    def get_by_placeholder(self, v): return ("placeholder", v)
    def get_by_label(self, v): return ("label", v)
    def get_by_role(self, role, name=None): return ("role", role, name)
    def locator(self, css): return ("css", css)


def test_resolve_locator_routing():
    p = _RoutePage()
    assert record.resolve_locator(p, {"testid": "x"}) == ("testid", "x")
    assert record.resolve_locator(p, {"placeholder": "Search"}) == ("placeholder", "Search")
    assert record.resolve_locator(p, {"label": "Region"}) == ("label", "Region")
    assert record.resolve_locator(p, {"role": "button", "name": "Zoom in"}) == ("role", "button", "Zoom in")
    # css is the flagged escape hatch for non-semantic controls (map pins)
    assert record.resolve_locator(p, {"css": ".marker-member"}) == ("css", ".marker-member")
    try:
        record.resolve_locator(p, {})
        assert False, "empty locator must raise"
    except ValueError:
        pass
    print("OK  resolve_locator: testid/placeholder/label/role routed; css escape hatch; empty raises")


def test_click_repeat():
    el = FakeEl()
    record.do_action(FakePage([0]), el, {"action": "click", "repeat": 5, "repeat_delay_ms": 1})
    assert el.calls.count(("click",)) == 5, "repeat:5 clicks five times (e.g. zoom-in)"
    el2 = FakeEl()
    record.do_action(FakePage([0]), el2, {"action": "click"})
    assert el2.calls.count(("click",)) == 1, "no repeat -> single click"
    print("OK  do_action: click honours repeat (map zoom), defaults to one")


class _Resp:
    def __init__(self, ok=True, status=200, payload=None):
        self.ok, self.status, self._payload = ok, status, payload or {}
    def json(self): return self._payload


class _ReqPage:
    """Captures request.post calls and records goto navigations (for visit_field)."""
    def __init__(self, resp):
        self._resp, self.posts, self.gotos = resp, [], []
        self.request = self
    def post(self, url, data=None, headers=None):
        self.posts.append((url, data, headers)); return self._resp
    def goto(self, url): self.gotos.append(url)
    def wait_for_load_state(self, state=None): pass
    def evaluate(self, expr): return 0
    def wait_for_timeout(self, ms): pass


class _LoginCfg:
    def __init__(self, login): self.login = login


def test_login_api_modes():
    import os
    os.environ["TRAINGEN_ADMIN_PASSWORD"] = "secret-key"
    # admin: POST resolves {from_env} and sends it; no visit_field -> cookie-only
    p = _ReqPage(_Resp(ok=True))
    record.login(p, "admin", _LoginCfg({"admin": {
        "api": {"route": "/api/admin/login", "json": {"key": {"from_env": "TRAINGEN_ADMIN_PASSWORD"}}}}}))
    assert p.posts == [("/api/admin/login", {"key": "secret-key"}, None)], "POSTs the env-resolved key"
    assert p.gotos == [], "no visit_field -> cookie-only, no navigation"

    # member-style: POST to the backend base, then visit the verify URL built from the token
    os.environ["TRAINGEN_MEMBER_TEST_SECRET"] = "staging-secret"
    os.environ["TRAINGEN_API_BASE_URL"] = "http://localhost:8000"
    p2 = _ReqPage(_Resp(ok=True, payload={"token": "abc"}))
    record.login(p2, "member", _LoginCfg({"member": {"api": {
        "base_env": "TRAINGEN_API_BASE_URL",
        "route": "/api/v1/member/test-session",
        "headers": {"X-Test-Session-Secret": {"from_env": "TRAINGEN_MEMBER_TEST_SECRET"}},
        "json": {"slug": "demo-hotel"}, "visit": {"path": "/member/login/verify?token={token}"}}}}))
    assert p2.posts[0][0] == "http://localhost:8000/api/v1/member/test-session", "POST hits the backend base"
    assert p2.posts[0][2] == {"X-Test-Session-Secret": "staging-secret"}, "header secret resolved"
    assert p2.gotos == ["/member/login/verify?token=abc"], "visits verify URL built from token on our base"
    os.environ.pop("TRAINGEN_API_BASE_URL", None)

    # missing credential -> no POST at all (stay unauthenticated)
    os.environ.pop("TRAINGEN_ADMIN_PASSWORD", None)
    p3 = _ReqPage(_Resp(ok=True))
    record.login(p3, "admin", _LoginCfg({"admin": {
        "api": {"route": "/api/admin/login", "json": {"key": {"from_env": "TRAINGEN_ADMIN_PASSWORD"}}}}}))
    assert p3.posts == [], "missing secret -> never POST a blank credential"

    # auth rejected (401) -> no navigation, returns cleanly (no masquerading session)
    os.environ["TRAINGEN_ADMIN_PASSWORD"] = "bad"
    p4 = _ReqPage(_Resp(ok=False, status=401))
    record.login(p4, "admin", _LoginCfg({"admin": {
        "api": {"route": "/api/admin/login", "json": {"key": {"from_env": "TRAINGEN_ADMIN_PASSWORD"}}}}}))
    assert len(p4.posts) == 1 and p4.gotos == [], "401 surfaced, no session, no further nav"
    os.environ.pop("TRAINGEN_ADMIN_PASSWORD", None)
    os.environ.pop("TRAINGEN_MEMBER_TEST_SECRET", None)
    print("OK  login: api mode resolves env secrets, visits verify_url, bails on missing/invalid creds")


def main() -> int:
    test_settle_returns_when_text_stabilizes()
    test_settle_times_out_when_text_keeps_growing()
    test_do_action_dispatch()
    test_point_is_noop()
    test_fill_types_visibly_with_delay()
    test_dismiss_overlays()
    test_resolve_locator_routing()
    test_click_repeat()
    test_login_api_modes()
    print("\nall record tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
