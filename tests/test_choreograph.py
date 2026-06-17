"""choreograph pacing test — offline. The `pace` multiplier stretches per-step dwell
without touching audio (compose still pins narration at measured_start).

    python -m tests.test_choreograph
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from traingen import choreograph
from traingen import config as prod_config

prod_config.OUT = Path(tempfile.mkdtemp())

SCENARIO = {"scenario_id": "demo", "steps": [{"id": "a", "settle_ms": 0, "emphasis": "none"}]}
NARRATE = {"lang": "en", "steps": [{"id": "a", "duration": 2.0}]}


def _cfg(pace):
    return prod_config.Config(base_url="", viewport={}, fps=30, cursor_travel_s=0.8,
                              tail_pad_s=0.4, langs=["en"], voices={}, pace=pace)


def test_pace_scales_dwell():
    base = choreograph.run(SCENARIO, NARRATE, _cfg(1.0))["steps"][0]["step_duration"]
    slow = choreograph.run(SCENARIO, NARRATE, _cfg(2.0))["steps"][0]["step_duration"]
    # audio 2.0 > floor(0.8+0.4+0)=1.2 -> (2.0+0.4)=2.4 at pace 1.0; doubled at pace 2.0
    assert abs(base - 2.4) < 1e-6, f"base dwell {base}"
    assert abs(slow - 2 * base) < 1e-6, f"pace=2 should double dwell: {slow} vs {base}"
    print(f"OK  pace: dwell {base}s -> {slow}s at pace 2.0 (audio still pinned at measured_start)")


def main() -> int:
    test_pace_scales_dwell()
    print("\nall choreograph tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
