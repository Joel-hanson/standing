#!/bin/zsh
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

if pgrep -x "Cursor" >/dev/null 2>&1; then
  echo "Cursor is still running. Quit Cursor fully (Cmd+Q), then rerun this script."
  exit 1
fi

echo "Migrating chat metadata: Standing-or-not -> standing"
cursor-move --metadata-only \
  '/Users/joelhanson/Desktop/Personal/Standing-or-not' \
  '/Users/joelhanson/Desktop/Personal/standing'

echo
echo "Done. Open /Users/joelhanson/Desktop/Personal/standing in Cursor."
