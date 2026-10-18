#!/usr/bin/env bash
# Build a Mac App Store–oriented .pkg from Standing.app.
#
# Prerequisites (Apple Developer Program):
#   1. App ID ai.standing.mac with App Sandbox + Camera (+ Network Client)
#   2. Certificates in Keychain:
#        - "Apple Distribution" (or "3rd Party Mac Developer Application")
#        - "3rd Party Mac Developer Installer"
#   3. Mac App Store provisioning profile matching that App ID
#   4. App record in App Store Connect
#
# Usage:
#   export STANDING_APP_VERSION=0.2.0 STANDING_APP_BUILD=3
#   export STANDING_MAS_APP_IDENTITY="Apple Distribution: Your Name (TEAMID)"
#   export STANDING_MAS_INSTALLER_IDENTITY="3rd Party Mac Developer Installer: Your Name (TEAMID)"
#   export STANDING_MAS_PROVISIONING_PROFILE="$HOME/Library/MobileDevice/Provisioning Profiles/Standing_MAS.provisionprofile"
#   ./scripts/package-mas.sh
#
# Output:
#   dist/Standing-<version>-mas.pkg   → upload with Transporter / altool / notary is N/A
#
# Without identities: builds an unsigned MAS-entitled .app under native/Standing/
# for local sandbox smoke tests only (will not install via App Store).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP_VERSION="${STANDING_APP_VERSION:-0.2.0}"
APP_BUILD="${STANDING_APP_BUILD:-1}"
SHIP_ARCH="${STANDING_SHIP_ARCH:-$(uname -m)}"
DIST="$ROOT/dist"
APP="$ROOT/native/Standing/Standing.app"
ENTITLEMENTS="$ROOT/native/Standing/Standing.mas.entitlements"
PKG="$DIST/Standing-${APP_VERSION}-mas.pkg"
PROFILE="${STANDING_MAS_PROVISIONING_PROFILE:-}"
APP_IDENTITY="${STANDING_MAS_APP_IDENTITY:-}"
INSTALLER_IDENTITY="${STANDING_MAS_INSTALLER_IDENTITY:-}"

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      sed -n '2,28p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

chmod +x "$ROOT/scripts/package-app.sh" "$ROOT/scripts/verify-release-payload.sh"

echo "Packaging MAS Standing.app (v$APP_VERSION build $APP_BUILD, $SHIP_ARCH)…" >&2
STANDING_APP_VERSION="$APP_VERSION" \
  STANDING_APP_BUILD="$APP_BUILD" \
  STANDING_SHIP_ARCH="$SHIP_ARCH" \
  ./scripts/package-app.sh --mas >/dev/null

test -d "$APP"
./scripts/verify-release-payload.sh "$APP" "$SHIP_ARCH"

# Confirm distribution + sandbox entitlement baked in.
DIST_MARK="$(/usr/libexec/PlistBuddy -c 'Print :StandingDistribution' "$APP/Contents/Info.plist" 2>/dev/null || true)"
if [[ "$DIST_MARK" != "mas" ]]; then
  echo "Expected StandingDistribution=mas in Info.plist (got: ${DIST_MARK:-empty})" >&2
  exit 1
fi
if ! grep -q 'com.apple.security.app-sandbox' "$ENTITLEMENTS"; then
  echo "MAS entitlements missing app-sandbox" >&2
  exit 1
fi
test -f "$APP/Contents/Resources/PrivacyInfo.xcprivacy"

mkdir -p "$DIST"

if [[ -z "$APP_IDENTITY" || -z "$INSTALLER_IDENTITY" ]]; then
  echo "No STANDING_MAS_APP_IDENTITY / STANDING_MAS_INSTALLER_IDENTITY — left ad-hoc signed .app for sandbox smoke." >&2
  echo "Set both identities + STANDING_MAS_PROVISIONING_PROFILE to produce an uploadable .pkg." >&2
  echo "$APP"
  exit 0
fi

if [[ -n "$PROFILE" ]]; then
  if [[ ! -f "$PROFILE" ]]; then
    echo "Provisioning profile not found: $PROFILE" >&2
    exit 1
  fi
  echo "Embedding provisioning profile…" >&2
  cp "$PROFILE" "$APP/Contents/embedded.provisionprofile"
else
  echo "Warning: STANDING_MAS_PROVISIONING_PROFILE unset — App Store upload will fail without it." >&2
fi

echo "Codesigning for Mac App Store ($APP_IDENTITY)…" >&2
# Sign nested Mach-O first (deepest helpers), then frameworks, then the app.
while IFS= read -r -d '' bin; do
  codesign --force --options runtime --timestamp \
    --sign "$APP_IDENTITY" --entitlements "$ENTITLEMENTS" "$bin" || true
done < <(find "$APP/Contents/Resources" -type f \( -perm +111 -o -name '*.dylib' -o -name '*.so' \) -print0 2>/dev/null)

if [[ -d "$APP/Contents/Frameworks/Sparkle.framework" ]]; then
  codesign --force --options runtime --timestamp --sign "$APP_IDENTITY" \
    "$APP/Contents/Frameworks/Sparkle.framework"
fi

codesign --force --options runtime --timestamp \
  --sign "$APP_IDENTITY" --entitlements "$ENTITLEMENTS" \
  "$APP/Contents/MacOS/Standing"
codesign --force --options runtime --timestamp \
  --sign "$APP_IDENTITY" --entitlements "$ENTITLEMENTS" "$APP"
codesign --verify --verbose=2 "$APP"

echo "Building installer package…" >&2
productbuild \
  --component "$APP" /Applications \
  --sign "$INSTALLER_IDENTITY" \
  "$PKG"

echo "MAS package ready: $PKG" >&2
echo "Upload with Transporter (or: xcrun altool --upload-app -f \"$PKG\" …)" >&2
echo "$PKG"
