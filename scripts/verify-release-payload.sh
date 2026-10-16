#!/usr/bin/env bash
# Verify a release Standing.app embeds a relocatable CPython for the given arch.
#
# Usage:
#   ./scripts/verify-release-payload.sh /path/to/Standing.app arm64
#   ./scripts/verify-release-payload.sh /path/to/Standing.app x86_64
set -euo pipefail

APP="${1:?Standing.app path required}"
WANT_ARCH="${2:?arch required (arm64|x86_64)}"

case "$WANT_ARCH" in
  arm64|x86_64) ;;
  *)
    echo "Unsupported arch: $WANT_ARCH" >&2
    exit 1
    ;;
esac

PAYLOAD="$APP/Contents/Resources/StandingPayload"
SHELL_BIN="$APP/Contents/MacOS/Standing"
EMBED_PY="$PAYLOAD/python/bin/python3"
if [[ ! -e "$EMBED_PY" && ! -L "$EMBED_PY" ]]; then
  EMBED_PY="$PAYLOAD/python/bin/python3.12"
fi

test -x "$SHELL_BIN"
test -e "$EMBED_PY" || test -L "$EMBED_PY"

if [[ -f "$PAYLOAD/python/pyvenv.cfg" ]]; then
  echo "Embedded Python is a virtualenv; it will not run on other Macs." >&2
  exit 1
fi

REAL_PY="$EMBED_PY"
for _ in 1 2 3 4 5 6 7 8; do
  if [[ ! -L "$REAL_PY" ]]; then
    break
  fi
  LINK="$(readlink "$REAL_PY")"
  if [[ "$LINK" != /* ]]; then
    REAL_PY="$(cd "$(dirname "$REAL_PY")" && pwd)/$LINK"
  else
    REAL_PY="$LINK"
  fi
done

case "$(cd "$(dirname "$REAL_PY")" && pwd)/" in
  "$PAYLOAD/python/"*) ;;
  *)
    echo "Embedded Python resolves outside the app: $REAL_PY" >&2
    exit 1
    ;;
esac
test -x "$REAL_PY"

for bin in "$SHELL_BIN" "$REAL_PY"; do
  case " $(lipo -archs "$bin") " in
    *" $WANT_ARCH "*) ;;
    *)
      echo "Expected $WANT_ARCH Mach-O, got [$(lipo -archs "$bin")]: $bin" >&2
      exit 1
      ;;
  esac
done

(
  cd "$PAYLOAD"
  "$EMBED_PY" -c "import platform, keyring, cv2, dotenv; assert platform.machine() == '${WANT_ARCH}', platform.machine(); print('embedded python ok', platform.machine())"
)

echo "release payload ok ($WANT_ARCH): $APP"
