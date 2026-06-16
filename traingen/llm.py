"""Shared Claude client (per the claude-api skill). Opus 4.8 removes temperature/top_p —
control behaviour with `effort`. `complete_json` forces structured output via
output_config.format; `complete_text` returns plain text. Used by discovery (synthesize,
verify matcher) and production (script narration).
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
            model=self.model, max_tokens=16000, system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema},
                           "effort": self.effort})
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text)

    def complete_text(self, system: str, user: str) -> str:
        resp = self._client_().messages.create(
            model=self.model, max_tokens=4000, system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.effort})
        return "".join(b.text for b in resp.content if b.type == "text").strip()
