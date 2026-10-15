#!/usr/bin/env bash
# Build Standing as a real .app (required for UserNotifications + MenuBarExtra),
# then launch it. Requires: Xcode CLT, repo .venv.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP="$("$ROOT/scripts/package-app.sh")"

# Drop any previous instance so the menu-bar icon refreshes cleanly.
pkill -x Standing 2>/dev/null || true
sleep 0.2

echo "Launching $APP"
open "$APP"
echo "Standing is in the menu bar (near the clock). Quit from the menu."
