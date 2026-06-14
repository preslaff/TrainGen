"""Stage 3 — choreograph (Phase A, predict). Audio exists first; each step's
on-screen duration must be long enough to contain its narration (BLUEPRINT §4):

    step_duration = max(audio, cursor_travel + action_exec + settle) + TAIL_PAD

Predicted durations only decide *how long to dwell*. Where audio actually goes is
decided later by the measured offsets in record_log.json — never by this file.
"""
from __future__ import annotations

import json

from . import config

ACTION_EXEC_ESTIMATE_S = 0.4   # rough; the real cost is captured by measurement


def run(scenario: dict, narrate_doc: dict, cfg: config.Config) -> dict:
    sid, lang = scenario["scenario_id"], narrate_doc["lang"]
    ld = config.lang_dir(sid, lang)
    audio_by_id = {s["id"]: s["duration"] for s in narrate_doc["steps"]}

    steps = []
    for step in scenario["steps"]:
        audio = audio_by_id[step["id"]]
        settle = step.get("settle_ms", 0) / 1000.0
        floor = cfg.cursor_travel_s + ACTION_EXEC_ESTIMATE_S + settle
        step_duration = max(audio, floor) + cfg.tail_pad_s
        steps.append({
            "id": step["id"],
            "audio_duration": round(audio, 3),
            "step_duration": round(step_duration, 3),
        })

    doc = {
        "scenario_id": sid,
        "lang": lang,
        "fps": cfg.fps,
        "rec_start_pad": cfg.rec_start_pad_s,
        "steps": steps,
    }
    (ld / "timeline.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return doc
