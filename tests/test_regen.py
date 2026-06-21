"""Regenerate-on-demand tests — offline. Covers the two flows that let a server-side OmniVoice
lexicon/stress fix reach the videos without drifting the narration text:

  * narrate(force=True) re-synthesizes even on a cache hit (forced audio);
  * script.run reuses the durable narration store VERBATIM (deterministic, no LLM), with an
    intent fallback for steps missing from the store; force_regen ignores the store + re-saves;
  * reaudio_one re-narrates (forced) + recomposes from the kept script WITHOUT regenerating
    the script or re-recording.

Redirects OUT and NARRATION to tempdirs so neither real out/ nor the real narration/ is touched.

    python -m tests.test_regen
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from traingen import config as prod_config

prod_config.OUT = Path(tempfile.mkdtemp())
prod_config.NARRATION = Path(tempfile.mkdtemp())

from traingen import narrate, script   # noqa: E402  (after OUT/NARRATION redirect)

SCENARIO = {
    "scenario_id": "demo", "goal": "Teach creating a thing.",
    "steps": [{"id": "open", "intent": "Open the form"},
              {"id": "save", "intent": "Save the thing"}],
}


class StubNarrator:
    name = "stub"

    def __init__(self):
        self.calls = 0

    def narrate(self, goal, steps, lang, style="instructional"):
        self.calls += 1
        return {s["id"]: f"GEN {s['id']}" for s in steps}


class CountingTTS:
    """Stub TTS backend: counts synth calls and writes a tiny valid WAV."""
    def __init__(self):
        self.calls = 0

    def synth(self, text, lang, voice, out_path):
        self.calls += 1
        import wave
        with wave.open(str(out_path), "w") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
            w.writeframes(b"\x00\x00" * 2400)


class _Cfg:
    tts_backend = "stub"
    voices = {"bg": "voice_bg_calm"}


def _fresh():
    import shutil
    shutil.rmtree(prod_config.OUT, ignore_errors=True)
    shutil.rmtree(prod_config.NARRATION, ignore_errors=True)


def test_narrate_force_resynthesizes():
    _fresh()
    tts = CountingTTS()
    orig = narrate.get_backend
    narrate.get_backend = lambda name: tts
    try:
        sdoc = {"scenario_id": "demo", "lang": "bg", "voice": "voice_bg_calm",
                "steps": [{"id": "open", "narration": "Здравей"}]}
        narrate.run(sdoc, _Cfg())
        assert tts.calls == 1, "first synth"
        narrate.run(sdoc, _Cfg())                       # same text -> cache hit
        assert tts.calls == 1, "unchanged text caches (no re-synth)"
        narrate.run(sdoc, _Cfg(), force=True)           # lexicon fix: force past the cache
        assert tts.calls == 2, "force=True re-synthesizes even though the text is unchanged"
    finally:
        narrate.get_backend = orig
    print("OK  narrate: force=True re-synthesizes on a cache hit; default still caches")


def test_store_used_verbatim_without_llm():
    _fresh()
    cfg = _Cfg()
    n = StubNarrator()
    d1 = script.run(SCENARIO, "bg", cfg, narrator=n)     # first run generates + saves store
    assert n.calls == 1 and d1["locked"] is False
    assert prod_config.script_store("demo", "bg").exists(), "store auto-saved on generation"
    d2 = script.run(SCENARIO, "bg", cfg, narrator=n)     # store now exists -> verbatim
    assert n.calls == 1, "store reused -> narrator NOT called again (deterministic)"
    assert d2["locked"] is True
    assert d2["steps"][0]["narration"] == "GEN open" and d2["steps"][0]["source"] == "stored"
    print("OK  script: durable store reused verbatim, no LLM on re-run")


def test_store_missing_step_falls_back_to_intent():
    _fresh()
    cfg = _Cfg()
    # store covers only 'open'
    prod_config.NARRATION.mkdir(parents=True, exist_ok=True)
    prod_config.script_store("demo", "bg").write_text(json.dumps(
        {"scenario_id": "demo", "lang": "bg", "steps": {"open": "Фиксиран текст"}}),
        encoding="utf-8")
    n = StubNarrator()
    doc = script.run(SCENARIO, "bg", cfg, narrator=n)
    assert n.calls == 0, "store present -> no LLM"
    assert doc["steps"][0]["narration"] == "Фиксиран текст" and doc["steps"][0]["source"] == "stored"
    assert doc["steps"][1]["narration"] == "Save the thing" and doc["steps"][1]["source"] == "intent"
    print("OK  script: step missing from store -> intent fallback, flagged")


def test_force_regen_ignores_store():
    _fresh()
    cfg = _Cfg()
    prod_config.NARRATION.mkdir(parents=True, exist_ok=True)
    sp = prod_config.script_store("demo", "bg")
    sp.write_text(json.dumps({"scenario_id": "demo", "lang": "bg",
                              "steps": {"open": "OLD", "save": "OLD"}}), encoding="utf-8")
    n = StubNarrator()
    doc = script.run(SCENARIO, "bg", cfg, narrator=n, force_regen=True)
    assert n.calls == 1, "force_regen -> regenerate via LLM"
    assert doc["locked"] is False and doc["steps"][0]["narration"] == "GEN open"
    # store overwritten with the fresh text
    assert json.loads(sp.read_text())["steps"]["open"] == "GEN open", "force_regen re-saves the store"
    print("OK  script: force_regen ignores the store and re-saves fresh narration")


def test_reaudio_one_renarrates_without_script_or_record(monkeypatch=None):
    _fresh()
    import run as runmod
    cfg = _Cfg()
    ld = prod_config.lang_dir("demo", "bg")
    (ld / "script.json").write_text(json.dumps(
        {"scenario_id": "demo", "lang": "bg", "voice": "voice_bg_calm",
         "steps": [{"id": "open", "narration": "Здравей"}]}), encoding="utf-8")
    (ld / "record_log.json").write_text(json.dumps(
        {"scenario_id": "demo", "lang": "bg", "video": "demo/bg/video.webm",
         "steps": [{"id": "open", "measured_start": 0.5, "measured_end": 3.0}]}), encoding="utf-8")

    tts = CountingTTS()
    calls = {"narrate": 0, "subtitle": 0, "compose": 0, "script": 0, "record": 0}
    o_get, o_sub, o_comp = narrate.get_backend, runmod.subtitle.run, runmod.compose.run
    o_scr, o_rec = runmod.script.run, runmod.record.run
    narrate.get_backend = lambda name: tts
    runmod.script.run = lambda *a, **k: calls.__setitem__("script", calls["script"] + 1)
    runmod.record.run = lambda *a, **k: calls.__setitem__("record", calls["record"] + 1)
    runmod.subtitle.run = lambda *a, **k: (calls.__setitem__("subtitle", calls["subtitle"] + 1),
                                           Path("x.vtt"))[1]
    runmod.compose.run = lambda *a, **k: (calls.__setitem__("compose", calls["compose"] + 1),
                                          ld / "final.mp4")[1]
    try:
        runmod.reaudio_one("demo", "bg", cfg)
    finally:
        narrate.get_backend = o_get
        runmod.subtitle.run, runmod.compose.run = o_sub, o_comp
        runmod.script.run, runmod.record.run = o_scr, o_rec

    assert tts.calls == 1, "audio re-synthesized (forced) from the kept script"
    assert calls["subtitle"] == 1 and calls["compose"] == 1, "recomposed"
    assert calls["script"] == 0 and calls["record"] == 0, "no script regen, no re-record"
    print("OK  reaudio_one: forces audio + recompose from kept script; no script/record")


def main() -> int:
    test_narrate_force_resynthesizes()
    test_store_used_verbatim_without_llm()
    test_store_missing_step_falls_back_to_intent()
    test_force_regen_ignores_store()
    test_reaudio_one_renarrates_without_script_or_record()
    print("\nall regen tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
