#!/usr/bin/env bash
# Install Monday 11:00 local-time launchd job for weekly refresh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="$ROOT/scripts/com.bolt.new-cities-launch-tracker-refresh.plist"
PLIST_DST="${HOME}/Library/LaunchAgents/com.bolt.new-cities-launch-tracker-refresh.plist"
BIN_DIR="${HOME}/bin"
LAUNCHER="${BIN_DIR}/new-cities-launch-tracker-refresh"

mkdir -p "$BIN_DIR"
chmod +x "$ROOT/scripts/refresh_and_push.sh"

# Launcher lives outside ~/Downloads — macOS blocks launchd from executing scripts in Downloads.
sed "s|__REPO_ROOT__|$ROOT|g" "$ROOT/scripts/launchd_wrapper.sh" > "$LAUNCHER"
chmod +x "$LAUNCHER"

sed -e "s|__LAUNCHER__|$LAUNCHER|g" -e "s|__HOME__|$HOME|g" "$PLIST_SRC" > "$PLIST_DST"

launchctl bootout "gui/$(id -u)" "$PLIST_DST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
launchctl enable "gui/$(id -u)/com.bolt.new-cities-launch-tracker-refresh"

echo "Installed: $PLIST_DST"
echo "Launcher:  $LAUNCHER"
echo "Runs every Monday at 11:00 (your Mac local timezone — set to Europe/Prague)."
echo "Logs: ~/Library/Logs/new-cities-launch-tracker-refresh.log"
echo ""
echo "If Monday runs fail with 'Operation not permitted', either:"
echo "  • Move repo out of ~/Downloads (e.g. ~/Projects/cz_city_v2_dashboard), re-run this script"
echo "  • Or grant Full Disk Access to /bin/bash in System Settings → Privacy & Security"
echo ""
echo "Test now: bash $ROOT/scripts/refresh_and_push.sh"
