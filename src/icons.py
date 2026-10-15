"""Template menu-bar icons (monochrome PNGs for light/dark menu bars)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "assets" / "icons"


def icon_path(name: str) -> str | None:
    path = ICON_DIR / f"{name}.png"
    return str(path) if path.is_file() else None
