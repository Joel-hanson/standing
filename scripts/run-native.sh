#!/usr/bin/env bash
# Build Standing as a real .app (required for UserNotifications + MenuBarExtra),
# then launch it. Requires: Xcode CLT, repo .venv.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/.venv/bin/python3" ]]; then
  echo "Missing .venv — run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

NATIVE="$ROOT/native/Standing"
APP="$NATIVE/Standing.app"
BIN_DIR="$NATIVE/.build/arm64-apple-macosx/release"
# Intel Macs use x86_64 in the path; prefer whatever exists.
if [[ ! -d "$BIN_DIR" ]]; then
  BIN_DIR="$NATIVE/.build/x86_64-apple-macosx/release"
fi

APP_VERSION="${STANDING_APP_VERSION:-0.1.0}"
APP_BUILD="${STANDING_APP_BUILD:-1}"
# Optional Sparkle feed — leave unset for local/dev builds (Check for Updates stays hidden).
SPARKLE_FEED_URL="${STANDING_SPARKLE_FEED_URL:-}"
SPARKLE_PUBLIC_ED_KEY="${STANDING_SPARKLE_PUBLIC_ED_KEY:-}"

echo "Building Standing (release)…"
(
  cd "$NATIVE"
  swift build -c release
)

# Re-resolve after build (swift may create the arch folder on first build).
if [[ ! -x "$BIN_DIR/Standing" ]]; then
  BIN_DIR="$(echo "$NATIVE"/.build/*-apple-macosx/release)"
fi
if [[ ! -x "$BIN_DIR/Standing" ]]; then
  echo "Could not find built Standing binary under $NATIVE/.build" >&2
  exit 1
fi

echo "Packaging Standing.app…"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" "$APP/Contents/Frameworks"
cp "$BIN_DIR/Standing" "$APP/Contents/MacOS/Standing"
chmod +x "$APP/Contents/MacOS/Standing"

# Embed Sparkle.framework from the SwiftPM build (binary artifact or checkouts).
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
# Fallback: any Sparkle.framework under .build
if [[ -z "$SPARKLE_FW" ]]; then
  SPARKLE_FW="$(find "$NATIVE/.build" -path '*/macos-arm64_x86_64/Sparkle.framework' -type d 2>/dev/null | head -1 || true)"
fi
if [[ -n "$SPARKLE_FW" && -d "$SPARKLE_FW" ]]; then
  echo "Embedding Sparkle.framework…"
  cp -R "$SPARKLE_FW" "$APP/Contents/Frameworks/"
  # Ensure the binary can find the embedded framework when launched as an .app.
  install_name_tool -add_rpath @executable_path/../Frameworks "$APP/Contents/MacOS/Standing" 2>/dev/null || true
else
  echo "Warning: Sparkle.framework not found under $NATIVE/.build — updates UI needs a rebuild with network." >&2
fi

# Optional Sparkle Info.plist keys (only when both are set).
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
  echo "Sparkle feed: $SPARKLE_FEED_URL"
fi

# Bake repo paths so the app finds the Python worker when opened from Finder/Dock.
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
	<key>LSEnvironment</key>
	<dict>
		<key>STANDING_ROOT</key>
		<string>${ROOT}</string>
		<key>STANDING_PYTHON</key>
		<string>${ROOT}/.venv/bin/python3</string>
		<key>PYTHONUNBUFFERED</key>
		<string>1</string>
	</dict>
</dict>
</plist>
EOF

# Drop any previous instance so the menu-bar icon refreshes cleanly.
pkill -x Standing 2>/dev/null || true
sleep 0.2

echo "Launching $APP"
open "$APP"
echo "Standing is in the menu bar (near the clock). Quit from the menu."
