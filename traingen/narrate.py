"""Stage 2 — narrate: narration text -> one WAV per step + measured durations.
Cache key = sha256(text + voice + lang + backend) so unchanged lines never
re-synthesize (BLUEPRINT §6)."""
from __future__ import annotations

import json
import wave

from . import config
from .cache import digest
from .tts import get_backend


def _duration(path) -> float:
    try:
        import soundfile as sf
        return float(sf.info(str(path)).duration)
    except Exception:
        with wave.open(str(path)) as w:
            return w.getnframes() / float(w.getframerate())


def run(script_doc: dict, cfg: config.Config, *, force: bool = False) -> dict:
    """Synthesize one WAV per step. `force=True` re-synthesizes every step even on a cache
    hit — used by `--regenerate-audio` to apply a server-side OmniVoice lexicon/stress fix,
    which leaves the cache key (text+voice+lang+backend) unchanged."""
    sid, lang = script_doc["scenario_id"], script_doc["lang"]
    ld = config.lang_dir(sid, lang)
    audio_dir = ld / "audio"
    audio_dir.mkdir(exist_ok=True)
    backend = get_backend(cfg.tts_backend)
    voice = script_doc.get("voice") or f"voice_{lang}_calm"

    steps = []
    for i, s in enumerate(script_doc["steps"]):
        wav = audio_dir / f"step_{i:02d}.wav"
        hashf = audio_dir / f"step_{i:02d}.hash"
        key = digest(s["narration"], voice, lang, cfg.tts_backend)
        fresh = (wav.exists() and hashf.exists()
                 and hashf.read_text(encoding="utf-8").strip() == key)
        if force or not fresh:
            backend.synth(s["narration"], lang, voice, wav)
            hashf.write_text(key, encoding="utf-8")
        steps.append({
            "id": s["id"],
            "wav": str(wav.relative_to(config.OUT)),
            "duration": round(_duration(wav), 3),
        })

    doc = {"scenario_id": sid, "lang": lang, "steps": steps}
    (ld / "narrate.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc
