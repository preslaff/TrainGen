"""Tiny .env loader (no dependency). Reads KEY=VALUE lines from the repo-root .env into
os.environ WITHOUT overriding already-set variables — so a real shell env wins over the
file. Imported for its side effect by traingen/config.py, so every entrypoint (run.py, the
discovery CLIs, tests) picks it up automatically.

All system parameters live here as TRAINGEN_* (+ ANTHROPIC_API_KEY); see .env.example.
Structured blocks (viewport, voices, login) stay in manifest/scenarios.yaml.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _clean_value(val: str) -> str:
    """Unwrap a quoted value, or strip a trailing inline comment from a bare one.

    Quoted values keep everything inside the quotes verbatim (so a `#` in a secret
    survives). Bare values drop an inline comment introduced by whitespace + `#`
    (the dotenv convention) — this is what `.env.example`'s annotated lines need.
    """
    if val[:1] in ("'", '"'):
        quote = val[0]
        end = val.find(quote, 1)
        return val[1:end] if end != -1 else val[1:]
    for sep in (" #", "\t#"):
        idx = val.find(sep)
        if idx != -1:
            val = val[:idx]
    return val.strip()


def load_dotenv(path=ENV_PATH) -> None:
    path = Path(path)
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = _clean_value(val.strip())
        if key:
            os.environ.setdefault(key, val)   # real env wins over the file


load_dotenv()
