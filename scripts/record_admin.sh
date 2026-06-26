#!/usr/bin/env bash
# Reset the demo org to a known state, then record an admin scenario — so mutating admin
# flows (approve / create / moderate) are reproducible run to run.
#
#   bash scripts/record_admin.sh <scenario> <lang> [--no-seed]
#   bash scripts/record_admin.sh admin-communications en
#   bash scripts/record_admin.sh admin-applications bg
#
# DATABASE_URL: the platform DB the seed is applied to. Defaults to the value in
# ../Tourism_API/.env if not set in the environment. Read-only/analytics admin scenarios
# don't mutate data — pass --no-seed to skip the reset for those.
set -euo pipefail

SCENARIO="${1:?usage: record_admin.sh <scenario> <lang> [--no-seed]}"
LANG_ARG="${2:?usage: record_admin.sh <scenario> <lang> [--no-seed]}"
NO_SEED="${3:-}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SEED_SQL="${ROOT}/scripts/seed_demo_admin_data.sql"

if [ "${NO_SEED}" != "--no-seed" ]; then
  DSN="${DATABASE_URL:-}"
  if [ -z "${DSN}" ] && [ -f "${ROOT}/../Tourism_API/.env" ]; then
    DSN="$(grep -E '^DATABASE_URL=' "${ROOT}/../Tourism_API/.env" | cut -d= -f2- | tr -d '"'"'"' ')"
  fi
  [ -n "${DSN}" ] || { echo "ERROR: DATABASE_URL not set and not found in ../Tourism_API/.env" >&2; exit 1; }
  echo "[record_admin] reset+seed demo org -> known state"
  psql "${DSN}" -v ON_ERROR_STOP=1 -f "${SEED_SQL}" >/dev/null
fi

echo "[record_admin] recording ${SCENARIO} (${LANG_ARG})"
cd "${ROOT}"
python run.py --scenario "${SCENARIO}" --lang "${LANG_ARG}"
