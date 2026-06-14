"""Tiny idempotency helper. Every stage hashes its inputs and skips if the
hash matches a stored stamp and the outputs still exist (BLUEPRINT §1, §12)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def digest(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        if isinstance(p, (dict, list)):
            p = json.dumps(p, sort_keys=True, ensure_ascii=False)
        h.update(str(p).encode("utf-8"))
    return h.hexdigest()


def is_fresh(stamp_path, key: str, outputs) -> bool:
    stamp = Path(stamp_path)
    if not stamp.exists():
        return False
    if any(not Path(o).exists() for o in outputs):
        return False
    return stamp.read_text(encoding="utf-8").strip() == key


def write_stamp(stamp_path, key: str) -> None:
    Path(stamp_path).write_text(key, encoding="utf-8")
