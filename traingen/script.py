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


# Narration styles -> system prompt. Default "instructional" (training); "promotional" is the
# marketing voice for platform/advert videos. The user prompt framing differs per style too.
def _system_for(style: str, ln: str) -> str:
    if style == "promotional":
        return (
            f"You write the voiceover for a PROMOTIONAL product video advertising a tourism "
            f"platform, in {ln}. Tone: warm, aspirational, confident — a polished brand advert, "
            "not a tutorial. For EACH beat write ONE short, vivid spoken sentence in "
            f"{ln} that conveys the VALUE or idea of what's on screen — never a UI label or an "
            "instruction. Vary the openings; together the sentences should flow as one building "
            "pitch. Keep each ~8-16 words. Return JSON {steps:[{id, narration}]} covering every "
            "beat, in order.")
    return (
        f"You write narration for a software training video, in {ln}. Tone: calm, "
        "instructional, second person. For EACH step write ONE natural spoken sentence "
        f"in {ln} that teaches what the user is doing and why — not a UI label, not a "
        "translation of the step id. Keep each sentence short enough to speak in a few "
        "seconds (roughly 8-18 words). Return JSON {steps:[{id, narration}]} covering "
        "every step, in order.")


class EchoNarrator:
    """Offline fallback: narration = the step intent (English). No LLM, no key."""
    name = "echo"

    def narrate(self, goal: str, steps: list, lang: str, style: str = "instructional") -> dict:
        return {s["id"]: s["intent"] for s in steps}


class AnthropicNarrator:
    """Generate per-language spoken narration for every step in one call."""
    name = "anthropic"

    def __init__(self, backend):
        self.backend = backend

    def narrate(self, goal: str, steps: list, lang: str, style: str = "instructional") -> dict:
        ln = _LANG_NAME.get(lang, lang)
        system = _system_for(style, ln)
        lead = "Video goal" if style == "promotional" else "Learning goal"
        item = "what it shows" if style == "promotional" else "what it teaches"
        user = (f"{lead}: {goal}\nBeats (id: {item}):\n"
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


def _save_store(path, doc: dict) -> None:
    """Persist a generated script doc to the durable, git-tracked narration store."""
    import datetime
    path.parent.mkdir(parents=True, exist_ok=True)
    store = {
        "scenario_id": doc["scenario_id"], "lang": doc["lang"],
        "saved_at": datetime.date.today().isoformat(),
        "narrator": doc.get("narrator", "echo"),
        "steps": {s["id"]: s["narration"] for s in doc["steps"]},
    }
    path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def _doc_from_store(scenario: dict, lang: str, cfg, store: dict) -> dict:
    """Build the script doc VERBATIM from the durable store (no LLM). Steps missing from the
    store (e.g. a newly added scenario step) fall back to their intent, flagged + logged."""
    sid = scenario["scenario_id"]
    stored = store.get("steps", {})
    steps = []
    for s in scenario["steps"]:
        if s["id"] in stored:
            steps.append({"id": s["id"], "intent": s["intent"],
                          "narration": stored[s["id"]], "source": "stored"})
        else:
            print(f"[{sid}/{lang}] script: step '{s['id']}' not in the narration store "
                  "-> intent fallback (run --regenerate-script to capture it)")
            steps.append({"id": s["id"], "intent": s["intent"],
                          "narration": s["intent"], "source": "intent"})
    return {
        "scenario_id": sid, "lang": lang,
        "voice": cfg.voices.get(lang, f"voice_{lang}_calm"),
        "narrator": store.get("narrator", "stored"),
        "locked": True,
        "steps": steps,
    }


def run(scenario: dict, lang: str, cfg: config.Config, narrator=None, *,
        force_regen: bool = False) -> dict:
    """Generate per-language narration, persisting it to a durable store. Once a store exists
    the narration is reused VERBATIM (deterministic, no LLM) so OmniVoice lexicon tuning never
    drifts; only `force_regen=True` (run.py --regenerate-script) produces fresh text."""
    sid = scenario["scenario_id"]
    ld = config.lang_dir(sid, lang)
    out = ld / "script.json"
    store_path = config.script_store(sid, lang)

    # Deterministic path: reuse the durable store verbatim (no LLM).
    if not force_regen and store_path.exists():
        doc = _doc_from_store(scenario, lang, cfg,
                              json.loads(store_path.read_text(encoding="utf-8")))
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        return doc

    narrator = narrator or get_narrator(cfg)
    key = digest("script-v2", scenario, lang, getattr(narrator, "name", "echo"))
    # No store yet but a fresh working copy exists (pre-store recordings): migrate it into the
    # durable store so it persists across `out/` wipes, then use it.
    if not force_regen and is_fresh(ld / "script.hash", key, [out]):
        doc = json.loads(out.read_text(encoding="utf-8"))
        _save_store(store_path, doc)
        return doc

    style = scenario.get("narration_style", "instructional")   # "promotional" for advert videos
    texts = narrator.narrate(scenario["goal"], scenario["steps"], lang, style)
    steps = [{"id": s["id"], "intent": s["intent"],
              "narration": texts.get(s["id"]) or s["intent"],
              "source": "generated" if texts.get(s["id"]) else "intent"}
             for s in scenario["steps"]]
    doc = {
        "scenario_id": sid,
        "lang": lang,
        "voice": cfg.voices.get(lang, f"voice_{lang}_calm"),
        "narrator": getattr(narrator, "name", "echo"),
        "locked": False,
        "steps": steps,
    }
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    write_stamp(ld / "script.hash", key)
    _save_store(store_path, doc)            # auto-save: durable + survives `rm -rf out/`
    return doc
