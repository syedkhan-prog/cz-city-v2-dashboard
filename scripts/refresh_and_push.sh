#!/usr/bin/env bash
# Pull Databricks data locally, rebuild HTML, push to GitHub (Boltable deploys via Actions).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${HOME}/Library/Logs"
LOG_FILE="${LOG_DIR}/new-cities-launch-tracker-refresh.log"
LOCK_FILE="/tmp/new-cities-launch-tracker-refresh.lock"

mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $*"; }

if ! mkdir "$LOCK_FILE" 2>/dev/null; then
  log "SKIP: refresh already running (lock $LOCK_FILE)"
  exit 0
fi
trap 'rmdir "$LOCK_FILE" 2>/dev/null || true' EXIT

log "=== refresh start ==="
log "repo: $ROOT"

cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  log "ERROR: python3 not found"
  exit 1
fi

if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

log "git pull --rebase --autostash origin main"
git pull --rebase --autostash origin main

log "fetch.py"
python3 fetch.py

log "build.py"
python3 build.py --no-local

GENERATED_AT="$(python3 -c "import json; print(json.load(open('data.json'))['meta']['generated_at'])")"
log "generated_at=$GENERATED_AT"

git add data.json docs/index.html boltable/index.html
if git diff --staged --quiet; then
  log "No data changes — skipping commit"
else
  MSG="auto-refresh data $(date -u +'%Y-%m-%d %H:%M UTC')"
  git commit -m "$MSG"
  log "git push origin main"
  git push origin main
  log "Pushed — deploy-boltable.yml will mirror to Boltable"
fi

log "=== refresh done ==="
