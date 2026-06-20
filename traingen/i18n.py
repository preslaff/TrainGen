"""i18n catalog access for locale-aware locators.

The SSOT stays language-neutral (BLUEPRINT §3): a locator names a control by its i18n KEY
(e.g. `tour.next`), and at record time we resolve it to the rendered string in the run's
language by reading the app's next-intl message files (`messages/<lang>.json`). This is how
the same scenario records a correct /en AND /bg video — testids are neutral; text controls
resolve per locale instead of hardcoding English.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path


@functools.lru_cache(maxsize=None)
def load_catalog(lang: str, messages_dir: str | None) -> tuple:
    """Load messages/<lang>.json as a flat {dotted_key: string} map (cached). Empty if the
    dir/file is absent — locale-aware locators then simply fall back to their literal value."""
    if not messages_dir:
        return ()
    f = Path(messages_dir) / f"{lang}.json"
    if not f.is_file():
        return ()
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return ()
    flat: dict = {}

    def walk(o, prefix=""):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{prefix}.{k}" if prefix else k)
        elif isinstance(o, str):
            flat[prefix] = o

    walk(data)
    return tuple(flat.items())   # tuple so the lru_cache return stays hashable/immutable


def resolve(lang: str, key: str, messages_dir: str | None) -> str | None:
    """The localized string for a dotted i18n key, or None if unknown."""
    return dict(load_catalog(lang, messages_dir)).get(key)
