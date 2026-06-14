"""Offline proof of the v0.1 timing model — no platform, no browser.

Exercises script -> narrate -> choreograph -> compose using the REAL stages, with
a synthetic video standing in for the Playwright capture and a fabricated
record_log.json supplying measured offsets. Proves that compose places each
narration clip at its measured_start and muxes a valid A/V file (BLUEPRINT §4, §8).

Run: python -m tests.test_timing
"""
from __future__ import annotations

import json
import subprocess
import sys

from traingen import choreograph, compose, config, narrate, script

SCENARIO_ID = "add-partner-profile"
LANG = "bg"


def _ffprobe(path, *args) -> str:
    return subprocess.run(
        ["ffprobe", "-v", "error", *args, "-of",
         "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _synth_video(path, seconds, cfg):
    """A solid-color clip standing in for the Playwright recording."""
    w, h = cfg.viewport["width"], cfg.viewport["height"]
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"color=c=slategray:s={w}x{h}:r={cfg.fps}:d={seconds:.3f}",
         "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True,
    )


def main() -> int:
    cfg = config.load_config()
    cfg.tts_backend = "offline"
    scenario = config.get_scenario(SCENARIO_ID)
    ld = config.lang_dir(SCENARIO_ID, LANG)

    sdoc = script.run(scenario, LANG, cfg)
    ndoc = narrate.run(sdoc, cfg)
    timeline = choreograph.run(scenario, ndoc, cfg)

    # Fabricate measured offsets: steps run back-to-back after rec_start_pad,
    # each dwelling its predicted step_duration. (record.py measures these live.)
    t = cfg.rec_start_pad_s
    rec_steps = []
    for s in timeline["steps"]:
        start = t
        end = t + s["step_duration"]
        rec_steps.append({"id": s["id"],
                          "measured_start": round(start, 3),
                          "measured_end": round(end, 3)})
        t = end
    total = t + cfg.tail_pad_s

    _synth_video(ld / "video.webm", total, cfg)
    record_log = {
        "scenario_id": SCENARIO_ID, "lang": LANG, "fps": cfg.fps,
        "rec_start_pad": cfg.rec_start_pad_s,
        "video": str((ld / "video.webm").relative_to(config.OUT)),
        "steps": rec_steps,
    }
    (ld / "record_log.json").write_text(
        json.dumps(record_log, ensure_ascii=False, indent=2), encoding="utf-8")

    final = compose.run(record_log, ndoc, cfg)

    # --- assertions ---
    codecs = _ffprobe(final, "-select_streams", "v", "-show_entries",
                      "stream=codec_name").splitlines()
    acodecs = _ffprobe(final, "-select_streams", "a", "-show_entries",
                       "stream=codec_name").splitlines()
    dur = float(_ffprobe(final, "-show_entries", "format=duration"))

    assert codecs and codecs[0] == "h264", f"expected h264 video, got {codecs}"
    assert acodecs and acodecs[0] == "aac", f"expected aac audio, got {acodecs}"
    assert abs(dur - total) < 1.0, f"duration {dur:.2f}s drifted from {total:.2f}s"
    # Last narration must start at its measured offset, well inside the clip.
    assert rec_steps[-1]["measured_start"] < dur, "last clip starts past end of video"

    print(f"OK  {len(rec_steps)} steps  video={dur:.2f}s "
          f"(expected {total:.2f}s)  v={codecs[0]} a={acodecs[0]}")
    print(f"    last narration pinned at measured_start="
          f"{rec_steps[-1]['measured_start']}s -> {final}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
