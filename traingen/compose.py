"""Stage 5 — compose (FFmpeg, BLUEPRINT §8). Build one continuous audio track by placing
each step's narration WAV at its MEASURED start offset (adelay = measured_start * 1000),
mix without volume drop (normalize=0), and mux onto the transcoded video → the body. Then
optionally prepend `assets/intro_<lang>.mp4` / append `assets/outro_<lang>.mp4`, normalizing
each segment to a canonical 1920x1080@fps h264/aac so the concat is clean. Subtitles are a
separate soft VTT sidecar (subtitle.py), not burned in.
"""
from __future__ import annotations

import shutil
import subprocess

from . import config

ASSETS = config.ROOT / "assets"
_CANON_FPS = 30


def _build_body(record_log: dict, narrate_doc: dict, cfg, body):
    video = config.OUT / record_log["video"]
    wav_by_id = {s["id"]: config.OUT / s["wav"] for s in narrate_doc["steps"]}
    inputs, filters, labels = ["-i", str(video)], [], []
    for i, st in enumerate(record_log["steps"]):
        inputs += ["-i", str(wav_by_id[st["id"]])]
        ms = int(round(st["measured_start"] * 1000))
        filters.append(f"[{i + 1}:a]adelay={ms}:all=1[a{i}]")
        labels.append(f"[a{i}]")
    fc = ";".join(filters) + f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0[aout]"
    subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", fc,
                    "-map", "0:v", "-map", "[aout]",
                    "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                    "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
                    "-r", str(cfg.fps), str(body)], check=True)


def _has_audio(src) -> bool:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
         "-of", "csv=p=0", str(src)], capture_output=True, text=True).stdout.strip()
    return bool(out)


def _normalize(src, dst, cfg):
    """Re-encode a segment to ONE canonical video + ONE audio track (48 kHz stereo aac,
    WxH@fps h264) so segments concat with -c copy. Keeps the source audio (e.g. the body's
    narration); synthesizes silence only when the source is video-only (a bumper)."""
    w, h = cfg.viewport.get("width", 1920), cfg.viewport.get("height", 1080)
    vf = f"scale={w}:{h},fps={cfg.fps},format=yuv420p"
    common = ["-c:v", "libx264", "-crf", "18", "-preset", "medium",
              "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-ar", "48000", str(dst)]
    if _has_audio(src):
        cmd = ["ffmpeg", "-y", "-i", str(src), "-map", "0:v:0", "-map", "0:a:0",
               "-vf", vf, *common]
    else:
        cmd = ["ffmpeg", "-y", "-i", str(src),
               "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
               "-map", "0:v:0", "-map", "1:a:0", "-shortest", "-vf", vf, *common]
    subprocess.run(cmd, check=True)


def _concat(segments, final, cfg):
    norm = []
    for i, seg in enumerate(segments):
        n = final.parent / f"_norm_{i}.mp4"
        _normalize(seg, n, cfg)
        norm.append(n)
    listfile = final.parent / "_concat.txt"
    listfile.write_text("".join(f"file '{n.resolve()}'\n" for n in norm), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
                    "-c", "copy", str(final)], check=True)
    for n in norm:
        n.unlink(missing_ok=True)
    listfile.unlink(missing_ok=True)


def run(record_log: dict, narrate_doc: dict, cfg: config.Config):
    sid, lang = record_log["scenario_id"], record_log["lang"]
    ld = config.lang_dir(sid, lang)
    final = ld / "final.mp4"

    body = ld / "body.mp4"
    _build_body(record_log, narrate_doc, cfg, body)

    intro, outro = ASSETS / f"intro_{lang}.mp4", ASSETS / f"outro_{lang}.mp4"
    segments = ([intro] if intro.exists() else []) + [body] + ([outro] if outro.exists() else [])
    if len(segments) == 1:
        shutil.move(str(body), str(final))     # no bumpers — body is the final
    else:
        _concat(segments, final, cfg)
        body.unlink(missing_ok=True)
    return final
