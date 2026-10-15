#!/usr/bin/env bash
# Build Standing.app (Swift shell + optional embedded Python payload).
# Does not launch the app — use scripts/run-native.sh for local iterate.
#
# Usage:
#   ./scripts/package-app.sh              # dev: points at repo .venv
#   ./scripts/package-app.sh --release    # ship: embeds src + relocatable CPython
#
# Env:
#   STANDING_APP_VERSION / STANDING_APP_BUILD
#   STANDING_SPARKLE_FEED_URL / STANDING_SPARKLE_PUBLIC_ED_KEY
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi
  echo "Installing uv (needed to fetch a relocatable Python)…" >&2
  curl -LsSf https://astral.sh/uv/install.sh | sh >&2
  export PATH="${HOME}/.local/bin:${PATH}"
  if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found on PATH after install" >&2
    exit 1
  fi
}

# Drop tooling / tests / GUI stdlib that the worker never imports.
# Keeps camera + AI deps intact (OpenCV, NumPy, Pillow, keyring, typesafe).
slim_embedded_python() {
  local pyroot="$1"
  local stdlib site

  rm -rf \
    "$pyroot/include" \
    "$pyroot/share" \
    "$pyroot/lib/pkgconfig"
  rm -rf "$pyroot/lib"/tcl* "$pyroot/lib"/tk* "$pyroot/lib"/itcl* "$pyroot/lib"/thread*

  stdlib="$(echo "$pyroot"/lib/python3.*)"
  if [[ -d "$stdlib" ]]; then
    rm -rf \
      "$stdlib/test" \
      "$stdlib/idlelib" \
      "$stdlib/tkinter" \
      "$stdlib/turtledemo" \
      "$stdlib/ensurepip" \
      "$stdlib/pydoc_data" \
      "$stdlib/lib2to3" \
      "$stdlib/config-"*
  fi

  site="$(echo "$stdlib"/site-packages)"
  if [[ -d "$site" ]]; then
    # Installer leftovers — not needed at runtime.
    rm -rf \
      "$site"/pip \
      "$site"/pip-*.dist-info \
      "$site"/setuptools \
      "$site"/setuptools-*.dist-info \
      "$site"/_distutils_hack \
      "$site"/pkg_resources \
      "$site"/wheel \
      "$site"/wheel-*.dist-info \
      "$site"/PyObjCTest

    # Package test suites (especially NumPy) are large and unused.
    # Prefer -print0|xargs so macOS find -o precedence cannot skip dirs.
    find "$site" -type d \( -name tests -o -name test -o -name testing \) -print0 2>/dev/null \
      | xargs -0 rm -rf 2>/dev/null || true
    find "$site" -type d -name __pycache__ -print0 2>/dev/null \
      | xargs -0 rm -rf 2>/dev/null || true
    find "$site" -type f \( -name '*.pyc' -o -name '*.pyi' -o -name 'py.typed' \) -delete 2>/dev/null || true
    # Debug symbols from some wheels (e.g. PyObjC) are never needed at runtime.
    find "$site" -type d -name '*.dSYM' -print0 2>/dev/null \
      | xargs -0 rm -rf 2>/dev/null || true
  fi

  # Stdlib bytecode caches — app sets PYTHONDONTWRITEBYTECODE.
  find "$pyroot" -type d -name __pycache__ -print0 2>/dev/null \
    | xargs -0 rm -rf 2>/dev/null || true
}

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
  # Copy worker source only — never .env, stats, calibration images, or logs.
  # Skip rumps UI modules (native Swift shell replaces them).
  REQ_RELEASE="$ROOT/requirements-release.txt"
  if [[ ! -f "$REQ_RELEASE" ]]; then
    echo "Missing $REQ_RELEASE" >&2
    exit 1
  fi
  rsync -a \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    --exclude 'main.py' \
    --exclude 'menubar.py' \
    --exclude 'settings_window.py' \
    "$ROOT/src" "$PAYLOAD/"
  cp "$REQ_RELEASE" "$PAYLOAD/requirements.txt"
  if [[ -f "$ROOT/.env.example" ]]; then
    cp "$ROOT/.env.example" "$PAYLOAD/.env.example"
  fi
  mkdir -p "$PAYLOAD/data" "$PAYLOAD/assets"
  if [[ -d "$ROOT/assets/icons" ]]; then
    rsync -a "$ROOT/assets/icons" "$PAYLOAD/assets/"
  fi

  # Embed a relocatable CPython (python-build-standalone via uv).
  # A normal `python3 -m venv` only symlinks to /Library/Frameworks or the
  # builder's toolchain — that breaks on other Macs and makes Save AI key crash.
  echo "Embedding relocatable Python runtime (this can take a few minutes)…" >&2
  ensure_uv
  uv python install 3.12 >&2
  UV_PY="$(uv python find 3.12)"
  STANDALONE_ROOT="$(cd "$(dirname "$UV_PY")/.." && pwd)"
  echo "  source: $STANDALONE_ROOT" >&2
  mkdir -p "$PAYLOAD/python"
  # Copy standalone tree; drop obvious dead weight before pip install.
  rsync -a --delete \
    --exclude '__pycache__' \
    --exclude '.DS_Store' \
    --exclude 'include/' \
    --exclude 'share/' \
    --exclude 'lib/pkgconfig/' \
    --exclude 'lib/tcl*' \
    --exclude 'lib/tk*' \
    --exclude 'lib/itcl*' \
    --exclude 'lib/thread*' \
    --exclude 'lib/python3.*/test' \
    --exclude 'lib/python3.*/idlelib' \
    --exclude 'lib/python3.*/tkinter' \
    --exclude 'lib/python3.*/turtledemo' \
    --exclude 'lib/python3.*/pydoc_data' \
    --exclude 'lib/python3.*/lib2to3' \
    --exclude 'lib/python3.*/config-*' \
    "$STANDALONE_ROOT/" "$PAYLOAD/python/"
  EMBED_PY="$PAYLOAD/python/bin/python3"
  if [[ ! -x "$EMBED_PY" ]]; then
    EMBED_PY="$PAYLOAD/python/bin/python3.12"
  fi
  if [[ ! -x "$EMBED_PY" ]]; then
    echo "Embedded Python missing at $PAYLOAD/python/bin" >&2
    exit 1
  fi
  # This is our private copy — remove uv's PEP 668 marker so pip can install deps.
  find "$PAYLOAD/python" -name EXTERNALLY-MANAGED -delete
  # Install worker deps only (no rumps/PyObjC).
  "$EMBED_PY" -m ensurepip --upgrade >/dev/null 2>&1 || true
  "$EMBED_PY" -m pip install --upgrade --no-cache-dir pip >&2
  "$EMBED_PY" -m pip install --no-cache-dir -r "$PAYLOAD/requirements.txt" >&2
  echo "Slimming embedded Python…" >&2
  BEFORE_BYTES="$(du -sk "$PAYLOAD/python" | awk '{print $1}')"
  slim_embedded_python "$PAYLOAD/python"
  AFTER_BYTES="$(du -sk "$PAYLOAD/python" | awk '{print $1}')"
  echo "  embedded python: $((BEFORE_BYTES / 1024))M → $((AFTER_BYTES / 1024))M" >&2
  # Prove the runtime is self-contained (no dangling Framework symlink).
  (
    cd "$PAYLOAD"
    "$EMBED_PY" -c "import keyring, cv2, dotenv, numpy, PIL, typesafe_sdk; print('embedded imports ok')"
  ) >&2

  LS_ENVIRONMENT=$(cat <<EOF
	<key>LSEnvironment</key>
	<dict>
		<key>PYTHONUNBUFFERED</key>
		<string>1</string>
		<key>PYTHONDONTWRITEBYTECODE</key>
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
