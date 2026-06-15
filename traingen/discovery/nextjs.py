"""Next.js App Router → routes[] (FEATURE_INVENTORY §4.3). Static, no execution.

Route enumeration (routes, segments, dynamic params, layout chain, requires_seed_record)
is exact. Control extraction is a deliberately heuristic regex scan of each page file:
it captures interactive JSX tags and their data-testid presence/absence well enough to
produce testid_coverage and the testid_gaps list, but it does not follow imported
components. Treated as a first-cut signal, refined later (e.g. a real TSX parse / crawl).
"""
from __future__ import annotations

import re
from pathlib import Path

_PAGE = re.compile(r"^page\.(tsx|ts|jsx|js)$")
_LAYOUT = re.compile(r"^layout\.(tsx|ts|jsx|js)$")
_ACTION_SEGMENTS = {"new", "edit", "create"}

_WITH_TEXT = re.compile(r"<(button|a|Link)\b([^>]*)>([^<]{0,120})", re.IGNORECASE | re.DOTALL)
_INPUT_LIKE = re.compile(r"<(input|select|textarea)\b([^>]*?)/?>", re.IGNORECASE | re.DOTALL)

_ROLE = {"button": "button", "link": "link", "text_input": "textbox",
         "select": "combobox", "checkbox": "checkbox"}


def _attr(attrs: str, name: str):
    m = re.search(name + r'=[\"\']([^\"\']+)[\"\']', attrs)
    return m.group(1) if m else None


def _segment_type(name: str) -> str:
    if name.startswith("(") and name.endswith(")"):
        return "group"
    if name.startswith("[") and name.endswith("]"):
        return "dynamic"
    return "static"


def _control(tag: str, attrs: str, text: str | None = None) -> dict:
    tag = tag.lower()
    testid = _attr(attrs, "data-testid")
    aria = _attr(attrs, "aria-label")
    name_attr = _attr(attrs, "name")
    placeholder = _attr(attrs, "placeholder")
    if tag in ("a", "link"):
        ctype = "link"
    elif tag == "button":
        ctype = "button"
    elif tag == "select":
        ctype = "select"
    elif tag == "textarea":
        ctype = "text_input"
    else:  # input
        itype = _attr(attrs, "type")
        ctype = ("button" if itype in ("button", "submit")
                 else "checkbox" if itype == "checkbox" else "text_input")
    label = aria or ((text or "").strip() or name_attr or placeholder or "")
    return {
        "label": label,
        "control_type": ctype,
        "role": _ROLE.get(ctype),
        "testid": testid,
        "name_attr": name_attr,
        "i18n_key": None,
        "maps_to_field_hint": name_attr,
    }


def _controls(text: str) -> list:
    controls = [_control(m.group(1), m.group(2), m.group(3)) for m in _WITH_TEXT.finditer(text)]
    controls += [_control(m.group(1), m.group(2)) for m in _INPUT_LIKE.finditer(text)]
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


def _route(parts: list) -> str:
    url = [p for p in parts if _segment_type(p) != "group"]
    return "/" + "/".join(url) if url else "/"


def _resource_hint(parts: list) -> str:
    statics = [p for p in parts if _segment_type(p) == "static" and p not in _ACTION_SEGMENTS]
    if statics:
        return statics[-1]
    return parts[0] if parts else "root"


def _role_gate(route: str, role_gates: list) -> str:
    for rg in role_gates:
        if route.startswith(rg["prefix"]):
            return rg["role"]
    return "public"


def extract_routes(app_dir, role_gates: list) -> list:
    app = Path(app_dir)
    routes = []
    for page in sorted(p for p in app.rglob("*") if _PAGE.match(p.name)):
        parts = [p for p in page.parent.relative_to(app).parts if p != "."]
        route = _route(parts)
        segments = [{"name": p, "type": _segment_type(p)} for p in parts]
        dynamic = [p.strip("[]").lstrip(".") for p in parts if _segment_type(p) == "dynamic"]
        controls = _controls(page.read_text(encoding="utf-8", errors="ignore"))
        missing = [c["label"] or c["name_attr"] or c["control_type"]
                   for c in controls if not c["testid"]]
        routes.append({
            "route": route,
            "file": str(page.relative_to(app.parent)),
            "segments": segments,
            "dynamic_params": dynamic,
            "resource_hint": _resource_hint(parts),
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
