#!/usr/bin/env bash
# Install Monday 11:00 local-time launchd job for weekly refresh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="$ROOT/scripts/com.bolt.new-cities-launch-tracker-refresh.plist"
PLIST_DST="${HOME}/Library/LaunchAgents/com.bolt.new-cities-launch-tracker-refresh.plist"
SCRIPT="$ROOT/scripts/refresh_and_push.sh"

chmod +x "$SCRIPT"

# Substitute repo path into plist
sed -e "s|__REPO_ROOT__|$ROOT|g" -e "s|__HOME__|$HOME|g" "$PLIST_SRC" > "$PLIST_DST"

launchctl bootout "gui/$(id -u)" "$PLIST_DST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
launchctl enable "gui/$(id -u)/com.bolt.new-cities-launch-tracker-refresh"
launchctl kickstart -k "gui/$(id -u)/com.bolt.new-cities-launch-tracker-refresh" 2>/dev/null || true

echo "Installed: $PLIST_DST"
echo "Runs every Monday at 11:00 (your Mac local timezone — set to Europe/Prague)."
echo "Logs: ~/Library/Logs/new-cities-launch-tracker-refresh.log"
echo ""
echo "Test now: bash $SCRIPT"
