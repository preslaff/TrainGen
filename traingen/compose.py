"""Stage 5 — compose (FFmpeg). Build one continuous audio track by placing each
step's narration WAV at its MEASURED start offset (adelay = measured_start * 1000),
mix without volume drop (normalize=0), and mux onto the transcoded video
(BLUEPRINT §8). v0.1: no intro/outro/subtitles — those land in v0.3.
"""
from __future__ import annotations

import subprocess

from . import config


def run(record_log: dict, narrate_doc: dict, cfg: config.Config):
    sid, lang = record_log["scenario_id"], record_log["lang"]
    ld = config.lang_dir(sid, lang)
    video = config.OUT / record_log["video"]
    wav_by_id = {s["id"]: config.OUT / s["wav"] for s in narrate_doc["steps"]}

    inputs, filters, labels = ["-i", str(video)], [], []
    for i, st in enumerate(record_log["steps"]):
        inputs += ["-i", str(wav_by_id[st["id"]])]
        ms = int(round(st["measured_start"] * 1000))
        idx = i + 1                       # input 0 is the video
        filters.append(f"[{idx}:a]adelay={ms}:all=1[a{i}]")
        labels.append(f"[a{i}]")

    n = len(labels)
    fc = ";".join(filters) + \
        f";{''.join(labels)}amix=inputs={n}:normalize=0[aout]"

    final = ld / "final.mp4"
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", fc,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", "-r", str(cfg.fps),
        str(final),
    ]
    subprocess.run(cmd, check=True)
    return final
