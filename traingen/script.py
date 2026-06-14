"""Stage 1 — script: scenario goal + per-step intent -> narration text.

The SSOT never contains narration (BLUEPRINT §3); it is generated here. v0.1 ships
a deterministic fallback that uses the step `intent` as the narration so the chain
runs offline. v0.4 replaces generate_narration() with the LLM script-drafting call
(BLUEPRINT §6/§10): tone calm, instructional, second person, per-language.
"""
from __future__ import annotations

import json

from . import config
from .cache import digest, is_fresh, write_stamp


def generate_narration(goal: str, step: dict, lang: str) -> str:
    # TODO(v0.4): call the LLM here, conditioned on `goal`, `step["intent"]`, `lang`.
    return step["intent"].strip()


def run(scenario: dict, lang: str, cfg: config.Config) -> dict:
    sid = scenario["scenario_id"]
    ld = config.lang_dir(sid, lang)
    out = ld / "script.json"
    key = digest("script-v1", scenario, lang)
    if is_fresh(ld / "script.hash", key, [out]):
        return json.loads(out.read_text(encoding="utf-8"))

    steps = [
        {
            "id": step["id"],
            "intent": step["intent"],
            "narration": generate_narration(scenario["goal"], step, lang),
        }
        for step in scenario["steps"]
    ]
    doc = {
        "scenario_id": sid,
        "lang": lang,
        "voice": cfg.voices.get(lang, f"voice_{lang}_calm"),
        "steps": steps,
    }
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    write_stamp(ld / "script.hash", key)
    return doc
