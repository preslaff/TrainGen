"""Subtitle tests — offline, no aeneas. Verifies per-step VTT cues are timed by the
measured offsets and formatted as valid WebVTT.

    python -m tests.test_subtitle
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from traingen import config as prod_config
from traingen import subtitle

prod_config.OUT = Path(tempfile.mkdtemp())


def test_per_step_vtt():
    script_doc = {"steps": [
        {"id": "open", "narration": "Първо отворете формата."},
        {"id": "blank", "narration": ""},                 # no text -> no cue
        {"id": "save", "narration": "Запазете промените."}]}
    narrate_doc = {"steps": []}
    record_log = {"scenario_id": "demo", "lang": "bg", "steps": [
        {"id": "open", "measured_start": 0.5, "measured_end": 4.25},
        {"id": "blank", "measured_start": 4.25, "measured_end": 5.0},
        {"id": "save", "measured_start": 5.0, "measured_end": 9.123}]}

    out = subtitle.run(script_doc, narrate_doc, record_log, prod_config.Config(
        base_url="", viewport={}, fps=30, cursor_travel_s=0, tail_pad_s=0, langs=["bg"], voices={}))
    vtt = out.read_text(encoding="utf-8")

    assert out.name == "final.bg.vtt"
    assert vtt.startswith("WEBVTT\n\n")
    assert vtt.count(" --> ") == 2, "two cues (blank step skipped)"
    assert "00:00:00.500 --> 00:00:04.250\nПърво отворете формата." in vtt
    assert "00:00:05.000 --> 00:00:09.123\nЗапазете промените." in vtt
    print("OK  subtitle: per-step VTT timed by measured offsets, blank skipped, BG text intact")


def test_timestamp_format():
    assert subtitle._ts(0) == "00:00:00.000"
    assert subtitle._ts(3661.5) == "01:01:01.500"
    print("OK  subtitle: timestamp formatting (h:m:s.ms)")


def main() -> int:
    test_per_step_vtt()
    test_timestamp_format()
    print("\nall subtitle tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
