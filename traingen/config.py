"""Config + manifest access. Defaults come from the manifest `defaults:` block;
environment variables override the few things that change per machine/run."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifest" / "scenarios.yaml"
OUT = ROOT / "out"


@dataclass
class Config:
    base_url: str
    viewport: dict
    fps: int
    cursor_travel_s: float
    tail_pad_s: float
    langs: list
    voices: dict
    rec_start_pad_s: float = 0.5
    headless: bool = False
    tts_backend: str = "offline"   # "offline" (espeak-ng) | "omnivoice"
    login: dict | None = None      # optional auth block (see record.login)


def _manifest(path=MANIFEST) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def load_config(path=MANIFEST) -> Config:
    d = _manifest(path).get("defaults", {})
    return Config(
        base_url=os.environ.get("TRAINGEN_BASE_URL", d.get("base_url", "")),
        viewport=d.get("viewport", {"width": 1920, "height": 1080}),
        fps=int(d.get("fps", 30)),
        cursor_travel_s=float(d.get("cursor_travel_s", 0.8)),
        tail_pad_s=float(d.get("tail_pad_s", 0.4)),
        langs=d.get("langs", ["bg"]),
        voices=d.get("voices", {}),
        headless=os.environ.get("TRAINGEN_HEADLESS", "0") == "1",
        tts_backend=os.environ.get("TRAINGEN_TTS", "offline"),
        login=d.get("login"),
    )


def load_scenarios(path=MANIFEST) -> list:
    return _manifest(path)["scenarios"]


def get_scenario(scenario_id: str, path=MANIFEST) -> dict:
    for s in load_scenarios(path):
        if s["scenario_id"] == scenario_id:
            return s
    raise KeyError(f"scenario '{scenario_id}' not found in {path}")


def lang_dir(scenario_id: str, lang: str) -> Path:
    p = OUT / scenario_id / lang
    p.mkdir(parents=True, exist_ok=True)
    return p
