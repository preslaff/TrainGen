"""Discovery configuration — namespaced separately from the production Config
(DESIGN.md R5). Sourced from a `discovery:` block under the manifest `defaults:`,
with environment overrides for the two values that change per run."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .. import config as prod_config
from .resource import DEFAULT_SCOPE_SEGMENTS

EXTRACTOR_VERSION = "0.1.0"
SYNTHESIZER_VERSION = "0.1.0"

# Heuristic prefix -> role mapping (DESIGN.md R5 / FEATURE_INVENTORY §4.3 role_gate).
# Parsing middleware.ts directly is a later refinement; this is the first-cut stand-in.
DEFAULT_ROLE_GATES = [{"prefix": "/admin", "role": "admin"},
                      {"prefix": "/member", "role": "member"}]

# i18n locale segments (e.g. next-intl `[locale]`): treated as routing prefixes, not
# records — stripped from the route URL and excluded from dynamic_params / seed detection.
DEFAULT_LOCALE_PARAMS = ["locale", "lang", "locale?"]


@dataclass
class DiscoveryConfig:
    spec_url: str | None = None          # OpenAPI spec URL or local path
    frontend_app_dir: str | None = None  # path to the Next.js app/ directory
    frontend_repo: str | None = None
    frontend_commit: str | None = None
    api_commit: str | None = None
    ga4_property: str | None = None
    ga4_window_days: int = 30
    role_gates: list = field(default_factory=lambda: list(DEFAULT_ROLE_GATES))
    locale_params: list = field(default_factory=lambda: list(DEFAULT_LOCALE_PARAMS))
    scope_segments: list = field(default_factory=lambda: list(DEFAULT_SCOPE_SEGMENTS))
    extractor_version: str = EXTRACTOR_VERSION
    # Layer 2 (synthesize)
    synth_model: str = "claude-opus-4-8"
    synth_effort: str = "medium"
    synth_max_retries: int = 2
    synthesizer_version: str = SYNTHESIZER_VERSION
    # Layer 3 (verify)
    verify_max_steps: int = 12          # per-scenario crawl ceiling (the cage)


def load_discovery_config(path=prod_config.MANIFEST) -> DiscoveryConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    d = ((data.get("defaults") or {}).get("discovery") or {})
    api = d.get("api") or {}
    fe = d.get("frontend") or {}
    ga4 = d.get("ga4") or {}
    return DiscoveryConfig(
        spec_url=os.environ.get("TRAINGEN_OPENAPI_URL", api.get("spec_url")),
        frontend_app_dir=os.environ.get("TRAINGEN_FRONTEND_APP", fe.get("app_dir")),
        frontend_repo=fe.get("repo"),
        frontend_commit=fe.get("commit"),
        api_commit=api.get("commit"),
        ga4_property=ga4.get("property"),
        ga4_window_days=int(ga4.get("window_days", 30)),
        role_gates=d.get("role_gates") or list(DEFAULT_ROLE_GATES),
        locale_params=d.get("locale_params") or list(DEFAULT_LOCALE_PARAMS),
        scope_segments=d.get("scope_segments") or list(DEFAULT_SCOPE_SEGMENTS),
        synth_model=os.environ.get("TRAINGEN_SYNTH_MODEL", d.get("synth_model", "claude-opus-4-8")),
        synth_effort=os.environ.get("TRAINGEN_SYNTH_EFFORT", d.get("synth_effort", "medium")),
    )
