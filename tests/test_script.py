"""Script-narration tests — offline. A stub narrator stands in for Claude so per-language
narration, backend selection, and caching are exercised without an API key.

    python -m tests.test_script
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from traingen import config as prod_config
from traingen import script

prod_config.OUT = Path(tempfile.mkdtemp())          # never touch real out/
prod_config.NARRATION = Path(tempfile.mkdtemp())    # never touch the real narration/ store

SCENARIO = {
    "scenario_id": "demo", "goal": "Teach creating a thing.",
    "steps": [{"id": "open", "intent": "Open the form"},
              {"id": "save", "intent": "Save the thing"}],
}


class StubNarrator:
    name = "stub"

    def __init__(self, lang_text):
        self.lang_text = lang_text
        self.calls = 0

    def narrate(self, goal, steps, lang, style="instructional"):
        self.calls += 1
        self.last_style = style
        return {s["id"]: f"[{lang}] {self.lang_text}: {s['id']}" for s in steps}


def _cfg():
    return prod_config.Config(base_url="", viewport={}, fps=30, cursor_travel_s=0.8,
                              tail_pad_s=0.4, langs=["bg", "en"], voices={})


def test_echo_fallback_when_no_key(monkeypatch=None):
    import os
    os.environ.pop("ANTHROPIC_API_KEY", None)
    cfg = _cfg()                       # script_backend defaults to "anthropic"
    n = script.get_narrator(cfg)
    assert n.name == "echo", "no API key -> echo fallback so the chain runs offline"
    assert script.EchoNarrator().narrate(SCENARIO["goal"], SCENARIO["steps"], "bg") == {
        "open": "Open the form", "save": "Save the thing"}
    cfg.script_backend = "echo"
    assert script.get_narrator(cfg).name == "echo"
    print("OK  narrator: echo fallback without a key; echo returns intents")


def test_run_uses_narrator_per_language_and_caches():
    shutil.rmtree(prod_config.OUT, ignore_errors=True)
    shutil.rmtree(prod_config.NARRATION, ignore_errors=True)
    cfg = _cfg()
    bg = StubNarrator("BG")
    doc = script.run(SCENARIO, "bg", cfg, narrator=bg)
    assert doc["narrator"] == "stub" and doc["lang"] == "bg"
    assert doc["steps"][0]["narration"] == "[bg] BG: open"
    assert bg.calls == 1
    script.run(SCENARIO, "bg", cfg, narrator=bg)
    assert bg.calls == 1, "second run served from cache (hash includes narrator name)"

    en = StubNarrator("EN")             # different language -> different lang_dir, own narration
    docs_en = script.run(SCENARIO, "en", cfg, narrator=en)
    assert docs_en["steps"][1]["narration"] == "[en] EN: save"
    print("OK  run: narration is per-language and cached; narrator name recorded")


def test_narration_style_routed_from_scenario():
    shutil.rmtree(prod_config.OUT, ignore_errors=True)
    shutil.rmtree(prod_config.NARRATION, ignore_errors=True)
    cfg = _cfg()
    n = StubNarrator("BG")
    promo = {**SCENARIO, "scenario_id": "promo", "narration_style": "promotional"}
    script.run(promo, "bg", cfg, narrator=n)
    assert n.last_style == "promotional", "scenario narration_style reaches the narrator"
    # default scenario -> instructional
    n2 = StubNarrator("BG")
    script.run(SCENARIO, "en", cfg, narrator=n2)
    assert n2.last_style == "instructional", "no narration_style -> instructional default"
    # the two system prompts differ in voice
    assert "advert" in script._system_for("promotional", "English").lower()
    assert "training" in script._system_for("instructional", "English").lower()
    print("OK  style: narration_style routes promotional vs instructional system prompt")


def main() -> int:
    test_echo_fallback_when_no_key()
    test_run_uses_narrator_per_language_and_caches()
    test_narration_style_routed_from_scenario()
    print("\nall script tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
