"""Discovery's view of the shared Claude client. The backend itself lives in
`traingen/llm.py` (shared with production script narration); this module just selects
model/effort from the discovery config.

Per the claude-api skill: Opus 4.8 removes `temperature`; determinism is approached via
`effort` + the prompt's self-check, and reliable structure via output_config.format. The
SYNTHESIZER.md "temperature 0" predates that API change.
"""
from __future__ import annotations

from ..llm import AnthropicBackend


def get_backend(cfg) -> AnthropicBackend:
    return AnthropicBackend(model=getattr(cfg, "synth_model", "claude-opus-4-8"),
                            effort=getattr(cfg, "synth_effort", "medium"))
