#!/usr/bin/env bash
# Build Standing.app (Swift shell + optional embedded Python payload).
# Does not launch the app — use scripts/run-native.sh for local iterate.
#
# Usage:
#   ./scripts/package-app.sh              # dev: points at repo .venv
#   ./scripts/package-app.sh --release    # ship: embeds src + venv in Resources
#
# Env:
#   STANDING_APP_VERSION / STANDING_APP_BUILD
#   STANDING_SPARKLE_FEED_URL / STANDING_SPARKLE_PUBLIC_ED_KEY
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODE="dev"
for arg in "$@"; do
  case "$arg" in
    --release) MODE="release" ;;
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

if [[ ! -x "$ROOT/.venv/bin/python3" ]]; then
  echo "Missing .venv — run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

NATIVE="$ROOT/native/Standing"
APP="$NATIVE/Standing.app"
BIN_DIR="$NATIVE/.build/arm64-apple-macosx/release"
if [[ ! -d "$BIN_DIR" ]]; then
  BIN_DIR="$NATIVE/.build/x86_64-apple-macosx/release"
fi

APP_VERSION="${STANDING_APP_VERSION:-0.1.0}"
APP_BUILD="${STANDING_APP_BUILD:-1}"
SPARKLE_FEED_URL="${STANDING_SPARKLE_FEED_URL:-}"
SPARKLE_PUBLIC_ED_KEY="${STANDING_SPARKLE_PUBLIC_ED_KEY:-}"

echo "Building Standing (release, version $APP_VERSION build $APP_BUILD, mode=$MODE)…" >&2
# Keep stdout clean: callers capture the final app path only.
(
  cd "$NATIVE"
  swift build -c release
) >&2

if [[ ! -x "$BIN_DIR/Standing" ]]; then
  BIN_DIR="$(echo "$NATIVE"/.build/*-apple-macosx/release)"
fi
if [[ ! -x "$BIN_DIR/Standing" ]]; then
  echo "Could not find built Standing binary under $NATIVE/.build" >&2
  exit 1
fi

echo "Packaging Standing.app…" >&2
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" "$APP/Contents/Frameworks"
cp "$BIN_DIR/Standing" "$APP/Contents/MacOS/Standing"
chmod +x "$APP/Contents/MacOS/Standing"

# App icon (notifications, Finder, Dock) — built from the web brand mark.
ICON_SRC="$ROOT/web/icons/icon-512.png"
ICON_ICNS="$APP/Contents/Resources/AppIcon.icns"
if [[ -f "$ICON_SRC" ]]; then
  echo "Building AppIcon.icns…" >&2
  if sips -s format icns "$ICON_SRC" --out "$ICON_ICNS" >/dev/null; then
    echo "App icon: $ICON_ICNS" >&2
  else
    echo "Warning: could not build AppIcon.icns — notifications will show the placeholder icon." >&2
  fi
else
  echo "Warning: missing $ICON_SRC — packaging without AppIcon.icns." >&2
fi

# Embed Sparkle.framework from the SwiftPM build.
SPARKLE_FW=""
for candidate in \
  "$NATIVE"/.build/artifacts/sparkle/Sparkle/Sparkle.xcframework/macos-arm64_x86_64/Sparkle.framework \
  "$NATIVE"/.build/artifacts/*/*/Sparkle.xcframework/macos-arm64_x86_64/Sparkle.framework \
  "$NATIVE"/.build/checkouts/Sparkle/Sparkle.xcframework/macos-arm64_x86_64/Sparkle.framework
do
  if [[ -d "$candidate" ]]; then
    SPARKLE_FW="$candidate"
    break
  fi
done
if [[ -z "$SPARKLE_FW" ]]; then
  SPARKLE_FW="$(find "$NATIVE/.build" -path '*/macos-arm64_x86_64/Sparkle.framework' -type d 2>/dev/null | head -1 || true)"
fi
if [[ -n "$SPARKLE_FW" && -d "$SPARKLE_FW" ]]; then
  echo "Embedding Sparkle.framework…" >&2
  cp -R "$SPARKLE_FW" "$APP/Contents/Frameworks/"
  install_name_tool -add_rpath @executable_path/../Frameworks "$APP/Contents/MacOS/Standing" 2>/dev/null || true
else
  echo "Warning: Sparkle.framework not found under $NATIVE/.build — updates UI needs a rebuild with network." >&2
fi

SPARKLE_PLIST_KEYS=""
if [[ -n "$SPARKLE_FEED_URL" && -n "$SPARKLE_PUBLIC_ED_KEY" ]]; then
  SPARKLE_PLIST_KEYS=$(cat <<EOF
	<key>SUFeedURL</key>
	<string>${SPARKLE_FEED_URL}</string>
	<key>SUPublicEDKey</key>
	<string>${SPARKLE_PUBLIC_ED_KEY}</string>
	<key>SUEnableAutomaticChecks</key>
	<true/>
EOF
)
  echo "Sparkle feed: $SPARKLE_FEED_URL" >&2
fi

# Dev builds bake absolute repo paths. Release builds omit them so the app
# resolves StandingPayload inside Resources (see PythonBridge.resolveRepoRoot).
LS_ENVIRONMENT=""
if [[ "$MODE" == "dev" ]]; then
  LS_ENVIRONMENT=$(cat <<EOF
	<key>LSEnvironment</key>
	<dict>
		<key>STANDING_ROOT</key>
		<string>${ROOT}</string>
		<key>STANDING_PYTHON</key>
		<string>${ROOT}/.venv/bin/python3</string>
		<key>PYTHONUNBUFFERED</key>
		<string>1</string>
	</dict>
EOF
)
else
  PAYLOAD="$APP/Contents/Resources/StandingPayload"
  echo "Embedding Python payload into Standing.app…" >&2
  mkdir -p "$PAYLOAD"
  # Copy source + deps list only — never .env, stats, calibration images, or logs.
  rsync -a \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    "$ROOT/src" "$PAYLOAD/"
  cp "$ROOT/requirements.txt" "$PAYLOAD/requirements.txt"
  if [[ -f "$ROOT/.env.example" ]]; then
    cp "$ROOT/.env.example" "$PAYLOAD/.env.example"
  fi
  mkdir -p "$PAYLOAD/data" "$PAYLOAD/assets"
  if [[ -d "$ROOT/assets/icons" ]]; then
    rsync -a "$ROOT/assets/icons" "$PAYLOAD/assets/"
  fi

  echo "Creating embedded .venv (this can take a few minutes)…" >&2
  python3 -m venv "$PAYLOAD/.venv"
  "$PAYLOAD/.venv/bin/pip" install --upgrade pip >&2
  "$PAYLOAD/.venv/bin/pip" install -r "$PAYLOAD/requirements.txt" >&2

  LS_ENVIRONMENT=$(cat <<EOF
	<key>LSEnvironment</key>
	<dict>
		<key>PYTHONUNBUFFERED</key>
		<string>1</string>
	</dict>
EOF
)
fi

cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key>
	<string>en</string>
	<key>CFBundleExecutable</key>
	<string>Standing</string>
	<key>CFBundleIdentifier</key>
	<string>ai.standing.mac</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundleName</key>
	<string>Standing</string>
	<key>CFBundleIconFile</key>
	<string>AppIcon</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleShortVersionString</key>
	<string>${APP_VERSION}</string>
	<key>CFBundleVersion</key>
	<string>${APP_BUILD}</string>
	<key>LSMinimumSystemVersion</key>
	<string>14.0</string>
	<key>LSUIElement</key>
	<true/>
	<key>NSHighResolutionCapable</key>
	<true/>
	<key>NSCameraUsageDescription</key>
	<string>Standing uses the camera to check whether you are sitting or standing at your desk.</string>
${SPARKLE_PLIST_KEYS}
${LS_ENVIRONMENT}
</dict>
</plist>
EOF

# Ad-hoc sign for local runs (camera + hardened-runtime relaxations).
ENTITLEMENTS="$NATIVE/Standing.entitlements"
if [[ -f "$ENTITLEMENTS" ]]; then
  echo "Ad-hoc codesign…" >&2
  codesign --force --deep --sign - --entitlements "$ENTITLEMENTS" "$APP" 2>/dev/null \
    || echo "Warning: codesign failed — camera / embedded libs may be limited." >&2
fi

echo "Standing.app ready: $APP" >&2
echo "$APP"
