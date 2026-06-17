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
from pathlib import Path

# Per-voice reference clips for deterministic voice cloning (consistent speaker +
# accent across every clip). Drop "<voice>.wav" plus "<voice>.txt" (the EXACT
# transcript of that clip) into TRAINGEN_VOICE_DIR. If a voice has no reference
# files, the remote backend falls back to `instruct` voice design.
_VOICE_DIR = Path(
    os.environ.get(
        "TRAINGEN_VOICE_DIR",
        str(Path(__file__).resolve().parent.parent / "assets" / "voices"),
    )
)

# Map our manifest voice names -> OmniVoice voice-design attributes.
# OmniVoice's `instruct` is a FIXED vocabulary — the server rejects anything else with
# HTTP 500. Valid English items: female/male; child/teenager/young adult/middle-aged/
# elderly; very low/low/moderate/high/very high pitch; whisper; and accents (british,
# american, indian, ...). Free-form words like "calm", "instructional", "neutral" are NOT
# valid. A calm instructional narrator maps to: female + young adult + moderate pitch.
# Use only English (comma + space) OR only Chinese (full-width comma) items, not a mix.
INSTRUCT = {
    "voice_bg_calm": "female, young adult, moderate pitch",
    "voice_en_calm": "female, young adult, moderate pitch",
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


class RemoteOmniVoiceBackend:
    """OmniVoice running on another LAN machine (no local GPU needed).

    Talks to `omnivoice/cli/serve.py` over HTTP and writes the returned 24 kHz
    WAV to `out_path`. Voice selection stays here, per `voice`:

    - if a "<voice>.wav" + "<voice>.txt" pair exists in TRAINGEN_VOICE_DIR, the
      reference is sent for deterministic voice cloning (same speaker + accent
      every time — the server caches the encoded prompt and decodes greedily);
    - otherwise it falls back to the `voice -> instruct` design mapping.

    Configure the server URL via TRAINGEN_OMNIVOICE_URL, e.g.
        TRAINGEN_OMNIVOICE_URL=http://192.168.78.101:8002
    """

    def __init__(self, url: str | None = None, voice_dir=None):
        base = url or os.environ.get("TRAINGEN_OMNIVOICE_URL", "http://localhost:8002")
        self.url = base.rstrip("/")
        self.voice_dir = Path(voice_dir) if voice_dir else _VOICE_DIR
        self._ref_cache: dict[str, tuple[str, str] | None] = {}

    def _reference(self, voice: str):
        """Return (base64_wav, transcript) for a voice, or None if unconfigured."""
        if voice not in self._ref_cache:
            import base64

            wav = self.voice_dir / f"{voice}.wav"
            txt = self.voice_dir / f"{voice}.txt"
            if wav.is_file() and txt.is_file():
                self._ref_cache[voice] = (
                    base64.b64encode(wav.read_bytes()).decode("ascii"),
                    txt.read_text(encoding="utf-8").strip(),
                )
            else:
                self._ref_cache[voice] = None
        return self._ref_cache[voice]

    def synth(self, text: str, lang: str, voice: str, out_path) -> None:
        import json
        import urllib.error
        import urllib.request

        payload = {"text": text}
        ref = self._reference(voice)
        if ref is not None:
            payload["ref_audio_b64"], payload["ref_text"] = ref
        else:
            payload["instruct"] = INSTRUCT.get(voice, "female, young adult, moderate pitch")

        req = urllib.request.Request(
            f"{self.url}/synth",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # Generation is serialized server-side and can take a while for long text.
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                data = resp.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise RuntimeError(
                f"OmniVoice server {self.url}/synth returned HTTP {e.code}: {body}") from None
        with open(str(out_path), "wb") as f:
            f.write(data)


def get_backend(name: str):
    if name == "omnivoice":
        return OmniVoiceBackend()
    if name in ("omnivoice_remote", "omnivoice-remote"):
        return RemoteOmniVoiceBackend()
    return OfflineBackend()
