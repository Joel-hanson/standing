"""User-writable storage for Standing (macOS Application Support + Logs).

The app bundle / repo tree is not writable in a release install, so runtime
state lives under the standard per-user Library locations. Override with
STANDING_DATA_DIR / STANDING_LOG_DIR when needed (tests, portable runs).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

APP_NAME = "Standing"

_LEGACY_DATA_FILES = (
    "stats.json",
    "history.json",
    "calibrate_standing.jpg",
    "calibrate_sitting.jpg",
)


def user_data_dir() -> Path:
    override = os.environ.get("STANDING_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / "Library" / "Application Support" / APP_NAME).resolve()


def user_log_dir() -> Path:
    override = os.environ.get("STANDING_LOG_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / "Library" / "Logs" / APP_NAME).resolve()


def migrate_legacy_repo_data(repo_root: Path) -> None:
    """Copy one-time from the old repo `data/` folder into Library paths."""
    legacy = repo_root / "data"
    if not legacy.is_dir():
        return

    try:
        data = user_data_dir()
        already = any((data / name).is_file() for name in ("stats.json", "history.json"))
        if not already:
            for name in _LEGACY_DATA_FILES:
                src = legacy / name
                if not src.is_file():
                    continue
                data.mkdir(parents=True, exist_ok=True)
                dest = data / name
                if not dest.exists():
                    shutil.copy2(src, dest)

        legacy_log = legacy / "standing.log"
        dest_log = user_log_dir() / "standing.log"
        if legacy_log.is_file() and not dest_log.exists():
            dest_log.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy_log, dest_log)
    except OSError:
        # Never block startup if Library paths are unavailable.
        return


def ensure_dirs(*, repo_root: Path | None = None) -> None:
    user_data_dir().mkdir(parents=True, exist_ok=True)
    user_log_dir().mkdir(parents=True, exist_ok=True)
    if repo_root is not None:
        migrate_legacy_repo_data(repo_root)
