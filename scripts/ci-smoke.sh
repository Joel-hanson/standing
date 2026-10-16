#!/usr/bin/env bash
# macOS smoke checks for Standing (CI + local).
# Verifies: Python imports, Swift shell, Standing.app layout, optional DMG wrap.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Python imports"
PYTHON="${STANDING_PYTHON:-$ROOT/.venv/bin/python3}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi
"$PYTHON" - <<'PY'
import importlib

mods = [
    "src.core",
    "src.worker",
    "src.tracker",
    "src.motion",
    "src.jev_client",
    "src.credentials",
    "src.paths",
]
for name in mods:
    importlib.import_module(name)
    print(f"  ok {name}")
print("imports ok")
PY

echo "==> Package Standing.app (dev)"
export STANDING_APP_VERSION="${STANDING_APP_VERSION:-0.0.0-ci}"
export STANDING_APP_BUILD="${STANDING_APP_BUILD:-0}"
APP="$("$ROOT/scripts/package-app.sh" | tail -n1)"

echo "==> Verify app bundle"
test -x "$APP/Contents/MacOS/Standing"
test -f "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$APP/Contents/Info.plist" | grep -q 'ai.standing.mac'
/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist"
if [[ -d "$APP/Contents/Frameworks/Sparkle.framework" ]]; then
  echo "  Sparkle.framework present"
else
  echo "  warning: Sparkle.framework missing" >&2
fi
echo "  app ok: $APP"

# Optional: also build a release payload and prove embedded Python is relocatable.
# Skip with STANDING_SKIP_RELEASE_SMOKE=1 (faster local loops).
if [[ "${STANDING_SKIP_RELEASE_SMOKE:-0}" != "1" && "${STANDING_CI_RELEASE_SMOKE:-0}" == "1" ]]; then
  echo "==> Package Standing.app (release smoke)"
  HOST_ARCH="$(uname -m)"
  export STANDING_SHIP_ARCH="${STANDING_SHIP_ARCH:-$HOST_ARCH}"
  REL_APP="$("$ROOT/scripts/package-app.sh" --release | tail -n1)"
  "$ROOT/scripts/verify-release-payload.sh" "$REL_APP" "$STANDING_SHIP_ARCH"
fi

echo "==> Wrap DMG (from existing app)"
export STANDING_DMG_PATH="${STANDING_DMG_PATH:-$ROOT/dist/Standing-ci.dmg}"
DMG="$("$ROOT/scripts/package-dmg.sh" --skip-build | tail -n1)"
test -f "$DMG"
# Mount read-only and confirm Standing.app is inside.
ATTACH_OUT="$(hdiutil attach -nobrowse -readonly "$DMG")"
MNT="$(echo "$ATTACH_OUT" | awk '/\/Volumes\//{print $NF; exit}')"
test -d "$MNT/Standing.app/Contents/MacOS"
hdiutil detach "$MNT" >/dev/null
echo "  dmg ok: $DMG"

echo "Smoke checks passed."
