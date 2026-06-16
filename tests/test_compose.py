"""Compose intro/outro concat test — synthesizes tiny clips with ffmpeg and checks the
normalize+concat helper joins them into one valid A/V file. Skips if ffmpeg is absent.

    python -m tests.test_compose
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from traingen import compose
from traingen import config as prod_config


def _clip(path, seconds, color):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x240:r=30:d={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(path)],
        check=True, capture_output=True)


def _probe(path, entries):
    return subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", entries, "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True).stdout.strip()


def main() -> int:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("SKIP test_compose: ffmpeg/ffprobe not installed")
        return 0

    d = Path(tempfile.mkdtemp())
    intro, body, outro, final = d / "i.mp4", d / "b.mp4", d / "o.mp4", d / "final.mp4"
    _clip(intro, 1.0, "red")
    _clip(body, 2.0, "blue")
    _clip(outro, 1.0, "green")

    cfg = prod_config.Config(base_url="", viewport={"width": 320, "height": 240}, fps=30,
                             cursor_travel_s=0, tail_pad_s=0, langs=["bg"], voices={})
    compose._concat([intro, body, outro], final, cfg)

    dur = float(_probe(final, "format=duration"))
    codecs = _probe(final, "stream=codec_type").split()
    assert abs(dur - 4.0) < 1.0, f"concat duration {dur:.2f}s (expected ~4)"
    assert codecs.count("video") == 1 and codecs.count("audio") == 1, \
        f"expected exactly one video + one audio stream, got {codecs}"
    assert not (d / "_concat.txt").exists() and not (d / "_norm_0.mp4").exists(), "temp files cleaned"
    print(f"OK  compose: intro(1s)+body(2s)+outro(1s) concat -> {dur:.2f}s, video+audio, temps cleaned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
