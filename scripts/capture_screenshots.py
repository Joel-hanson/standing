#!/usr/bin/env python3
"""Capture Standing Settings for the landing page (web/screenshots/settings.png).

Requires Screen Recording permission for Terminal/Cursor, and:
  pip install pyobjc-framework-Quartz

Usage:
  python scripts/capture_screenshots.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "web" / "screenshots" / "settings.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

from AppKit import (  # noqa: E402
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBitmapImageRep,
    NSPNGFileType,
)
from Foundation import NSObject, NSTimer  # noqa: E402
from PyObjCTools import AppHelper  # noqa: E402
from Quartz import (  # noqa: E402
    CGRectNull,
    CGWindowListCreateImage,
    kCGWindowImageBoundsIgnoreFraming,
    kCGWindowListOptionIncludingWindow,
)

from src.settings_window import SettingsSnapshot, SettingsWindow  # noqa: E402


class _Runner(NSObject):
    def run_(self, _timer) -> None:  # noqa: N802
        noop = lambda *a, **k: None  # noqa: E731
        self._win = SettingsWindow(
            on_save_api_key=noop,
            on_clear_api_key=noop,
            on_toggle_suggestions=noop,
            on_apply_thresholds=noop,
            on_calibrate_sitting=noop,
            on_calibrate_standing=noop,
            on_clear_calibration=noop,
            on_open_log=noop,
        )
        self._win.show(
            SettingsSnapshot(
                has_api_key=True,
                suggestions_enabled=True,
                calibration_label="Calibration: sitting + standing set",
                usage_label="12 checks · ~4.2k tokens · ~$0.01",
                history_label="Today  ·  4 stand-ups · Stand 1h 12m · Sit 3h 40m\nYesterday  ·  6 stand-ups · Stand 1h 45m · Sit 4h 10m",
                sit_warn_minutes=30,
                stand_warn_minutes=45,
            )
        )
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.8, self, "capture:", None, False
        )

    def capture_(self, _timer) -> None:  # noqa: N802
        nsw = self._win._controller._window  # noqa: SLF001
        assert nsw is not None
        cg = CGWindowListCreateImage(
            CGRectNull,
            kCGWindowListOptionIncludingWindow,
            int(nsw.windowNumber()),
            kCGWindowImageBoundsIgnoreFraming,
        )
        if cg is None:
            print(
                "Capture failed — grant Screen Recording to your terminal, then retry.",
                file=sys.stderr,
            )
            AppHelper.stopEventLoop()
            return
        rep = NSBitmapImageRep.alloc().initWithCGImage_(cg)
        data = rep.representationUsingType_properties_(NSPNGFileType, None)
        data.writeToFile_atomically_(str(OUT), True)
        print(f"Wrote {OUT}")
        AppHelper.stopEventLoop()


def main() -> int:
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    app.activateIgnoringOtherApps_(True)
    runner = _Runner.alloc().init()
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        0.2, runner, "run:", None, False
    )
    AppHelper.runConsoleEventLoop()
    return 0 if OUT.is_file() else 1


if __name__ == "__main__":
    raise SystemExit(main())
