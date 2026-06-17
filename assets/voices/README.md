# Voice reference clips

Drop one short reference clip per manifest voice here to pin a **consistent,
deterministic speaker + accent** for the `omnivoice_remote` TTS backend.

## Convention

For a manifest voice named `voice_bg_calm`, add two files:

```
voice_bg_calm.wav    # 5–10s clean reference clip, same language as the narration
voice_bg_calm.txt    # the EXACT transcript of that clip (verbatim, with punctuation)
```

The backend (`traingen/tts.py` → `RemoteOmniVoiceBackend`) sends this pair to the
OmniVoice server, which clones the voice and decodes greedily — so every clip in
the video uses the same voice. If a voice has **no** matching `.wav` + `.txt`
pair here, the backend falls back to `instruct` voice design (a non-deterministic
voice that varies per clip).

## Notes

- Use a reference in the **same language** as the narration, or the clone carries
  a foreign accent (e.g. use a Bulgarian clip for `voice_bg_*`).
- Keep it 5–10s, clean (no music/noise), with clear, neutral prosody.
- The transcript must match the audio word-for-word — a mismatch causes wrong
  emphasis. If unsure, leave the `.txt` out and let the server transcribe, but
  a hand-checked transcript is best.
- Override this directory with the `TRAINGEN_VOICE_DIR` env var.
