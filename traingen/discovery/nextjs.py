"""Next.js App Router → routes[] (FEATURE_INVENTORY §4.3). Static, no execution.

Route enumeration (routes, segments, dynamic params, layout chain, requires_seed_record)
is exact. Control extraction is heuristic: a brace-aware scan of each page file for
interactive JSX tags and their data-testid presence/absence. It does NOT follow imported
components, and it favours precision over recall — a control is only reported with an
identity (and only feeds testid_gaps) when it has a clean accessible name: an aria-label,
an i18n `t("key")`, or a `name=` attribute. Buttons whose content is a bare JS expression
are counted for coverage but not emitted as gaps (they would be noise on a dev ask-list).
A real TSX parse / Layer 3 crawl hardens this later.
"""
from __future__ import annotations

import re
from pathlib import Path

_PAGE = re.compile(r"^page\.(tsx|ts|jsx|js)$")
_LAYOUT = re.compile(r"^layout\.(tsx|ts|jsx|js)$")
_ACTION_SEGMENTS = {"new", "edit", "create"}

_ITAGS = ("button", "a", "Link", "input", "select", "textarea")
_TEXT_TAGS = {"button", "a", "link"}
_I18N = re.compile(r"""\bt\(\s*["']([^"']+)["']""")
_EXPR_CHARS = set("{}()<>=`")

_ROLE = {"button": "button", "link": "link", "text_input": "textbox",
         "select": "combobox", "checkbox": "checkbox"}


def _attr(attrs: str, name: str):
    m = re.search(r"\b" + name + r'=[\"\']([^\"\']+)[\"\']', attrs)
    return m.group(1) if m else None


def _param_name(name: str) -> str:
    return name.strip("[]").lstrip(".").rstrip("?")


def _segment_type(name: str, locale_params=()) -> str:
    if name.startswith("(") and name.endswith(")"):
        return "group"
    if name.startswith("[") and name.endswith("]"):
        return "locale" if _param_name(name) in locale_params else "dynamic"
    return "static"


def _clean(s: str | None) -> str:
    """A visible string is usable as a label only if it has no JSX-expression chars."""
    s = (s or "").strip()
    return "" if (not s or any(c in _EXPR_CHARS for c in s)) else s


def _opening_tags(text: str, tag: str):
    """Yield (attrs, end_index) for each `<tag ...>` opening, tolerating arrow
    functions and nested braces in attributes (so `=>` and `onClick={() => x}` don't
    truncate the tag the way a naive `[^>]*` would)."""
    needle, n, i = "<" + tag, len(text), 0
    while True:
        i = text.find(needle, i)
        if i < 0:
            return
        j = i + len(needle)
        if j < n and (text[j].isalnum() or text[j] in "-_"):
            i = j                      # e.g. <article when scanning for <a
            continue
        depth, k = 0, j
        while k < n:
            c = text[k]
            if c == "{":
                depth += 1
            elif c == "}":
                depth = max(0, depth - 1)
            elif c == ">" and depth == 0 and text[k - 1] != "=":
                break
            k += 1
        yield text[j:k], k
        i = k + 1


def _inner_text(text: str, end: int) -> str:
    nxt = text.find("<", end + 1)
    return text[end + 1: nxt] if nxt > 0 else ""


def _ctype(tag: str, attrs: str) -> str:
    if tag in ("a", "link"):
        return "link"
    if tag == "button":
        return "button"
    if tag == "select":
        return "select"
    if tag == "textarea":
        return "text_input"
    itype = _attr(attrs, "type")            # input
    return "button" if itype in ("button", "submit") else \
        "checkbox" if itype == "checkbox" else "text_input"


def _controls(text: str) -> list:
    controls = []
    for tag in _ITAGS:
        low = tag.lower()
        for attrs, end in _opening_tags(text, tag):
            inner = _inner_text(text, end) if low in _TEXT_TAGS else ""
            i18n_m = _I18N.search(attrs) or _I18N.search(inner)
            i18n_key = i18n_m.group(1) if i18n_m else None
            aria = _attr(attrs, "aria-label")
            name_attr = _attr(attrs, "name")
            placeholder = _attr(attrs, "placeholder")
            label = _clean(aria) or _clean(inner) or (i18n_key or "") \
                or (name_attr or "") or _clean(placeholder)
            controls.append({
                "label": label,
                "control_type": _ctype(low, attrs),
                "role": _ROLE.get(_ctype(low, attrs)),
                "testid": _attr(attrs, "data-testid"),
                "name_attr": name_attr,
                "i18n_key": i18n_key,
                "maps_to_field_hint": name_attr,
            })
    return controls


def _layout_chain(app: Path, page_dir: Path) -> list:
    rel = page_dir.relative_to(app)
    dirs = [app] + [app.joinpath(*rel.parts[: i + 1]) for i in range(len(rel.parts))]
    chain = []
    for d in dirs:
        for layout in sorted(d.glob("layout.*")):
            if _LAYOUT.match(layout.name):
                chain.append(str(layout.relative_to(app.parent)))
    return chain


def _route(typed: list) -> str:
    # keep static + real dynamic segments; drop route groups and i18n locale segments
    url = [name for name, t in typed if t in ("static", "dynamic")]
    return "/" + "/".join(url) if url else "/"


def _resource_hint(typed: list) -> str:
    statics = [name for name, t in typed
               if t == "static" and name not in _ACTION_SEGMENTS]
    if statics:
        return statics[-1]
    return typed[0][0] if typed else "root"


def _role_gate(route: str, role_gates: list) -> str:
    for rg in role_gates:
        if route.startswith(rg["prefix"]):
            return rg["role"]
    return "public"


def extract_routes(app_dir, role_gates: list, locale_params=()) -> list:
    app = Path(app_dir)
    routes = []
    for page in sorted(p for p in app.rglob("*") if _PAGE.match(p.name)):
        parts = [p for p in page.parent.relative_to(app).parts if p != "."]
        typed = [(p, _segment_type(p, locale_params)) for p in parts]
        route = _route(typed)
        segments = [{"name": name, "type": t} for name, t in typed]
        dynamic = [_param_name(name) for name, t in typed if t == "dynamic"]
        controls = _controls(page.read_text(encoding="utf-8", errors="ignore"))
        # only nameable controls (clean accessible name) are actionable gaps
        missing = [c["label"] for c in controls if not c["testid"] and c["label"]]
        routes.append({
            "route": route,
            "file": str(page.relative_to(app.parent)),
            "segments": segments,
            "dynamic_params": dynamic,
            "resource_hint": _resource_hint(typed),
            "layout_chain": _layout_chain(app, page.parent),
            "role_gate": _role_gate(route, role_gates),
            "requires_seed_record": bool(dynamic),
            "controls": controls,
            "testid_coverage": {
                "total_controls": len(controls),
                "with_testid": sum(1 for c in controls if c["testid"]),
                "missing": missing,
            },
            "provenance": "next_app_router",
        })
    routes.sort(key=lambda r: r["route"])
    return routes
