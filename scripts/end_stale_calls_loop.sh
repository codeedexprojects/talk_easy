#!/usr/bin/env bash
# Launches `manage.py end_stale_calls --loop` once, as a single long-lived
# process (Django/Firebase boot cost paid only once, not per cycle). The
# loop itself, sleep interval, and failure-escalation logic all live in the
# management command — this script only wires up the environment and PM2.
#
# Usage (one-time, on the server):
#   pm2 start scripts/end_stale_calls_loop.sh --name end-stale-calls-loop
#   pm2 save
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-5}"

cd "$APP_DIR"
source venv/bin/activate
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-talkeasy.settings.production}"

exec python manage.py end_stale_calls --loop --interval "$POLL_INTERVAL_SECONDS"
