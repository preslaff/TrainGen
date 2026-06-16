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
        val = val.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, val)   # real env wins over the file


load_dotenv()
