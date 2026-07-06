#!/usr/bin/env bash
# Launcher for launchd — lives in ~/bin (outside Downloads) so macOS TCC allows execution.
REPO_ROOT="__REPO_ROOT__"
exec /bin/bash "$REPO_ROOT/scripts/refresh_and_push.sh"
