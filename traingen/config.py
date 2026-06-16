"""Config + manifest access. Defaults come from the manifest `defaults:` block;
environment variables override the few things that change per machine/run."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import env as _env  # noqa: F401  (side effect: load repo-root .env into os.environ)

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
    browser_args: list = field(default_factory=list)   # Chromium launch flags (e.g. --disable-gpu)
    tts_backend: str = "offline"   # "offline" (espeak-ng) | "omnivoice"
    login: dict | None = None      # optional auth block (see record.login)
    dismiss: list = field(default_factory=list)   # pre-roll overlays to close (cookie banner, etc.)
    subtitles: str = "per_step"    # "per_step" | "aeneas"
    # script narration LLM (falls back to echo when no key)
    script_backend: str = "anthropic"   # "anthropic" | "echo"
    script_model: str = "claude-opus-4-8"
    script_effort: str = "low"


def _manifest(path=MANIFEST) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _env_or(d, manifest_key, env_key, default):
    """Precedence: TRAINGEN_* env (incl. .env) > manifest defaults > hardcoded default."""
    v = os.environ.get(env_key)
    return v if v is not None else d.get(manifest_key, default)


def _browser_args(d) -> list:
    v = os.environ.get("TRAINGEN_BROWSER_ARGS")        # comma-separated, e.g. "--disable-gpu,--disable-dev-shm-usage"
    if v is not None:
        return [a.strip() for a in v.split(",") if a.strip()]
    return d.get("browser_args", [])


def _viewport(d) -> dict:
    vp = os.environ.get("TRAINGEN_VIEWPORT")          # "1920x1080"
    if vp and "x" in vp.lower():
        w, h = vp.lower().split("x", 1)
        return {"width": int(w), "height": int(h)}
    return d.get("viewport", {"width": 1920, "height": 1080})


def load_config(path=MANIFEST) -> Config:
    d = _manifest(path).get("defaults", {})
    langs = _env_or(d, "langs", "TRAINGEN_LANGS", ["bg"])
    if isinstance(langs, str):
        langs = [x.strip() for x in langs.split(",") if x.strip()]
    return Config(
        base_url=_env_or(d, "base_url", "TRAINGEN_BASE_URL", ""),
        viewport=_viewport(d),
        fps=int(_env_or(d, "fps", "TRAINGEN_FPS", 30)),
        cursor_travel_s=float(_env_or(d, "cursor_travel_s", "TRAINGEN_CURSOR_TRAVEL_S", 0.8)),
        tail_pad_s=float(_env_or(d, "tail_pad_s", "TRAINGEN_TAIL_PAD_S", 0.4)),
        langs=langs,
        voices=d.get("voices", {}),
        rec_start_pad_s=float(_env_or(d, "rec_start_pad_s", "TRAINGEN_REC_START_PAD_S", 0.5)),
        headless=str(_env_or(d, "headless", "TRAINGEN_HEADLESS", "0")).lower() in ("1", "true", "yes"),
        browser_args=_browser_args(d),
        tts_backend=_env_or(d, "tts_backend", "TRAINGEN_TTS", "offline"),
        login=d.get("login"),
        dismiss=d.get("dismiss", []),
        subtitles=_env_or(d, "subtitles", "TRAINGEN_SUBTITLES", "per_step"),
        script_backend=_env_or(d, "script_backend", "TRAINGEN_SCRIPT_BACKEND", "anthropic"),
        script_model=_env_or(d, "script_model", "TRAINGEN_SCRIPT_MODEL", "claude-opus-4-8"),
        script_effort=_env_or(d, "script_effort", "TRAINGEN_SCRIPT_EFFORT", "low"),
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
