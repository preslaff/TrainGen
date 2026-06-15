"""Human-gate merge tests — offline. Verifies the DESIGN §5 drop-list, eligibility
gating, dry-run vs --apply, and that the defaults header/comments survive a write.

    python -m tests.test_merge
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import yaml

from traingen.discovery import merge

VERIFIED_DRAFT = {
    "scenario_id": "add-partner-profile",
    "title": {"bg": "Добавяне", "en": "Adding a partner profile"},
    "role": "admin", "goal": "Create and publish a partner.",
    "entry_route": "/admin/partners",
    "needs_seed_record": False, "destructive": False,
    # draft-only metadata that MUST be dropped at the gate:
    "usage_rank": 9, "provenance": "route+endpoint+crawl",
    "source_refs": {"routes": ["/admin/partners"], "endpoints": ["create_partner"]},
    "open_questions": [], "verification": {"needs_review": False, "confirmed": 2},
    "steps": [
        {"id": "open", "intent": "Open the form", "locator": {"testid": "partners-add-btn"},
         "action": "click", "value": "", "emphasis": "highlight", "settle_ms": 800,
         "provenance": "route+crawl", "bound_via": "testid", "verified": {"status": "confirmed"}},
        {"id": "name", "intent": "Enter the name", "locator": {"testid": "partner-business-name"},
         "action": "fill", "value": "Хотел", "emphasis": "zoom", "settle_ms": 400,
         "provenance": "route+endpoint+crawl", "bound_via": "testid"},
    ],
}


def test_to_ssot_strips_metadata():
    s = merge.to_ssot(VERIFIED_DRAFT)
    assert set(s) == {"scenario_id", "title", "role", "goal", "entry_route",
                      "needs_seed_record", "destructive", "steps"}
    assert "provenance" not in s and "usage_rank" not in s and "verification" not in s
    st0, st1 = s["steps"]
    assert set(st0) == {"id", "intent", "locator", "action", "emphasis", "settle_ms"}  # empty value dropped
    assert st1["value"] == "Хотел"
    assert "provenance" not in st0 and "bound_via" not in st0 and "verified" not in st0
    print("OK  to_ssot: dropped draft-only fields; kept lean SSOT schema + needs_seed_record")


def test_eligibility():
    ok, _ = merge.eligibility(VERIFIED_DRAFT)
    assert ok

    flagged = {**VERIFIED_DRAFT, "verification": {"needs_review": True}}
    ok, reasons = merge.eligibility(flagged)
    assert not ok and "needs_review" in reasons
    assert merge.eligibility(flagged, include_unverified=True)[0]   # override

    dropcand = {**VERIFIED_DRAFT, "verification": {"needs_review": False},
                "steps": [{**VERIFIED_DRAFT["steps"][0], "drop_candidate": True}]}
    ok, reasons = merge.eligibility(dropcand)
    assert not ok and any("drop_candidate" in r for r in reasons)
    print("OK  eligibility: clean passes; needs_review/drop_candidate blocked (overridable)")


def _temp_manifest() -> Path:
    text = (
        "# TrainGen SSOT — KEEP THIS COMMENT\n"
        "defaults:\n"
        "  base_url: \"https://staging.example.com\"   # demo tenant, NOT prod\n"
        "  langs: [bg, en]\n\n"
        "scenarios:\n"
        "  - scenario_id: old-one\n"
        "    title: { bg: x, en: x }\n"
        "    role: member\n"
        "    goal: keep me\n"
        "    entry_route: /dashboard\n"
        "    steps:\n"
        "      - { id: s, intent: i, locator: { testid: t }, action: click, emphasis: none, settle_ms: 0 }\n"
    )
    f = Path(tempfile.mkdtemp()) / "scenarios.yaml"
    f.write_text(text, encoding="utf-8")
    return f


def test_dry_run_does_not_write():
    mf = _temp_manifest()
    before = mf.read_text()
    summary = merge.merge({"drafts": [VERIFIED_DRAFT]}, manifest_path=mf, scenario_ids=None, apply=False)
    assert summary["added"] == ["add-partner-profile"] and summary["applied"] is False
    assert mf.read_text() == before, "dry-run must not modify the manifest"
    print("OK  dry-run: reports add, writes nothing")


def test_apply_writes_and_preserves_header():
    mf = _temp_manifest()
    summary = merge.merge({"drafts": [VERIFIED_DRAFT]}, manifest_path=mf, scenario_ids=None, apply=True)
    assert summary["applied"] is True and summary["added"] == ["add-partner-profile"]

    text = mf.read_text()
    assert "KEEP THIS COMMENT" in text and "NOT prod" in text, "defaults header/comments preserved"
    data = yaml.safe_load(text)
    ids = {s["scenario_id"] for s in data["scenarios"]}
    assert ids == {"old-one", "add-partner-profile"}, "existing kept + new appended"
    new = next(s for s in data["scenarios"] if s["scenario_id"] == "add-partner-profile")
    assert "provenance" not in new, "merged scenario is stripped to SSOT schema"
    assert data["defaults"]["base_url"] == "https://staging.example.com"
    print("OK  apply: SSOT written, defaults comments preserved, scenario upserted + stripped")


def main() -> int:
    test_to_ssot_strips_metadata()
    test_eligibility()
    test_dry_run_does_not_write()
    test_apply_writes_and_preserves_header()
    print("\nall merge tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
