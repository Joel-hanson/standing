"""Mac menu-bar glance UI — quiet in the bar, clear when you look."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import rumps

from src.core import calibration_label
from src.icons import icon_path
from src.support import open_support, support_menu_title
from src.tracker import format_duration

if TYPE_CHECKING:
    from src.tracker import TrackerSnapshot

# Re-export for callers that imported from menubar.
__all__ = ["StandingMenuBar", "calibration_label"]


class StandingMenuBar(rumps.App):
    """Lives in the Mac menu bar like other status apps."""

    def __init__(
        self,
        *,
        on_toggle_tracking: Callable[[], None],
        on_reset_day: Callable[[], None],
        on_toggle_suggestions: Callable[[], None],
        on_open_settings: Callable[[], None],
        on_quit: Callable[[], None],
        suggestions_enabled: bool = True,
    ) -> None:
        super().__init__(
            name="Standing",
            title="",
            icon=icon_path("paused"),
            template=True,
            quit_button=None,
        )
        self._on_toggle = on_toggle_tracking
        self._on_reset = on_reset_day
        self._on_toggle_suggestions = on_toggle_suggestions
        self._on_open_settings = on_open_settings
        self._on_quit = on_quit

        # Glance band — read-only
        self.status_item = rumps.MenuItem("Paused")
        self.today_item = rumps.MenuItem("Today —")
        self.hint_item = rumps.MenuItem("Open Settings to finish setup")
        for item in (self.status_item, self.today_item, self.hint_item):
            item.set_callback(None)

        # Actions — Start stays hidden until an API key is set (setup CTA instead).
        self.setup_item = rumps.MenuItem("Set up Standing…", callback=self._settings)
        self.toggle_item = rumps.MenuItem("Start Tracking", callback=self._toggle)
        self.toggle_item.hidden = True
        self.suggestions_item = rumps.MenuItem(
            "Suggestions",
            callback=self._toggle_suggestions,
        )
        self.suggestions_item.state = suggestions_enabled

        self.menu = [
            self.status_item,
            self.today_item,
            self.hint_item,
            None,
            self.setup_item,
            self.toggle_item,
            None,
            self.suggestions_item,
            rumps.MenuItem("Reset Today…", callback=self._reset),
            None,
            rumps.MenuItem("Settings…", callback=self._settings, key=","),
            rumps.MenuItem(support_menu_title(), callback=self._support),
            rumps.MenuItem("Quit Standing", callback=self._quit),
        ]

    def _toggle(self, _sender: rumps.MenuItem | None = None) -> None:
        self._on_toggle()

    def _reset(self, _sender: rumps.MenuItem | None = None) -> None:
        self._on_reset()

    def _toggle_suggestions(self, _sender: rumps.MenuItem | None = None) -> None:
        self._on_toggle_suggestions()

    def _settings(self, _sender: rumps.MenuItem | None = None) -> None:
        self._on_open_settings()

    def _support(self, _sender: rumps.MenuItem | None = None) -> None:
        open_support()

    def _quit(self, _sender: rumps.MenuItem | None = None) -> None:
        self._on_quit()
        rumps.quit_application()

    def prompt_api_key(self) -> str | None:
        """Native secure-style prompt; return key or None if cancelled."""
        window = rumps.Window(
            message="Paste your TypeSafe API key.\nGet one at console.typesafe.ai → API Keys.\nIt is stored in the macOS Keychain.",
            title="Standing",
            default_text="",
            ok="Save",
            cancel="Cancel",
            dimensions=(320, 24),
        )
        response = window.run()
        if not response.clicked:
            return None
        text = (response.text or "").strip()
        return text or None

    def update(
        self,
        snap: TrackerSnapshot,
        *,
        has_standing_cal: bool,
        has_sitting_cal: bool,
        has_api_key: bool,
        suggestions_enabled: bool,
    ) -> None:
        setup_needed = not has_api_key or not (has_standing_cal and has_sitting_cal)
        cal = calibration_label(
            has_standing=has_standing_cal,
            has_sitting=has_sitting_cal,
        )

        if snap.last_error:
            self._set_bar(icon="warn", title="")
            self.status_item.title = f"Error: {snap.last_error[:48]}"
            self.toggle_item.title = "Start Tracking" if not snap.tracking else "Pause Tracking"
        elif not snap.tracking:
            self._set_bar(icon="paused", title="")
            self.status_item.title = "Paused" if has_api_key else "Needs setup"
            self.toggle_item.title = "Start Tracking"
        elif snap.posture == "standing":
            streak = format_duration(snap.standing_streak_seconds)
            self._set_bar(icon="stand", title=streak)
            self.status_item.title = f"Standing · {streak} streak"
            self.toggle_item.title = "Pause Tracking"
        elif snap.posture == "sitting":
            streak = format_duration(snap.sitting_streak_seconds)
            self._set_bar(icon="sit", title=streak)
            self.status_item.title = f"Sitting · {streak} streak"
            self.toggle_item.title = "Pause Tracking"
        elif snap.posture == "away":
            self._set_bar(icon="away", title="")
            self.status_item.title = "Away"
            self.toggle_item.title = "Pause Tracking"
        else:
            self._set_bar(icon="paused", title="…")
            self.status_item.title = "Checking posture…"
            self.toggle_item.title = "Pause Tracking"

        self.today_item.title = (
            f"Today  {snap.stand_ups} stand-ups · "
            f"Stand {format_duration(snap.standing_seconds_today)} · "
            f"Sit {format_duration(snap.sitting_seconds_today)}"
        )

        # Onboarding: no Start until a TypeSafe key is saved (Keychain / env).
        self.setup_item.hidden = has_api_key
        self.toggle_item.hidden = not has_api_key

        if not has_api_key:
            self.hint_item.title = "1) Add API key  →  2) Calibrate  →  3) Start"
            self.hint_item.hidden = False
        elif not (has_standing_cal and has_sitting_cal):
            self.hint_item.title = f"{cal} — Settings → Calibration"
            self.hint_item.hidden = False
        else:
            self.hint_item.title = cal
            self.hint_item.hidden = not setup_needed

        self.suggestions_item.state = suggestions_enabled

    def _set_bar(self, *, icon: str, title: str) -> None:
        path = icon_path(icon)
        if path and self.icon != path:
            self.icon = path
            self.template = True
        self.title = title

    def notify(self, title: str, message: str) -> None:
        rumps.notification("Standing", title, message)
