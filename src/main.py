"""Standing: AI-based standing tracker — Mac menu bar + Jev posture checks (rumps shell)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import rumps
from dotenv import load_dotenv

from src.core import ROOT, StandingCore, add_common_args
from src.credentials import get_api_key, has_keychain_key
from src.logging_setup import setup_logging
from src.menubar import StandingMenuBar
from src.settings_window import SettingsSnapshot, SettingsWindow


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Standing — AI-based standing tracker for Mac")
    add_common_args(p)
    return p.parse_args(argv)


class App:
    """Rumps UI adapter over StandingCore."""

    def __init__(self, args: argparse.Namespace, log_path: Path | None) -> None:
        self.core = StandingCore(args, log_path)
        self.ui = StandingMenuBar(
            on_toggle_tracking=self.core.toggle_tracking,
            on_reset_day=self.core.reset_day,
            on_toggle_suggestions=self.core.toggle_suggestions,
            on_open_settings=self.open_settings,
            on_quit=self.core.shutdown,
            suggestions_enabled=self.core.suggestions.enabled,
        )
        self.settings = SettingsWindow(
            on_save_api_key=lambda key: self.core.save_api_key(key),
            on_clear_api_key=self.core.clear_api_key,
            on_toggle_suggestions=self.core.set_suggestions,
            on_apply_thresholds=self.core.apply_thresholds,
            on_calibrate_sitting=lambda: self.core.calibrate("sitting"),
            on_calibrate_standing=lambda: self.core.calibrate("standing"),
            on_clear_calibration=self.core.clear_calibration,
            on_open_log=self.core.open_log,
            on_connect_strava=self.core.connect_strava,
            on_disconnect_strava=self.core.disconnect_strava,
        )
        self.core.set_callbacks(on_state=self._on_state, on_notify=self.ui.notify)

    def open_settings(self) -> None:
        self.settings.show(self._settings_snapshot())

    def _settings_snapshot(self) -> SettingsSnapshot:
        state = self.core.snapshot_state()
        return SettingsSnapshot(
            has_api_key=state.has_api_key,
            suggestions_enabled=state.suggestions_enabled,
            calibration_label=state.calibration_label,
            usage_label=state.usage_label,
            history_label=state.history_label,
            sit_warn_minutes=state.sit_warn_minutes,
            stand_warn_minutes=state.stand_warn_minutes,
            strava_connected=state.strava_connected,
            strava_configured=state.strava_configured,
            strava_label=state.strava_label,
        )

    def _on_state(self, _state: dict) -> None:
        snap_state = self.core.snapshot_state()
        # Rebuild a TrackerSnapshot-compatible update via core fields.
        from src.tracker import TrackerSnapshot

        snap = TrackerSnapshot(
            posture=snap_state.posture,  # type: ignore[arg-type]
            stand_ups=snap_state.stand_ups,
            standing_seconds_today=snap_state.standing_seconds_today,
            sitting_seconds_today=snap_state.sitting_seconds_today,
            standing_streak_seconds=snap_state.standing_streak_seconds,
            sitting_streak_seconds=snap_state.sitting_streak_seconds,
            api_calls=snap_state.api_calls,
            input_tokens=snap_state.input_tokens,
            estimated_cost_usd=snap_state.estimated_cost_usd,
            tracking=snap_state.tracking,
            last_error=snap_state.last_error,
            motion_score=0.0,
            last_call_reason=None,
        )
        self.ui.update(
            snap,
            has_standing_cal=snap_state.has_standing_cal,
            has_sitting_cal=snap_state.has_sitting_cal,
            has_api_key=snap_state.has_api_key,
            suggestions_enabled=snap_state.suggestions_enabled,
        )
        self.settings.refresh(self._settings_snapshot())

    def run(self) -> None:
        self.core.publish_state()
        if not get_api_key():
            # First-run onboarding: open Settings instead of offering Start.
            self.open_settings()
            self.ui.notify(
                "Welcome to Standing",
                "Paste your TypeSafe AI key, then calibrate sit + stand.",
            )

        def _pulse(_sender: rumps.Timer) -> None:
            with self.core._lock:  # noqa: SLF001
                self.core.tracker.tick()
                self.core.publish_state()
                self.core._maybe_suggest()  # noqa: SLF001

        self._ui_timer = rumps.Timer(_pulse, 0.5)
        self._ui_timer.start()
        self.ui.run()

    def shutdown(self) -> None:
        self.core.shutdown()


def main(argv: list[str] | None = None) -> int:
    # Allow `python -m src.main --worker` for convenience.
    raw = list(argv) if argv is not None else sys.argv[1:]
    if raw and raw[0] == "--worker":
        from src.worker import main as worker_main

        return worker_main(raw[1:])

    load_dotenv(ROOT / ".env")
    args = parse_args(raw)

    log_path: Path | None = None
    if args.log_file:
        log_path = Path(args.log_file).expanduser()
    setup_logging(verbose=args.verbose, log_file=log_path)

    key = get_api_key()
    key_src = "Keychain" if has_keychain_key() else (".env/env" if key else "missing")

    print(
        "Standing — AI-based standing tracker — is in your Mac menu bar (top-right, near the clock).\n"
        "1) Settings… → API key  2) Calibrate sit + stand  3) Start Tracking\n"
        f"API key: {key_src} · image max-side={args.max_side}px\n"
        f"Logs: terminal"
        + (f" + {log_path}" if log_path else "")
        + (" (verbose)" if args.verbose else "")
        + ".\n"
        "Quit from the menu, or Ctrl+C in this terminal.\n"
        "Tip: SwiftUI shell → open native/Standing and run, or: python -m src.worker\n",
        flush=True,
    )
    app = App(args, log_path)
    try:
        app.run()
    finally:
        app.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
