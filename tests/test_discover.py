"""Discovery orchestrator tests — offline. Monkeypatches the three stage functions to
confirm sequencing, the role filter, and the skip-verify path without running extract,
the LLM, or Playwright.

    python -m tests.test_discover
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from traingen import config as prod_config
from traingen.discovery import discover
from traingen.discovery.config import DiscoveryConfig

# Redirect all OUT-based writes to a throwaway dir so tests never clobber real artifacts
# (discover.run writes feature_inventory.json).
prod_config.OUT = Path(tempfile.mkdtemp())


def test_orchestration_role_filter_and_skip_verify(monkeypatch=None):
    calls = []
    fake_inv = {"meta": {}, "endpoints": [1, 2, 3], "routes": [1, 2]}
    fake_drafts = {"discovery_run": {}, "drafts": [
        {"scenario_id": "a", "role": "admin"},
        {"scenario_id": "m", "role": "member"},
    ]}

    discover.extract.build_inventory = lambda cfg: (calls.append("extract") or fake_inv)
    discover.synthesize.run = lambda inv, cfg=None, backend=None: (calls.append("synth") or
                                                                   {**fake_drafts, "drafts": list(fake_drafts["drafts"])})
    discover.verify.verify = lambda doc, cfg=None, make_driver=None: (calls.append("verify") or doc)

    # also stop the inventory file write from needing a real dir is fine (out/discovery exists)
    summary = discover.run(roles=["admin"], skip_verify=False, cfg=DiscoveryConfig())

    assert calls == ["extract", "synth", "verify"], f"stage order wrong: {calls}"
    assert summary["drafts"] == 1, "role filter kept only the admin draft"
    assert summary["endpoints"] == 3 and summary["routes"] == 2
    assert summary["verified"] is True
    print(f"OK  orchestration: extract→synth→verify; role filter admin -> {summary['drafts']} draft")

    calls.clear()
    summary = discover.run(roles=None, skip_verify=True, cfg=DiscoveryConfig())
    assert calls == ["extract", "synth"], "skip_verify must not run verify"
    assert summary["drafts"] == 2 and summary["verified"] is False
    print("OK  skip-verify: verify stage skipped; all roles kept")


def main() -> int:
    test_orchestration_role_filter_and_skip_verify()
    print("\nall discover tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
