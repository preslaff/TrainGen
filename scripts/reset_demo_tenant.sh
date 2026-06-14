#!/usr/bin/env bash
# Reset the seeded demo tenant to a known state before recording (BLUEPRINT §11).
# Training flows mutate data (create partner, capture lead), so each run must start
# from a clean, deterministic snapshot. Never point this at production.
#
# TODO: implement against your platform — e.g. restore a DB snapshot, or run a
# transactional seed script against the staging demo org.
set -euo pipefail
echo "reset_demo_tenant.sh: not implemented — wire this to your staging demo tenant." >&2
exit 1
