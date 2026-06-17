"""Stage 1 — script: scenario goal + per-step intent -> narration text, per language.

The SSOT never contains narration (BLUEPRINT §3); it is generated here. Narration comes
from a pluggable narrator: AnthropicNarrator (Claude — calm, instructional, second person,
in the target language) when an API key is present, else EchoNarrator (uses the step
intent) so the chain still runs offline. One LLM call per (scenario, lang); cached.
"""
from __future__ import annotations

import json
import os

from . import config
from .cache import digest, is_fresh, write_stamp

_LANG_NAME = {"bg": "Bulgarian", "en": "English"}

_NARRATE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"steps": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {"id": {"type": "string"}, "narration": {"type": "string"}},
        "required": ["id", "narration"]}}},
    "required": ["steps"],
}


class EchoNarrator:
    """Offline fallback: narration = the step intent (English). No LLM, no key."""
    name = "echo"

    def narrate(self, goal: str, steps: list, lang: str) -> dict:
        return {s["id"]: s["intent"] for s in steps}


class AnthropicNarrator:
    """Generate per-language spoken narration for every step in one call."""
    name = "anthropic"

    def __init__(self, backend):
        self.backend = backend

    def narrate(self, goal: str, steps: list, lang: str) -> dict:
        ln = _LANG_NAME.get(lang, lang)
        system = (
            f"You write narration for a software training video, in {ln}. Tone: calm, "
            "instructional, second person. For EACH step write ONE natural spoken sentence "
            f"in {ln} that teaches what the user is doing and why — not a UI label, not a "
            "translation of the step id. Keep each sentence short enough to speak in a few "
            "seconds (roughly 8-18 words). Return JSON {steps:[{id, narration}]} covering "
            "every step, in order.")
        user = (f"Learning goal: {goal}\nSteps (id: what it teaches):\n"
                + "\n".join(f"- {s['id']}: {s['intent']}" for s in steps))
        out = self.backend.complete_json(system, user, _NARRATE_SCHEMA)
        got = {r["id"]: r["narration"] for r in out.get("steps", []) if r.get("narration")}
        return {s["id"]: got.get(s["id"], s["intent"]) for s in steps}   # per-step fallback


def get_narrator(cfg: config.Config):
    """Anthropic narrator when configured AND a key is present; otherwise echo (offline)."""
    if getattr(cfg, "script_backend", "anthropic") == "echo":
        return EchoNarrator()
    try:
        import anthropic  # noqa: F401
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return EchoNarrator()
        from .llm import AnthropicBackend
        return AnthropicNarrator(AnthropicBackend(
            getattr(cfg, "script_model", "claude-opus-4-8"),
            getattr(cfg, "script_effort", "low")))
    except Exception:
        return EchoNarrator()


def run(scenario: dict, lang: str, cfg: config.Config, narrator=None) -> dict:
    sid = scenario["scenario_id"]
    ld = config.lang_dir(sid, lang)
    out = ld / "script.json"
    narrator = narrator or get_narrator(cfg)
    key = digest("script-v2", scenario, lang, getattr(narrator, "name", "echo"))
    if is_fresh(ld / "script.hash", key, [out]):
        return json.loads(out.read_text(encoding="utf-8"))

    texts = narrator.narrate(scenario["goal"], scenario["steps"], lang)
    steps = [{"id": s["id"], "intent": s["intent"],
              "narration": texts.get(s["id"]) or s["intent"]} for s in scenario["steps"]]
    doc = {
        "scenario_id": sid,
        "lang": lang,
        "voice": cfg.voices.get(lang, f"voice_{lang}_calm"),
        "narrator": getattr(narrator, "name", "echo"),
        "steps": steps,
    }
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    write_stamp(ld / "script.hash", key)
    return doc
