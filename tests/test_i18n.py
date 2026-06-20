"""Locale-aware locators + routes — offline. Proves the i18n catalog read, the *_key locator
resolution (so a neutral SSOT records /en AND /bg), and route locale insertion/stripping.

    python -m tests.test_i18n
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from traingen import i18n
from traingen import record as r


def _catalog(d: Path):
    (d / "en.json").write_text(json.dumps({
        "tour": {"next": "Next", "finish": "Finish"},
        "viki": {"placeholder": "Ask about Bulgaria..."}}), encoding="utf-8")
    (d / "bg.json").write_text(json.dumps({
        "tour": {"next": "Напред", "finish": "Готово"},
        "viki": {"placeholder": "Попитайте за България..."}}, ensure_ascii=False), encoding="utf-8")


def test_i18n_resolve():
    d = Path(tempfile.mkdtemp())
    _catalog(d)
    i18n.load_catalog.cache_clear()
    assert i18n.resolve("bg", "tour.next", str(d)) == "Напред"
    assert i18n.resolve("en", "tour.next", str(d)) == "Next"
    assert i18n.resolve("bg", "viki.placeholder", str(d)) == "Попитайте за България..."
    assert i18n.resolve("bg", "nope.missing", str(d)) is None
    assert i18n.resolve("bg", "tour.next", None) is None          # no dir -> no resolution
    assert i18n.resolve("bg", "tour.next", str(d / "absent")) is None
    print("OK  i18n: resolves dotted keys per language; missing key/dir -> None")


def test_localize_locator():
    d = Path(tempfile.mkdtemp())
    _catalog(d)
    i18n.load_catalog.cache_clear()
    md = str(d)
    # *_key resolves to the per-language string
    assert r.localize_locator({"role": "button", "name_key": "tour.next"}, "bg", md) == \
        {"role": "button", "name": "Напред"}
    assert r.localize_locator({"placeholder_key": "viki.placeholder"}, "en", md) == \
        {"placeholder": "Ask about Bulgaria..."}
    # plain locators (testid / literal / css) pass through untouched
    assert r.localize_locator({"testid": "x"}, "bg", md) == {"testid": "x"}
    assert r.localize_locator({"role": "button", "name": "Zoom in"}, "bg", md) == \
        {"role": "button", "name": "Zoom in"}
    # unresolved key with a literal fallback keeps the literal
    assert r.localize_locator({"name_key": "nope.x", "name": "Fallback"}, "bg", md)["name"] == "Fallback"
    # no lang -> falls back to the literal (offline / lang-agnostic runs still work)
    assert r.localize_locator({"name_key": "tour.next", "name": "Next"}, None, md)["name"] == "Next"
    print("OK  localize_locator: *_key -> per-lang string; testid/literal/css pass through; fallbacks hold")


def test_localize_route():
    assert r.localize_route("/explore", "bg") == "/bg/explore"
    assert r.localize_route("/explore", "en") == "/en/explore"
    assert r.localize_route("/", "bg") == "/bg"
    assert r.localize_route("/member/dashboard", "bg") == "/member/bg/dashboard"
    # an existing/stale locale is stripped, then the run's lang inserted
    assert r.localize_route("/en/explore", "bg") == "/bg/explore"
    assert r.localize_route("/member/en/dashboard", "en") == "/member/en/dashboard"
    # no lang -> neutral (locale stripped)
    assert r.localize_route("/en/explore", None) == "/explore"
    print("OK  localize_route: inserts run locale (after admin/member scope); strips any stale locale")


def main() -> int:
    test_i18n_resolve()
    test_localize_locator()
    test_localize_route()
    print("\nall i18n tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
