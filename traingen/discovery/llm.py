"""Pluggable LLM client for Layer 2 synthesis. Default backend: Anthropic Claude
(claude-opus-4-8). Tests inject a stub backend so the synthesis plumbing — grouping,
schema, validation, caching, assembly — runs offline with no API key.

Per the current Claude API (claude-api skill): Opus 4.8 removes `temperature`/`top_p`
(they 400). Determinism is approached via low/medium `effort` + the prompt's self-check;
reliable structure comes from `output_config.format` (a JSON schema) rather than asking
for raw YAML and parsing it. The SYNTHESIZER.md "temperature 0" predates that API change.
"""
from __future__ import annotations

import json


class AnthropicBackend:
    def __init__(self, model: str = "claude-opus-4-8", effort: str = "medium"):
        self.model = model
        self.effort = effort
        self._client = None

    def _client_(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY
        return self._client

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        resp = self._client_().messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={
                "format": {"type": "json_schema", "schema": schema},
                "effort": self.effort,
            },
        )
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text)


def get_backend(cfg) -> AnthropicBackend:
    return AnthropicBackend(model=getattr(cfg, "synth_model", "claude-opus-4-8"),
                            effort=getattr(cfg, "synth_effort", "medium"))
