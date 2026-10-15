#!/usr/bin/env bash
# Wrap Standing.app into a distributable DMG.
#
# Usage:
#   ./scripts/package-dmg.sh                 # builds release app first
#   ./scripts/package-dmg.sh --skip-build    # use existing Standing.app
#
# Env:
#   STANDING_APP_VERSION / STANDING_APP_BUILD (passed through to package-app)
#   STANDING_DMG_PATH   optional output path (default: dist/Standing-<version>.dmg)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SKIP_BUILD=0
for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

APP_VERSION="${STANDING_APP_VERSION:-0.1.0}"
APP="$ROOT/native/Standing/Standing.app"
DIST="$ROOT/dist"
DMG_PATH="${STANDING_DMG_PATH:-$DIST/Standing-${APP_VERSION}.dmg}"
STAGE="$DIST/dmg-stage"

if [[ "$SKIP_BUILD" -eq 0 ]]; then
  # package-app prints the .app path on stdout — keep our stdout clean for callers.
  "$ROOT/scripts/package-app.sh" --release >/dev/null
fi

if [[ ! -d "$APP" ]]; then
  echo "Missing Standing.app at $APP — run scripts/package-app.sh --release first." >&2
  exit 1
fi

mkdir -p "$DIST"
rm -rf "$STAGE" "$DMG_PATH"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/Standing.app"
ln -s /Applications "$STAGE/Applications"

echo "Creating ${DMG_PATH}..." >&2
# hdiutil also prints to stdout; redirect so only the DMG path is emitted below.
hdiutil create \
  -volname "Standing" \
  -srcfolder "$STAGE" \
  -ov \
  -format UDZO \
  "$DMG_PATH" >&2

rm -rf "$STAGE"
echo "DMG ready: ${DMG_PATH}" >&2
echo "$DMG_PATH"
