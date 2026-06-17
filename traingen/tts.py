"""Pluggable TTS backends. Keep a fixed voice per language for library
consistency (BLUEPRINT §6).

- offline   : espeak-ng if installed, else silent WAVs sized by word count.
              Robotic / silent — only proves the timing model. No GPU, no creds.
- omnivoice : k2-fsa/OmniVoice (`pip install omnivoice torch`). Zero-shot
              multilingual; Bulgarian is inferred from Cyrillic text. Voice is
              steered via `instruct` design attributes. 24 kHz output.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import wave

# Map our manifest voice names -> OmniVoice voice-design attributes.
INSTRUCT = {
    "voice_bg_calm": "calm, instructional, neutral, female",
    "voice_en_calm": "calm, instructional, neutral, female",
}


class OfflineBackend:
    _ESPEAK_LANG = {"bg": "bg", "en": "en"}

    def __init__(self):
        # Speech speed in words/min (TRAINGEN_ESPEAK_SPEED). ~145 is calm/instructional;
        # also sizes the silent fallback so timing predictions stay consistent either way.
        self.wpm = int(os.environ.get("TRAINGEN_ESPEAK_SPEED", "145"))

    def synth(self, text: str, lang: str, voice: str, out_path) -> None:
        out_path = str(out_path)
        if shutil.which("espeak-ng"):
            subprocess.run(
                ["espeak-ng", "-v", self._ESPEAK_LANG.get(lang, "en"),
                 "-s", str(self.wpm), "-w", out_path, text],
                check=True,
            )
        else:
            self._silence(text, out_path, self.wpm)

    @staticmethod
    def _silence(text: str, out_path: str, wpm: int = 145, sr: int = 24000) -> None:
        words = max(1, len(text.split()))
        dur = words * 60.0 / wpm + 0.5      # spoken length at `wpm` + a little padding
        frames = int(dur * sr)
        with wave.open(out_path, "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(b"\x00\x00" * frames)


class OmniVoiceBackend:
    def __init__(self, model_id: str = "k2-fsa/OmniVoice"):
        self.model_id = model_id
        self._model = None

    def _load(self):
        if self._model is None:
            import torch
            from omnivoice import OmniVoice
            dev = "cuda:0" if torch.cuda.is_available() else "cpu"
            self._model = OmniVoice.from_pretrained(
                self.model_id,
                device_map=dev,
                dtype=torch.float16 if dev.startswith("cuda") else torch.float32,
            )
        return self._model

    def synth(self, text: str, lang: str, voice: str, out_path) -> None:
        import soundfile as sf
        audio = self._load().generate(
            text=text, instruct=INSTRUCT.get(voice, "calm, neutral"))
        sf.write(str(out_path), audio[0], 24000)


def get_backend(name: str):
    return OmniVoiceBackend() if name == "omnivoice" else OfflineBackend()
