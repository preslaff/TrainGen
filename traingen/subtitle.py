"""Stage 6 — subtitle (BLUEPRINT §7). We know the exact narration text and the exact
audio, so we ALIGN rather than transcribe. Each step's narration is timed and shifted by
that step's `measured_start` (from record_log.json), then concatenated into one soft VTT
sidecar per language (`final.<lang>.vtt`) — switchable BG/EN in the help-center player, no
re-encode.

Default backend = per-step cues: one cue per step spanning its measured [start, end].
Deterministic, no dependencies. Optional `aeneas` backend (lang codes bul/eng) subdivides
each step's text into finer word/fragment cues; opt-in via `subtitles: aeneas`.
"""
from __future__ import annotations

from . import config

_AENEAS_LANG = {"bg": "bul", "en": "eng"}


def _ts(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _to_vtt(cues: list) -> str:
    body = "".join(f"{_ts(a)} --> {_ts(b)}\n{t}\n\n" for a, b, t in cues)
    return "WEBVTT\n\n" + body


class AeneasAligner:
    """Optional finer alignment via aeneas (CPU-only). Lazily imported; falls back to a
    single whole-step cue on any error. Unrun without aeneas installed."""

    def fragments(self, text: str, audio_path: str, lang: str, duration: float):
        import tempfile
        from aeneas.executetask import ExecuteTask
        from aeneas.task import Task
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
                f.write(text.replace(". ", ".\n"))   # one fragment per sentence
                text_path = f.name
            conf = f"task_language={_AENEAS_LANG.get(lang, 'eng')}|os_task_file_format=json|is_text_type=plain"
            task = Task(config_string=conf)
            task.audio_file_path_absolute = str(audio_path)
            task.text_file_path_absolute = text_path
            ExecuteTask(task).execute()
            return [(float(fr.begin), float(fr.end), fr.text) for fr in task.sync_map.fragments if fr.text]
        except Exception:
            return [(0.0, duration, text)]


def get_aligner(cfg):
    if getattr(cfg, "subtitles", "per_step") == "aeneas":
        return AeneasAligner()
    return None


def run(script_doc: dict, narrate_doc: dict, record_log: dict, cfg, aligner=None) -> "config.Path":
    sid, lang = record_log["scenario_id"], record_log["lang"]
    ld = config.lang_dir(sid, lang)
    aligner = aligner if aligner is not None else get_aligner(cfg)
    narration = {s["id"]: s["narration"] for s in script_doc["steps"]}
    duration = {s["id"]: s.get("duration", 0.0) for s in narrate_doc.get("steps", [])}
    wav = {s["id"]: config.OUT / s["wav"] for s in narrate_doc.get("steps", []) if s.get("wav")}

    # compose trims the pre-roll so the body starts at t0; measured offsets are already relative
    # to t0, so cues align directly (no rec_offset shift needed here).
    cues = []
    for st in record_log["steps"]:
        text = (narration.get(st["id"]) or "").strip()
        if not text:
            continue
        start = st["measured_start"]
        if aligner and st["id"] in wav:
            for b, e, frag in aligner.fragments(text, wav[st["id"]], lang, duration.get(st["id"], 0.0)):
                cues.append((start + b, start + e, frag.strip()))
        else:
            cues.append((start, st["measured_end"], text))

    out = ld / f"final.{lang}.vtt"
    out.write_text(_to_vtt(cues), encoding="utf-8")
    return out
