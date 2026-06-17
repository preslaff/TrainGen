"""TTS offline backend — narration length scales with TRAINGEN_ESPEAK_SPEED (so audio
pace is tunable, and the silent fallback stays timing-consistent). Offline; works whether
or not espeak-ng is installed (both honour -s / the wpm).

    python -m tests.test_tts
"""
from __future__ import annotations

import os
import sys
import tempfile
import wave
from pathlib import Path

from traingen import tts


def _dur(path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / float(w.getframerate())


def test_speed_scales_narration_length():
    d = Path(tempfile.mkdtemp())
    text = "one two three four five six seven eight"
    try:
        os.environ["TRAINGEN_ESPEAK_SPEED"] = "60"
        tts.OfflineBackend().synth(text, "en", "voice_en_calm", d / "slow.wav")
        os.environ["TRAINGEN_ESPEAK_SPEED"] = "240"
        tts.OfflineBackend().synth(text, "en", "voice_en_calm", d / "fast.wav")
    finally:
        os.environ.pop("TRAINGEN_ESPEAK_SPEED", None)
    slow, fast = _dur(d / "slow.wav"), _dur(d / "fast.wav")
    assert slow > fast, f"lower wpm -> longer narration ({slow:.2f}s vs {fast:.2f}s)"
    print(f"OK  tts: speed tunes narration length ({slow:.2f}s @60wpm vs {fast:.2f}s @240wpm)")


def main() -> int:
    test_speed_scales_narration_length()
    print("\nall tts tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
