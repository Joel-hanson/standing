"""One-time Support link — app stays fully free; no feature locks."""

from __future__ import annotations

import os
import webbrowser

# Buy Me a Coffee page. Override anytime with STANDING_SUPPORT_URL.
DEFAULT_SUPPORT_URL = "https://buymeacoffee.com/joelhanson"
def support_url() -> str:
    return (os.environ.get("STANDING_SUPPORT_URL") or "").strip() or DEFAULT_SUPPORT_URL


def support_menu_title() -> str:
    return "Support Standing…"


def open_support() -> None:
    webbrowser.open(support_url())
